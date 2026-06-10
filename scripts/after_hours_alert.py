import os
import sys
import json
import time
import requests
from datetime import date

from utils.market_calendar import is_trading_day
from utils.logger import log
from utils.rate_limiter import finnhub_limiter
from config.universe import get_universe
from data.fetch_prices import fetch_all_prices
from data.fetch_fundamentals import fetch_fundamentals_batch
from signals.relative_strength import calculate_relative_strength, get_rs_qualified
from signals.trend_filter import apply_trend_filter
from signals.breadth import calculate_breadth
from data.fetch_macro import fetch_macro_data
from engine.regime import determine_regime
from engine.scanner import run_full_scan
from engine.portfolio import get_open_positions
from ai.after_hours import generate_after_hours_briefing
from output.notion import write_after_hours_alert

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")


def load_morning_snapshot(today):
    """Load this morning's scan results for comparison."""
    path = f"data/cache/morning_snapshot_{today.isoformat()}.json"
    try:
        with open(path, "r") as f:
            snapshot = json.load(f)
        log(f"Morning snapshot loaded: {len(snapshot.get('strong', []))} strong, "
            f"{len(snapshot.get('developing', []))} developing")
        return snapshot
    except FileNotFoundError:
        log("No morning snapshot found for today — skipping candidate comparison")
        return None


def fetch_ticker_news(ticker: str) -> list:
    """
    Fetch ticker-specific news from Finnhub.
    Returns structured news items for one ticker.
    """
    try:
        finnhub_limiter.wait()
        url = (
            f"https://finnhub.io/api/v1/company-news"
            f"?symbol={ticker}&from={date.today().isoformat()}"
            f"&to={date.today().isoformat()}&token={FINNHUB_KEY}"
        )
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        results = []
        for item in data[:5]:
            headline = item.get("headline", "").strip()
            if headline:
                results.append({
                    "headline": headline,
                    "source": item.get("source", ""),
                    "datetime": str(item.get("datetime", "")),
                })
        return results
    except Exception as e:
        log(f"Ticker news fetch error for {ticker}: {e}")
        return []


def compare_snapshots(morning: dict, afternoon: dict) -> dict:
    """
    Compare morning and afternoon scan results.
    Returns dict of changes: new strong, dropped strong,
    score increases, score decreases, new catalysts.
    """
    if not morning:
        return {"no_morning_data": True}

    morning_strong = {c["ticker"]: c for c in morning.get("strong", [])}
    afternoon_strong = {c["ticker"]: c for c in afternoon.get("strong", [])}
    morning_developing = {c["ticker"]: c for c in morning.get("developing", [])}
    afternoon_developing = {c["ticker"]: c for c in afternoon.get("developing", [])}

    # New strong candidates not in morning
    new_strong = [
        c for ticker, c in afternoon_strong.items()
        if ticker not in morning_strong
    ]

    # Dropped from strong
    dropped_strong = [
        c for ticker, c in morning_strong.items()
        if ticker not in afternoon_strong
    ]

    # Score changes among strong candidates
    score_increases = []
    score_decreases = []
    for ticker, afternoon_c in afternoon_strong.items():
        if ticker in morning_strong:
            delta = afternoon_c["composite_score"] - morning_strong[ticker]["composite_score"]
            if delta >= 0.10:
                score_increases.append({**afternoon_c, "score_delta": round(delta, 3)})
            elif delta <= -0.10:
                score_decreases.append({**afternoon_c, "score_delta": round(delta, 3)})

    # New catalysts — had no catalyst this morning, has one now
    new_catalysts = []
    for ticker, afternoon_c in afternoon_strong.items():
        if ticker in morning_strong:
            had_catalyst = morning_strong[ticker].get("has_catalyst", False)
            has_catalyst_now = afternoon_c.get("has_catalyst", False)
            if not had_catalyst and has_catalyst_now:
                new_catalysts.append(afternoon_c)

    return {
        "new_strong": new_strong,
        "dropped_strong": dropped_strong,
        "score_increases": score_increases,
        "score_decreases": score_decreases,
        "new_catalysts": new_catalysts,
        "no_morning_data": False,
    }


def main():
    start = time.time()
    try:
        import pytz
        from datetime import datetime as dt
        eastern = pytz.timezone("America/New_York")
        today = dt.now(eastern).date()
    except Exception:
        today = date.today()
    log(f"=== After-Hours Monitor starting: {today} ===")

    if not is_trading_day(today):
        log("Market closed today. Exiting cleanly.")
        sys.exit(0)

    # Load morning snapshot for comparison
    morning_snapshot = load_morning_snapshot(today)

    # Fetch fresh afternoon prices
    universe = get_universe()
    prices = fetch_all_prices(universe)
    if prices is None:
        log("ERROR: Price fetch failed. Cannot continue.")
        sys.exit(1)

    # Re-run scan using MORNING fundamentals to avoid re-fetching
    # Prices change intraday, fundamentals do not
    macro = fetch_macro_data()
    if macro:
        macro["breadth_pct"] = calculate_breadth(prices)
        regime = determine_regime(macro)
    else:
        regime = {"label": "Unknown", "confidence": "Low",
                  "bullish_points": 0, "bearish_points": 0,
                  "max_positions": 1, "min_cash_pct": 0.30,
                  "stop_loss_pct": 0.08, "degraded": True, "conditions": {}}

    # Use morning fundamentals if available, otherwise re-fetch for trend-qualified
    rs_scores = calculate_relative_strength(prices)
    rs_qualified = get_rs_qualified(rs_scores)
    trend_qualified = apply_trend_filter(prices, rs_qualified)

    if morning_snapshot and morning_snapshot.get("fundamentals_ticker_list"):
        # Re-fetch only tickers that were in morning scan
        morning_tickers = set(morning_snapshot["fundamentals_ticker_list"])
        afternoon_tickers = [t for t in trend_qualified if t in morning_tickers]
        log(f"Afternoon scan: using morning fundamentals list ({len(afternoon_tickers)} tickers)")
        fundamentals = fetch_fundamentals_batch(afternoon_tickers)
    else:
        fundamentals = fetch_fundamentals_batch(trend_qualified)

    afternoon_scan = run_full_scan(prices, fundamentals, regime)

    # Compare morning vs afternoon
    changes = compare_snapshots(morning_snapshot, afternoon_scan)

    # Function 1: Position risk review
    positions = get_open_positions(price_cache=prices)

    if not positions and not any([
        changes.get("new_strong"),
        changes.get("dropped_strong"),
        changes.get("score_increases"),
        changes.get("new_catalysts"),
    ]):
        log("No positions and no material candidate changes. No alert needed.")
        sys.exit(0)

    # Fetch ticker-specific news for each held position
    for position in positions:
        ticker = position["ticker"]
        log(f"Fetching news for held position: {ticker}")
        position["ticker_news"] = fetch_ticker_news(ticker)

    # Generate combined briefing
    briefing = generate_after_hours_briefing(
        positions=positions,
        candidate_changes=changes,
        afternoon_scan=afternoon_scan,
        today=today
    )

    if briefing:
        write_after_hours_alert(briefing=briefing, positions=positions, today=today)
    else:
        log("No material after-hours developments. No alert written.")

    elapsed = time.time() - start
    log(f"=== After-Hours Monitor complete | Runtime: {elapsed:.1f}s ===")


if __name__ == "__main__":
    main()
