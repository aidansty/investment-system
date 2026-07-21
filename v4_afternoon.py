#!/usr/bin/env python3
"""
V4 Investment System — Afternoon Run
Executes at 2:45 PM ET via cron-job.org
Portfolio review and opportunities via Telegram only.
"""

import sys
import time
import json
import os
import yfinance as yf
from datetime import date

from v4.utils.logger import log
from v4.utils.market_calendar import is_trading_day, get_trading_date
from v4.utils.telegram import send_telegram
from v4.data.fetch_prices import fetch_etf_prices
from v4.data.fetch_news import fetch_rss_news
from v4.data.fetch_macro import fetch_macro_data
from v4.intelligence.industry_scanner import run_industry_scan
from v4.intelligence.event_engine import enrich_industries_with_events
from v4.ai.afternoon_update import generate_afternoon_update
from v4.output.telegram_output import build_and_send_afternoon_telegram
from v4.intelligence.rules_engine import run_rules_engine
from v4.output.dashboard_writer import write_dashboard_data
from v4.config.settings import BENCHMARK_ETF


def get_open_positions():
    import json, os
    path = os.path.join(os.path.dirname(__file__), 'v4', 'config', 'positions.json')
    with open(path) as f:
        return json.load(f).get('positions', [])


def update_position_prices(positions, price_cache):
    for p in positions:
        ticker = p.get('ticker')
        if ticker in price_cache:
            current = price_cache[ticker]
            p['current_price'] = current
            entry = p.get('entry', 0)
            qty = p.get('qty', 0)
            if entry and qty:
                p['pnl'] = round((current - entry) * qty, 2)
                p['pnl_pct'] = round((current - entry) / entry * 100, 2)

def load_morning_snapshot(today) -> list:
    path = f"data/cache/v4_morning_snapshot_{today}.json"
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        log("No morning snapshot found")
        return []


