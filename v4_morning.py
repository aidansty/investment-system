#!/usr/bin/env python3
"""
V4 Investment System — Morning Run
Executes at 8:45 AM ET via cron-job.org
Delivers briefing to Notion and Telegram before 9:20 AM
"""

import sys
import time
from datetime import datetime
import pytz

from v4.utils.logger import log
from v4.utils.market_calendar import is_trading_day, get_trading_date
from v4.utils.telegram import send_telegram, send_morning_summary
from v4.data.fetch_prices import fetch_etf_prices, fetch_current_etf_prices
from v4.data.fetch_news import fetch_market_news
from v4.data.fetch_macro import fetch_macro_data
from v4.intelligence.industry_scanner import run_industry_scan
from v4.intelligence.event_engine import enrich_industries_with_events
from v4.ai.morning_briefing import generate_morning_briefing, build_telegram_morning_summary
from v4.output.notion_writer import (
    get_open_positions, update_position_prices, write_morning_briefing
)
from v4.config.settings import ALL_INDUSTRY_ETFS, BENCHMARK_ETF


def main():
    start = time.time()
    eastern = pytz.timezone("America/New_York")
    today = get_trading_date()

    log(f"=== V4 Investment System Morning Run: {today} ===")

    # Market calendar check
    if not is_trading_day(today):
        log("Market closed today. Exiting.")
        sys.exit(0)

    # Step 1 — Fetch ETF prices (all 25 industries + SPY)
    log("Step 1: Fetching ETF prices...")
    prices = fetch_etf_prices(lookback_days=90)
    if not prices or BENCHMARK_ETF not in prices:
        log("CRITICAL: ETF price fetch failed. Cannot continue.")
        send_telegram("⚠️ V4 Morning Run FAILED — ETF price fetch error. Check system.")
        sys.exit(1)

    # Step 2 — Fetch macro data
    log("Step 2: Fetching macro data...")
    macro = fetch_macro_data()

    # Step 3 — Fetch news
    log("Step 3: Fetching market news...")
    news = fetch_market_news()

    # Step 4 — Load open positions and update prices
    log("Step 4: Loading open positions...")
    positions = []
    try:
        positions = get_open_positions()
        if positions:
            tickers = [p["ticker"] for p in positions]
            from v4.data.fetch_prices import fetch_current_etf_prices
            import yfinance as yf
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
                log(f"Position price fetch error: {e}")
            update_position_prices(positions, price_cache)
    except Exception as e:
        log(f"Portfolio load error (non-fatal): {e}")

    # Step 5 — Run industry intelligence scan
    log("Step 5: Running industry intelligence scan...")
    industry_results = run_industry_scan(prices, news, macro)

    # Step 6 — Enrich with event intelligence
    log("Step 6: Enriching with event intelligence...")
    try:
        layer2 = industry_results.get("layer2", [])
        enriched_layer2 = enrich_industries_with_events(layer2, news)
        industry_results["layer2"] = enriched_layer2
        industry_results["top_industries"] = enriched_layer2[:4]
        industry_results["high_conviction"] = [
            i for i in enriched_layer2 if i["conviction_score"] >= 70
        ]
    except Exception as e:
        log(f"Event enrichment error (non-fatal): {e}")

    # Step 7 — Generate morning briefing via Claude
    log("Step 7: Generating morning briefing...")
    briefing = None
    try:
        briefing = generate_morning_briefing(
            macro=macro,
            industry_results=industry_results,
            news=news,
            positions=positions,
            today=str(today),
        )
    except Exception as e:
        log(f"CRITICAL: Briefing generation failed: {e}")
        send_telegram(f"⚠️ V4 Morning Briefing FAILED — Claude error: {str(e)[:200]}")

    # Step 8 — Write to Notion
    if briefing:
        try:
            notion_url = write_morning_briefing(
                briefing=briefing,
                industry_results=industry_results,
                macro=macro,
                positions=positions,
                today=today,
            )
            if notion_url:
                log(f"Notion briefing: {notion_url}")
        except Exception as e:
            log(f"Notion write error (non-fatal): {e}")

    # Step 9 — Send Telegram summary
    try:
        telegram_msg = build_telegram_morning_summary(
            briefing=briefing or {},
            industry_results=industry_results,
            macro=macro,
            positions=positions,
        )
        send_telegram(telegram_msg)
    except Exception as e:
        log(f"Telegram send error (non-fatal): {e}")

    elapsed = time.time() - start
    log(f"=== V4 Morning Run Complete: {today} | Runtime: {elapsed:.1f}s ===")

    top = industry_results.get("top_industries", [])
    if top:
        log(f"Top industry: {top[0]['industry']} | Conviction: {top[0]['conviction_score']}/100")


if __name__ == "__main__":
    main()
