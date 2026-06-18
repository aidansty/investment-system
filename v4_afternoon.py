#!/usr/bin/env python3
"""
V4 Investment System — Afternoon Run
Executes at 2:45 PM ET via cron-job.org
Portfolio review and new opportunity detection before market close
"""

import sys
import time
import json
from datetime import date

from v4.utils.logger import log
from v4.utils.market_calendar import is_trading_day, get_trading_date
from v4.utils.telegram import send_telegram, send_afternoon_summary
from v4.data.fetch_prices import fetch_etf_prices
from v4.data.fetch_news import fetch_market_news, fetch_ticker_news
from v4.data.fetch_macro import fetch_macro_data
from v4.intelligence.industry_scanner import run_industry_scan
from v4.intelligence.event_engine import enrich_industries_with_events
from v4.ai.afternoon_update import generate_afternoon_update
from v4.output.notion_writer import (
    get_open_positions, update_position_prices, write_afternoon_update
)
from v4.config.settings import BENCHMARK_ETF


def load_morning_snapshot(today: date) -> list:
    """Load morning top industries for comparison."""
    path = f"data/cache/v4_morning_snapshot_{today.isoformat()}.json"
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        log("No morning snapshot found — skipping comparison")
        return []


def save_morning_snapshot(top_industries: list, today: date) -> None:
    """Save top industries for afternoon comparison."""
    import os
    os.makedirs("data/cache", exist_ok=True)
    path = f"data/cache/v4_morning_snapshot_{today.isoformat()}.json"
    try:
        with open(path, "w") as f:
            json.dump(top_industries, f, indent=2, default=str)
        log(f"Morning snapshot saved: {path}")
    except Exception as e:
        log(f"Snapshot save error: {e}")


def main():
    start = time.time()
    today = get_trading_date()

    log(f"=== V4 Investment System Afternoon Run: {today} ===")

    if not is_trading_day(today):
        log("Market closed today. Exiting.")
        sys.exit(0)

    # Load open positions
    positions = []
    try:
        positions = get_open_positions()
    except Exception as e:
        log(f"Portfolio load error: {e}")

    # Load morning snapshot
    morning_top = load_morning_snapshot(today)

    if not positions and not morning_top:
        log("No positions and no morning snapshot. Minimal run.")

    # Fetch afternoon prices
    log("Fetching afternoon ETF prices...")
    prices = fetch_etf_prices(lookback_days=90)

    # Update position prices
    if positions and prices:
        import yfinance as yf
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
            log(f"Price fetch error: {e}")
        update_position_prices(positions, price_cache)

    # Fetch ticker-specific news for each position
    for position in positions:
        ticker = position["ticker"]
        try:
            position["ticker_news"] = fetch_ticker_news(ticker, days=1)
            log(f"News fetched for {ticker}: {len(position['ticker_news'])} items")
        except Exception as e:
            log(f"News fetch error for {ticker}: {e}")
            position["ticker_news"] = []

    # Afternoon news
    news = fetch_market_news()
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
    update = None
    try:
        update = generate_afternoon_update(
            positions=positions,
            industry_results=industry_results,
            news=news,
            morning_top_industries=morning_top,
            today=str(today),
        )
    except Exception as e:
        log(f"Afternoon update generation error: {e}")

    # Write to Notion
    if update:
        try:
            write_afternoon_update(update=update, positions=positions, today=today)
        except Exception as e:
            log(f"Notion write error: {e}")

    # Send Telegram summary
    try:
        sections = update.get("sections", {}) if update else {}
        portfolio_text = sections.get("Portfolio Review", "")

        position_updates = []
        for p in positions:
            pnl = 0
            entry = p.get("entry_price", 0)
            current = p.get("current_price", 0)
            if entry > 0:
                pnl = ((current - entry) / entry * 100)
            action = "HOLD"
            if pnl < -10:
                action = "REVIEW"
            position_updates.append({
                "ticker": p["ticker"],
                "action": action,
                "reason": f"P&L: {pnl:+.1f}%"
            })

        new_top = industry_results.get("top_industries", [])
        morning_names = {i.get("industry") for i in morning_top}
        new_opps = [
            f"{i['industry']} ({i['etf']}) — Conviction {i['conviction_score']}/100"
            for i in new_top if i["industry"] not in morning_names
        ]

        send_afternoon_summary(
            position_updates=position_updates,
            new_opportunities=new_opps
        )
    except Exception as e:
        log(f"Telegram send error: {e}")

    elapsed = time.time() - start
    log(f"=== V4 Afternoon Run Complete: {today} | Runtime: {elapsed:.1f}s ===")


if __name__ == "__main__":
    main()
