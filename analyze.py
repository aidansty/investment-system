import sys
import time
import json
from datetime import date

from utils.market_calendar import is_trading_day
from utils.logger import log
from config.universe import get_universe
from data.fetch_macro import fetch_macro_data
from data.fetch_prices import fetch_all_prices
from data.fetch_fundamentals import fetch_fundamentals_batch
from data.fetch_news import fetch_market_news
from signals.breadth import calculate_breadth
from signals.relative_strength import calculate_relative_strength, get_rs_qualified
from signals.trend_filter import apply_trend_filter
from engine.regime import determine_regime
from engine.scanner import run_full_scan
from engine.portfolio import get_open_positions, update_position_prices
from ai.briefing import generate_daily_briefing
from output.notion import write_daily_briefing, write_trade_candidates


def save_morning_snapshot(scan_results, fundamentals, regime, today):
    """
    Save morning scan results for afternoon comparison.
    Includes fundamentals so afternoon run does not need to re-fetch.
    """
    import os
    os.makedirs("data/cache", exist_ok=True)

    snapshot = {
        "date": today.isoformat(),
        "regime": {
            "label": regime["label"],
            "confidence": regime["confidence"],
            "bullish_points": regime["bullish_points"],
            "bearish_points": regime["bearish_points"],
        },
        "strong": scan_results.get("strong", []),
        "developing": scan_results.get("developing", []),
        "watch": scan_results.get("watch", []),
        "fundamentals_ticker_list": list(fundamentals.keys()),
    }

    path = f"data/cache/morning_snapshot_{today.isoformat()}.json"
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)

    log(f"Morning snapshot saved: {path}")


def main():
    start = time.time()
    try:
        import pytz
        from datetime import datetime as dt
        eastern = pytz.timezone("America/New_York")
        today = dt.now(eastern).date()
    except Exception:
        today = date.today()
    log(f"=== Investment System starting: {today} ===")

    if not is_trading_day(today):
        log("Market closed today. Exiting cleanly.")
        sys.exit(0)

    universe = get_universe()
    log(f"Universe loaded: {len(universe)} tickers")

    macro = fetch_macro_data()
    if macro is None:
        log("ERROR: Macro data fetch failed. Cannot continue.")
        sys.exit(1)

    log("Fetching universe prices...")
    prices = fetch_all_prices(universe)
    if prices is None:
        log("ERROR: Price fetch failed coverage threshold. Cannot continue.")
        sys.exit(1)

    breadth = calculate_breadth(prices)
    macro["breadth_pct"] = breadth
    regime = determine_regime(macro)

    positions = []
    try:
        positions = get_open_positions(price_cache=prices)
        if positions:
            update_position_prices(positions)
    except Exception as e:
        log(f"CRITICAL PORTFOLIO EXCEPTION: Risk tracking impaired: {e}")

    scan_results = {"strong": [], "developing": [], "watch": [], "scan_stats": {}}
    fundamentals = {}
    try:
        rs_scores = calculate_relative_strength(prices)
        rs_qualified = get_rs_qualified(rs_scores)
        trend_qualified = apply_trend_filter(prices, rs_qualified)
        log(f"Technical filter: {len(trend_qualified)} qualified tickers")

        fundamentals = fetch_fundamentals_batch(trend_qualified)

        coverage = len(fundamentals) / max(len(trend_qualified), 1)
        if coverage < 0.5:
            log(f"CRITICAL ERROR: Fundamentals coverage only {coverage:.0%}. Aborting scan.")
            sys.exit(1)

        scan_results = run_full_scan(prices, fundamentals, regime)

    except SystemExit:
        raise
    except Exception as e:
        log(f"SCANNER EXCEPTION: {e}")

    # Save morning snapshot for afternoon comparison
    try:
        save_morning_snapshot(scan_results, fundamentals, regime, today)
    except Exception as e:
        log(f"WARNING: Could not save morning snapshot: {e}")

    news = fetch_market_news()

    briefing = None
    try:
        briefing = generate_daily_briefing(
            regime=regime,
            macro=macro,
            news=news,
            candidates=scan_results,
            positions=positions,
            today=today
        )
    except Exception as e:
        log(f"CRITICAL ERROR: AI briefing generation failed: {e}")

    if briefing:
        try:
            page_url = write_daily_briefing(
                briefing=briefing,
                regime=regime,
                scan_results=scan_results,
                today=today
            )
            if page_url:
                log(f"Briefing URL: {page_url}")
            else:
                log("WARNING: Daily briefing failed to save to Notion")
        except Exception as e:
            log(f"ERROR: Could not write daily briefing to Notion: {e}")
    else:
        log("WARNING: No briefing generated — skipping Notion write")

    try:
        write_trade_candidates(scan_results, regime, today)
    except Exception as e:
        log(f"ERROR: Could not write trade candidates to Notion: {e}")

    elapsed = time.time() - start
    log(f"=== Daily briefing complete: {today} | Runtime: {elapsed:.1f}s ===")


if __name__ == "__main__":
    main()
