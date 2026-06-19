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
from v4.output.notion_writer import get_open_positions, update_position_prices
from v4.output.telegram_output import build_afternoon_telegram
from v4.config.settings import BENCHMARK_ETF


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

    # Load positions
    positions = []
    try:
        positions = get_open_positions()
    except Exception as e:
        log(f"Portfolio load error: {e}")

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

    # Send Telegram only
    try:
        msg = build_afternoon_telegram(
            positions=positions,
            update_sections=update.get("sections", {}),
            new_opportunities=new_opps,
            today=str(today),
        )
        send_telegram(msg)
        log("Telegram afternoon message sent")
    except Exception as e:
        log(f"Telegram error: {e}")

    elapsed = time.time() - start
    log(f"=== V4 Afternoon Complete: {today} | Runtime: {elapsed:.1f}s ===")


if __name__ == "__main__":
    main()
