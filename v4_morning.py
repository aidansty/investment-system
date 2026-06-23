#!/usr/bin/env python3
"""
V4 Investment System — Morning Run
Executes at 8:45 AM ET via cron-job.org
Delivers concise briefing to Telegram only.
Full analysis available on web dashboard (Phase 4).
"""

import sys
import time
import json
import os
import yfinance as yf

from v4.utils.logger import log
from v4.utils.market_calendar import is_trading_day, get_trading_date
from v4.utils.telegram import send_telegram
from v4.data.fetch_prices import fetch_etf_prices
from v4.data.fetch_news import fetch_complete_news_package
from v4.data.fetch_macro import fetch_macro_data
from v4.intelligence.industry_scanner import run_industry_scan
from v4.intelligence.event_engine import enrich_industries_with_events
from v4.ai.morning_briefing import generate_morning_briefing
from v4.output.notion_writer import get_open_positions, update_position_prices
from v4.output.telegram_output import build_and_send_morning_telegram
from v4.config.settings import BENCHMARK_ETF


def save_morning_snapshot(top_industries: list, today) -> None:
    os.makedirs("data/cache", exist_ok=True)
    path = f"data/cache/v4_morning_snapshot_{today}.json"
    try:
        with open(path, "w") as f:
            json.dump(top_industries, f, indent=2, default=str)
        log(f"Morning snapshot saved: {path}")
    except Exception as e:
        log(f"Snapshot save error: {e}")


def main():
    start = time.time()
    today = get_trading_date()
    log(f"=== V4 Morning Run: {today} ===")

    if not is_trading_day(today):
        log("Market closed. Exiting.")
        send_telegram(f"📅 {today} — Market closed today. No briefing to generate. See you next trading day.")
        sys.exit(0)

    # Step 1 — ETF prices
    log("Fetching ETF prices...")
    prices = fetch_etf_prices(lookback_days=90)
    if not prices or BENCHMARK_ETF not in prices:
        send_telegram("⚠️ V4 Morning Run FAILED — ETF price fetch error.")
        sys.exit(1)

    # Step 2 — Macro
    log("Fetching macro data...")
    macro = fetch_macro_data()

    # Step 3 — News (recent + forward catalysts)
    log("Fetching complete news package...")
    news_package = fetch_complete_news_package()
    news = news_package.get("recent_news", [])
    forward_catalysts = news_package.get("forward_catalysts", [])

    # Step 4 — Open positions and update prices
    log("Loading positions...")
    positions = []
    try:
        positions = get_open_positions()
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
                log(f"Position price error: {e}")
            update_position_prices(positions, price_cache)
    except Exception as e:
        log(f"Portfolio load error: {e}")

    # Step 5 — Industry scan
    log("Running industry scan...")
    industry_results = run_industry_scan(prices, news, macro)

    # Step 6 — Event enrichment
    log("Enriching with events...")
    try:
        layer2 = industry_results.get("layer2", [])
        enriched = enrich_industries_with_events(layer2, news)
        industry_results["layer2"] = enriched
        industry_results["top_industries"] = enriched[:4]
        industry_results["high_conviction"] = [
            i for i in enriched if i["conviction_score"] >= 70
        ]
    except Exception as e:
        log(f"Event enrichment error: {e}")

    # Step 7 — Generate briefing via Claude
    log("Generating briefing...")
    briefing = {"sections": {}}
    try:
        briefing = generate_morning_briefing(
            macro=macro,
            industry_results=industry_results,
            news=news,
            forward_catalysts=forward_catalysts,
            positions=positions,
            today=str(today),
        )
    except Exception as e:
        log(f"Briefing generation error: {e}")

    # Step 8 — Save morning snapshot for afternoon comparison
    save_morning_snapshot(industry_results.get("top_industries", []), today)

    # Step 9 — Send Telegram (2 messages)
    try:
        build_and_send_morning_telegram(
            macro=macro,
            industry_results=industry_results,
            news_package=news_package,
            positions=positions,
            briefing=briefing,
            forward_catalysts=forward_catalysts,
            today=str(today),
        )
    except Exception as e:
        log(f"Telegram error: {e}")
        send_telegram(f"⚠️ V4 briefing error: {str(e)[:200]}")

    elapsed = time.time() - start
    log(f"=== V4 Morning Complete: {today} | Runtime: {elapsed:.1f}s ===")


if __name__ == "__main__":
    main()
