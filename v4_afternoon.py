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
from v4.data.fetch_news import fetch_complete_news_package, fetch_ticker_news
from v4.data.fetch_macro import fetch_macro_data
from v4.intelligence.industry_scanner import run_industry_scan
from v4.intelligence.event_engine import enrich_industries_with_events
from v4.ai.afternoon_update import generate_afternoon_update
from v4.output.telegram_output import build_and_send_afternoon_telegram
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

    # Fetch ticker-specific news for each position
    for position in positions:
        ticker = position["ticker"]
        try:
            position["ticker_news"] = fetch_ticker_news(ticker, days=1)
        except Exception as e:
            position["ticker_news"] = []

    # Afternoon news and macro
    news_package = fetch_complete_news_package()
    news = news_package.get("recent_news", [])
    forward_catalysts = news_package.get("forward_catalysts", [])
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

    # Generate afternoon update
    update = {"sections": {}}
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
        )
        log("Dashboard data written successfully")
    except Exception as e:
        log(f"Dashboard write error (non-fatal): {e}")

    # Send Telegram (2 messages)
    try:
        build_and_send_afternoon_telegram(
            positions=positions,
            update=update,
            new_opportunities=[industry_results.get("top_industries", [])],
            notable_moves=[],
            today=str(today),
        )
    except Exception as e:
        log(f"Telegram error: {e}")

    elapsed = time.time() - start
    log(f"=== V4 Afternoon Complete: {today} | Runtime: {elapsed:.1f}s ===")


if __name__ == "__main__":
    main()