def main():
    start = time.time()
    today = get_trading_date()
    log(f"=== V4 Afternoon Run: {today} ===")

    if not is_trading_day(today):
        log("Market closed. Exiting.")
        sys.exit(0)

    # Load positions from positions.json
    positions = []
    try:
        import json as _json
        import yfinance as _yf
        with open("v4/config/positions.json", "r") as _f:
            _config = _json.load(_f)
        _raw = _config.get("positions", [])
        _stock_tickers = [p["ticker"] for p in _raw if p.get("type") != "Crypto"]
        _crypto_map = {"BTC": "BTC-USD", "ETH": "ETH-USD", "XRP": "XRP-USD", "ZEC": "ZEC-USD"}
        _price_cache = {}
        # Fetch stock prices via yfinance
        try:
            _data = _yf.download(_stock_tickers, period="2d", auto_adjust=True, progress=False)
            _close = _data["Close"] if "Close" in _data.columns else _data
            for _t in _stock_tickers:
                if _t in _close.columns:
                    _s = _close[_t].dropna()
                    if not _s.empty:
                        _price_cache[_t] = round(float(_s.iloc[-1]), 2)
        except Exception as _e:
            log(f"Stock price fetch error: {_e}")
        # Fetch crypto prices via Coinbase — yfinance crypto data is unreliable
        import requests as _req
        _coinbase_map = {"BTC": "BTC-USD", "ETH": "ETH-USD", "XRP": "XRP-USD", "ZEC": "ZEC-USD"}
        for _t, _pair in _coinbase_map.items():
            try:
                _r = _req.get(f"https://api.coinbase.com/v2/prices/{_pair}/spot", timeout=5)
                if _r.status_code == 200:
                    _price_cache[_t] = round(float(_r.json()["data"]["amount"]), 2)
            except Exception as _e:
                log(f"Coinbase price error for {_t}: {_e}")
        for _p in _raw:
            _t = _p["ticker"]
            _qty = _p["qty"]
            _entry = _p["entry"]
            _current = _price_cache.get(_t, 0)
            _balance = round(_current * _qty, 2) if _current else 0
            _pct = round((_current - _entry) / _entry * 100, 2) if _entry > 0 and _current > 0 else 0
            positions.append({
                "ticker": _t, "type": _p.get("type", "Stock"),
                "term": _p.get("term", "Medium-term"),
                "qty": _qty, "entry_price": _entry,
                "current_price": _current, "balance": _balance,
                "cost_basis": _p.get("cost_basis", 0),
                "pct_change": _pct,
                "dollar_change": round((_current - _entry) * _qty, 2) if _entry > 0 else 0,
                "industry": _p.get("industry", ""),
                "summary": _p.get("summary", ""),
                "catalyst": _p.get("catalyst", ""),
                "why": _p.get("why", ""),
                "what_to_do": _p.get("what_to_do", ""),
                "stop_price": _p.get("stop_price", 0),
                "thesis": _p.get("summary", ""),
            })
        log(f"Loaded {len(positions)} positions from positions.json")
    except Exception as e:
        log(f"Position load error: {e}")

    # Load morning snapshot
    morning_top = load_morning_snapshot(today)

    # Fetch afternoon prices
    log("Fetching ETF prices...")
    prices = fetch_etf_prices(lookback_days=90)

    # Update position prices
    if positions:
        tickers = [p["ticker"] for p in positions]
        price_cache = {}
        try:
            data = yf.download(tickers, period="2d", auto_adjust=True, progress=False)
            close = data["Close"] if "Close" in data.columns else data
            for ticker in tickers:
                if ticker in close.columns:
                    series = close[ticker].dropna()
                    if not series.empty:
                        price_cache[ticker] = round(float(series.iloc[-1]), 2)
        except Exception as e:
            log(f"Price error: {e}")
        update_position_prices(positions, price_cache)

    # COST-OPTIMIZED: Skip per-ticker Claude calls entirely.
    # Instead, fetch FREE RSS headlines and filter for holding mentions locally.
    # Only make ONE Claude call if thesis-breaking news is found.
    from v4.data.fetch_news import fetch_rss_news
    rss_raw = fetch_rss_news(hours_back=8)
    log(f"Afternoon RSS scan: {len(rss_raw)} headlines fetched (free, no Claude)")

    # Filter for headlines mentioning any current holding ticker
    holding_tickers = {p["ticker"] for p in positions}
    CRYPTO_SKIP = {"BTC", "ETH", "XRP", "ZEC"}
    stock_tickers = holding_tickers - CRYPTO_SKIP

    relevant_headlines = []
    for item in rss_raw:
        headline = (item.get("headline", "") or "").upper()
        summary = (item.get("summary", "") or "").upper()
        text = headline + " " + summary
        for tk in stock_tickers:
            if tk in text:
                item["matched_ticker"] = tk
                relevant_headlines.append(item)
                break

    log(f"Afternoon: {len(relevant_headlines)} headlines mention current holdings")

    # Also check for broad market-moving keywords
    urgent_keywords = ["FED ", "FOMC", "RATE CUT", "RATE HIKE", "CPI ", "INFLATION",
                        "CRASH", "SELLOFF", "SELL-OFF", "CIRCUIT BREAKER", "BLACK SWAN",
                        "WAR ", "BOMB", "SANCTION", "TARIFF", "BAN "]
    for item in rss_raw:
        if item in relevant_headlines:
            continue
        text = ((item.get("headline", "") or "") + " " + (item.get("summary", "") or "")).upper()
        if any(kw in text for kw in urgent_keywords):
            item["matched_ticker"] = "MACRO"
            relevant_headlines.append(item)

    news = relevant_headlines
    forward_catalysts = []
    news_package = {"recent_news": news, "forward_catalysts": []}

    # Intraday crash detection — alert if any stock drops 5%+ even with zero news
    CRYPTO_SKIP_CRASH = {"BTC", "ETH", "XRP", "ZEC", "SOL", "BNB"}
    morning_prices = {}
    try:
        import json as _json2
        snapshot_path = f"data/cache/v4_morning_snapshot_{today}.json"
        with open(snapshot_path) as _sf:
            snap = _json2.load(_sf)
        for sp in snap.get("positions", []):
            morning_prices[sp.get("ticker", "")] = sp.get("current_price", 0)
    except Exception:
        pass
    # Fetch intraday LOWS — catches flash crashes that recovered before 2:45 PM
    intraday_lows = {}
    try:
        _crash_tickers = [p.get("ticker", "") for p in positions if p.get("ticker", "") not in CRYPTO_SKIP_CRASH and p.get("ticker", "") != "SPY"]
        if _crash_tickers:
            import yfinance as _yf_crash
            _crash_data = _yf_crash.download(_crash_tickers, period="1d", interval="1d", progress=False)
            if "Low" in _crash_data.columns:
                _low_col = _crash_data["Low"]
                for _ct in _crash_tickers:
                    if _ct in _low_col.columns:
                        _low_val = _low_col[_ct].dropna()
                        if not _low_val.empty:
                            intraday_lows[_ct] = round(float(_low_val.iloc[-1]), 2)
                    elif len(_crash_tickers) == 1:
                        _low_val = _low_col.dropna()
                        if not _low_val.empty:
                            intraday_lows[_ct] = round(float(_low_val.iloc[-1]), 2)
    except Exception as _e:
        log(f"Intraday low fetch error (non-fatal): {_e}")

    for p in positions:
        tk = p.get("ticker", "")
        if tk in CRYPTO_SKIP_CRASH or tk == "SPY":
            continue
        current = p.get("current_price", 0) or 0
        morning = morning_prices.get(tk, 0)
        day_low = intraday_lows.get(tk, current)

        if morning > 0 and day_low > 0:
            # Check the WORST point of the day, not just where it is now
            low_change = round((day_low - morning) / morning * 100, 1)
            current_change = round((current - morning) / morning * 100, 1) if current > 0 else 0

            if low_change <= -5:
                recovered = current_change > low_change + 2
                if recovered:
                    log(f"FLASH CRASH DETECTED: {tk} hit {low_change}% intraday low but recovered to {current_change}%")
                    relevant_headlines.append({
                        "headline": f"FLASH CRASH WARNING: {tk} hit {low_change}% intraday low",
                        "summary": f"{tk} dropped from ${morning:.2f} to a low of ${day_low:.2f} ({low_change}%) during today's session but has partially recovered to ${current:.2f} ({current_change}%). The severe intraday wick suggests institutional distribution — a large seller dumped shares. This is a warning sign even though the price recovered.",
                        "matched_ticker": tk, "source": "Price Monitor",
                    })
                else:
                    log(f"CRASH DETECTION: {tk} is DOWN {current_change}% intraday (low: {low_change}%)")
                    relevant_headlines.append({
                        "headline": f"PRICE ALERT: {tk} down {current_change}% intraday (low: {low_change}%)",
                        "summary": f"{tk} dropped from ${morning:.2f} this morning to ${current:.2f} now ({current_change}% decline, intraday low ${day_low:.2f}). May indicate stealth downgrade, sector rotation, or block trade.",
                        "matched_ticker": tk, "source": "Price Monitor",
                    })
    for position in positions:
        position["ticker_news"] = [h for h in relevant_headlines if h.get("matched_ticker") == position["ticker"]]
    macro = fetch_macro_data()

    # Run afternoon industry scan
    industry_results = {}
    if prices and BENCHMARK_ETF in prices:
        industry_results = run_industry_scan(prices, news, macro)
        try:
            layer2 = industry_results.get("layer2", [])
            enriched = enrich_industries_with_events(layer2, news)
            industry_results["layer2"] = enriched
            industry_results["top_industries"] = enriched[:4]
        except Exception as e:
            log(f"Event enrichment error: {e}")

    # Generate afternoon update — ONLY call Claude if urgent news found (saves $0.50-1.00/day)
    update = {"sections": {}}
    if relevant_headlines:
        log(f"Urgent headlines found ({len(relevant_headlines)}) — calling Claude for afternoon update")
        try:
            update = generate_afternoon_update(
                positions=positions,
                industry_results=industry_results,
                news=news,
                morning_top_industries=morning_top,
                today=str(today),
        )
    except Exception as e:
        log(f"Afternoon update error: {e}")

    # New opportunities vs morning
    afternoon_top = industry_results.get("top_industries", [])
    morning_names = {i.get("industry") for i in morning_top}
    new_opps = [
        f"{i['industry']} ({i['etf']}) — Conviction {i['conviction_score']}/100"
        for i in afternoon_top
        if i["industry"] not in morning_names
    ]

    # Run rules engine for afternoon thesis monitoring
    aft_rules_output = {}
    try:
        portfolio_value = sum(p.get("current_price", 0) * p.get("qty", 0) for p in positions)
        cash_balance = portfolio_value * 0.15
        position_reviews = [{"ticker": p.get("ticker", ""), "conviction_score": 50, "thesis_break": False, "thesis_break_reason": ""} for p in positions]
        aft_rules_output = run_rules_engine(
            positions=positions, industry_results=industry_results, macro=macro,
            position_reviews=position_reviews, portfolio_value=portfolio_value, cash_balance=cash_balance,
        )
        log(f"Afternoon rules engine: regime={aft_rules_output.get('regime')} {aft_rules_output.get('regime_score')}/100")
    except Exception as e:
        log(f"Afternoon rules engine error (non-fatal): {e}")

    # Write dashboard data
    try:
        write_dashboard_data(
            macro=macro,
            industry_results=industry_results,
            news_package=news_package,
            positions=positions,
            briefing=update,
            run_type="afternoon",
            today=today,
            cash=0,
            cost_basis=sum(p.get("cost_basis", 0) for p in positions),
            intraday={},
            rules_output=aft_rules_output,
        )
        log("Dashboard data written successfully")
    except Exception as e:
        log(f"Dashboard write error (non-fatal): {e}")

    # Send Telegram (2 messages)
    try:
        # Get notable moves from Claude's output sections
        aft_sections = update.get("sections", {}) if update else {}
        notable_text = aft_sections.get("Notable Price Moves", "") or aft_sections.get("Notable Moves", "")
        notable_moves_parsed = []
        if notable_text:
            for line in notable_text.split("\n"):
                stripped = line.strip().lstrip("- •*").strip()
                if len(stripped) > 10:
                    notable_moves_parsed.append({"ticker": "", "move": "", "reason": stripped})

        build_and_send_afternoon_telegram(
            positions=positions,
            update=update,
            new_opportunities=industry_results.get("top_industries", []),
            notable_moves=notable_moves_parsed,
            today=str(today),
            rules_output=aft_rules_output,
        )
    except Exception as e:
        log(f"Telegram error: {e}")

    elapsed = time.time() - start
    log(f"=== V4 Afternoon Complete: {today} | Runtime: {elapsed:.1f}s ===")


if __name__ == "__main__":
    main()
