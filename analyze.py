import sys
import time
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


def main():
    start = time.time()
    today = date.today()
    log(f"=== Investment System starting: {today} ===")

    # Step 1: Market calendar check
    if not is_trading_day(today):
        log("Market closed today. Exiting cleanly.")
        sys.exit(0)

    # Step 2: Load universe
    universe = get_universe()
    log(f"Universe loaded: {len(universe)} tickers")

    # Step 3: Fetch macro data
    macro = fetch_macro_data()
    if macro is None:
        log("ERROR: Macro data fetch failed. Cannot continue.")
        sys.exit(1)

    # Step 4: Fetch universe prices
    log("Fetching universe prices...")
    prices = fetch_all_prices(universe)
    if prices is None:
        log("ERROR: Price fetch failed coverage threshold. Cannot continue.")
        sys.exit(1)

    # Step 5: Calculate breadth and add to macro
    breadth = calculate_breadth(prices)
    macro["breadth_pct"] = breadth

    # Step 6: Determine regime
    regime = determine_regime(macro)

    # Step 7: Portfolio always runs first — protects existing risk
    # Uses price cache to avoid redundant API calls
    positions = []
    try:
        positions = get_open_positions(price_cache=prices)
        if positions:
            update_position_prices(positions)
    except Exception as e:
        log(f"CRITICAL PORTFOLIO EXCEPTION: Risk tracking impaired: {e}")

    # Step 8: Scanning runs second — safely wrapped
    scan_results = {"strong": [], "developing": [], "watch": [], "scan_stats": {}}
    try:
        rs_scores = calculate_relative_strength(prices)
        rs_qualified = get_rs_qualified(rs_scores)
        trend_qualified = apply_trend_filter(prices, rs_qualified)
        log(f"Technical filter: {len(trend_qualified)} qualified tickers")

        fundamentals = fetch_fundamentals_batch(trend_qualified)

        # Fundamentals coverage check — abort if API is down
        coverage = len(fundamentals) / max(len(trend_qualified), 1)
        if coverage < 0.5:
            log(f"CRITICAL ERROR: Fundamentals coverage only {coverage:.0%}. "
                f"Possible Finnhub outage. Aborting scan.")
            sys.exit(1)

        scan_results = run_full_scan(prices, fundamentals, regime)

    except SystemExit:
        raise
    except Exception as e:
        log(f"SCANNER EXCEPTION: {e}")

    # Step 9: Fetch news
    news = fetch_market_news()

    # Step 10: Generate Claude briefing
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

    # Step 11: Write briefing to Notion
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

    # Step 12: Write candidates to Notion as one daily page
    try:
        write_trade_candidates(scan_results, regime, today)
    except Exception as e:
        log(f"ERROR: Could not write trade candidates to Notion: {e}")

    elapsed = time.time() - start
    log(f"=== Daily briefing complete: {today} | Runtime: {elapsed:.1f}s ===")


if __name__ == "__main__":
    main()
