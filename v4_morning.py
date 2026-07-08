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
from v4.data.fetch_prices import fetch_etf_prices, fetch_stock_prices
from v4.data.fetch_news import fetch_complete_news_package
from v4.data.fetch_macro import fetch_macro_data, fetch_earnings_calendar, fetch_recent_earnings_results
from v4.intelligence.industry_scanner import run_industry_scan
from v4.intelligence.event_engine import enrich_industries_with_events
from v4.ai.morning_briefing import generate_morning_briefing
from v4.output.telegram_output import build_and_send_morning_telegram
from v4.output.dashboard_writer import write_dashboard_data
from v4.data.fetch_intraday import fetch_intraday_candles
from v4.config.settings import BENCHMARK_ETF
from v4.intelligence.rules_engine import run_rules_engine
from v4.intelligence.win_tracker import log_recommendation


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
    from v4.config.settings import ALL_STOCKS
    try:
        stock_prices = fetch_stock_prices(tickers=ALL_STOCKS, lookback_days=90)
        log(f"Stock prices fetched: {len(stock_prices)} tickers")
    except Exception as e:
        log(f"Stock price fetch error (non-fatal): {e}")
        stock_prices = {}
    prices = {**prices, **stock_prices}
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
            # Stock prices via yfinance
            stock_tickers = [t for t in tickers if t not in {"BTC","ETH","XRP","ZEC"}]
            try:
                data = yf.download(stock_tickers, period="2d", auto_adjust=True, progress=False)
                close = data["Close"] if "Close" in data.columns else data
                for ticker in stock_tickers:
                    if ticker in close.columns:
                        series = close[ticker].dropna()
                        if not series.empty:
                            price_cache[ticker] = round(float(series.iloc[-1]), 2)
            except Exception as e:
                log(f"Position price error: {e}")
            # Crypto prices via Coinbase — yfinance crypto is unreliable
            import requests as _req
            coinbase_map = {"BTC": "BTC-USD", "ETH": "ETH-USD", "XRP": "XRP-USD", "ZEC": "ZEC-USD"}
            for ct, pair in coinbase_map.items():
                if ct in tickers:
                    try:
                        r = _req.get(f"https://api.coinbase.com/v2/prices/{pair}/spot", timeout=5)
                        if r.status_code == 200:
                            price_cache[ct] = round(float(r.json()["data"]["amount"]), 2)
                            log(f"Coinbase {ct}: ${price_cache[ct]:,.2f}")
                    except Exception as e:
                        log(f"Coinbase price error for {ct}: {e}")
            update_position_prices(positions, price_cache)
    except Exception as e:
        log(f"Portfolio load error: {e}")

    # Step 4a — Confirmed earnings dates from Finnhub
    log("Fetching confirmed earnings dates...")
    earnings_calendar = {}
    recent_earnings_results = {}
    try:
        tickers = [p["ticker"] for p in positions]
        earnings_calendar = fetch_earnings_calendar(tickers)
        log(f"Earnings calendar: {earnings_calendar}")
        recent_earnings_results = fetch_recent_earnings_results(tickers, lookback_days=14)
        log(f"Recent earnings results (last 14 days): {recent_earnings_results}")
    except Exception as e:
        log(f"Earnings calendar error (non-fatal): {e}")

    # Step 4b — Intraday candles for stock charts
    log("Fetching intraday candles...")
    intraday_data = {}
    try:
        intraday_data = fetch_intraday_candles(positions)
    except Exception as e:
        log(f"Intraday fetch error (non-fatal): {e}")

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

        # Re-apply Layer 2 stock-leader scoring to the final top_industries —
        # event enrichment replaced the objects that already had this data.
        from v4.intelligence.industry_scanner import score_stock_leaders
        from v4.config.settings import INDUSTRY_STOCK_LEADERS
        spy_prices_for_l2 = prices.get("SPY", [])
        log(f"DEBUG Layer 2: spy_prices length={len(spy_prices_for_l2)}, total tickers in prices dict={len(prices)}")
        for ind in industry_results["top_industries"]:
            industry_name = ind.get("industry", "")
            expected_stocks = INDUSTRY_STOCK_LEADERS.get(industry_name, [])
            stocks_with_data = [t for t in expected_stocks if t in prices and len(prices.get(t, [])) >= 63]
            log(f"DEBUG Layer 2: {industry_name} expects {len(expected_stocks)} stocks, {len(stocks_with_data)} have >=63 days of price data: {stocks_with_data[:5]}")
            stock_scores = score_stock_leaders(prices, industry_name, spy_prices_for_l2)
            log(f"DEBUG Layer 2: {industry_name} scored {len(stock_scores)} stocks")
            ind["stock_leaders"] = stock_scores[:3]
            etf_conv = ind.get("conviction_score", 0)
            if stock_scores and stock_scores[0]["conviction"] > etf_conv + 5:
                ind["recommended_security"] = stock_scores[0]["ticker"]
                ind["recommended_type"] = "stock"
                ind["recommended_conviction"] = stock_scores[0]["conviction"]
            else:
                ind["recommended_security"] = ind.get("etf", "")
                ind["recommended_type"] = "etf"
                ind["recommended_conviction"] = etf_conv
        log(f"Re-applied Layer 2 stock scoring to {len(industry_results['top_industries'])} final top industries")
    except Exception as e:
        log(f"Event enrichment error: {e}")

    # Step 6b — Catalyst Scanner (forward-looking, 30-day window)
    log("Running catalyst scanner...")
    catalyst_opportunities = []
    try:
        from v4.config.settings import ALL_STOCKS, INDUSTRY_STOCK_LEADERS, INDUSTRY_ETF_MAP
        from datetime import datetime, timedelta
        import pytz

        eastern = pytz.timezone("America/New_York")
        today_dt = datetime.now(eastern).date()
        thirty_days = today_dt + timedelta(days=30)

        stocks_with_momentum = []
        spy_prices_cat = prices.get("SPY", [])
        if len(spy_prices_cat) >= 21:
            spy_21d = (spy_prices_cat[-1] / spy_prices_cat[-21] - 1) * 100 if spy_prices_cat[-21] > 0 else 0
            for ticker, price_list in prices.items():
                if ticker == "SPY" or len(price_list) < 21:
                    continue
                stk_21d = (price_list[-1] / price_list[-21] - 1) * 100 if price_list[-21] > 0 else 0
                excess_21d = stk_21d - spy_21d
                if excess_21d > 3:
                    stocks_with_momentum.append({
                        "ticker": ticker,
                        "excess_21d": round(excess_21d, 1),
                        "price": round(price_list[-1], 2),
                    })

        stocks_with_momentum.sort(key=lambda x: x["excess_21d"], reverse=True)
        top_momentum = stocks_with_momentum[:30]
        log(f"Catalyst scanner: {len(stocks_with_momentum)} stocks with 21d momentum > SPY+3pp, scanning top {len(top_momentum)}")

        import requests, os
        FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
        catalyst_earnings = dict(earnings_calendar or {})
        momentum_tickers_to_scan = [s["ticker"] for s in top_momentum if s["ticker"] not in catalyst_earnings]

        for ticker in momentum_tickers_to_scan[:15]:
            try:
                url = f"https://finnhub.io/api/v1/calendar/earnings?symbol={ticker}&from={today_dt.strftime('%Y-%m-%d')}&to={thirty_days.strftime('%Y-%m-%d')}&token={FINNHUB_KEY}"
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    el = data.get("earningsCalendar", [])
                    if el:
                        catalyst_earnings[ticker] = {
                            "date": el[0].get("date", ""),
                            "hour": el[0].get("hour", ""),
                            "eps_estimate": el[0].get("epsEstimate"),
                        }
            except Exception:
                continue

        for s in top_momentum:
            tk = s["ticker"]
            if tk in catalyst_earnings:
                earn = catalyst_earnings[tk]
                earn_date = earn.get("date", "")
                if earn_date:
                    stock_industry = ""
                    for ind_name, tickers in INDUSTRY_STOCK_LEADERS.items():
                        if tk in tickers:
                            stock_industry = ind_name
                            break

                    ticker_news = []
                    for n in news:
                        affected = n.get("affected_tickers", [])
                        if isinstance(affected, list) and tk in affected:
                            ticker_news.append(n.get("headline", ""))
                        elif tk in n.get("headline", "").upper():
                            ticker_news.append(n.get("headline", ""))

                    catalyst_opportunities.append({
                        "ticker": tk,
                        "industry": stock_industry,
                        "earnings_date": earn_date,
                        "eps_estimate": earn.get("eps_estimate"),
                        "excess_21d": s["excess_21d"],
                        "price": s["price"],
                        "has_news": len(ticker_news) > 0,
                        "news_headlines": ticker_news[:2],
                        "catalyst_type": "earnings",
                        "days_until": (datetime.strptime(earn_date, "%Y-%m-%d").date() - today_dt).days if earn_date else 99,
                    })

        catalyst_opportunities.sort(key=lambda x: (-x["excess_21d"], x["days_until"]))
        catalyst_opportunities = catalyst_opportunities[:5]
        log(f"Catalyst scanner: {len(catalyst_opportunities)} stocks with momentum + upcoming earnings in 30 days")
        for c in catalyst_opportunities:
            log(f"  {c['ticker']}: earnings {c['earnings_date']} ({c['days_until']}d away), 21d excess +{c['excess_21d']}pp" + (f", news: {c['news_headlines'][0][:60]}" if c['news_headlines'] else ""))
    except Exception as e:
        log(f"Catalyst scanner error (non-fatal): {e}")
        import traceback
        traceback.print_exc()

    # Step 7 — Run rules engine FIRST (briefing needs its output)
    log("Running rules engine...")
    rules_output = {}
    try:
        portfolio_value = sum(p.get("current_price", 0) * p.get("qty", 0) for p in positions)
        cash_balance = portfolio_value * 0.15
        position_reviews = [{"ticker": p.get("ticker", ""), "conviction_score": 50, "thesis_break": False, "thesis_break_reason": ""} for p in positions]
        rules_output = run_rules_engine(
            positions=positions, industry_results=industry_results, macro=macro,
            position_reviews=position_reviews, portfolio_value=portfolio_value, cash_balance=cash_balance,
        )
        exits = rules_output.get("summary", {}).get("exits_triggered", [])
        entries = rules_output.get("summary", {}).get("entries_available", [])
        log(f"Rules engine: regime={rules_output.get('regime')} {rules_output.get('regime_score')}/100, {len(exits)} exits, {len(entries)} entries")

        # Log all entry signals to win tracker with component scores
        regime_score = rules_output.get("regime_score", 0)
        for sig in entries:
            try:
                log_recommendation(
                    ticker=sig.get("ticker", ""),
                    action=sig.get("action", "enter"),
                    price_at_recommendation=0,
                    reason=sig.get("reason", ""),
                    conviction_score=sig.get("conviction", 0),
                    run_type="morning",
                    regime_score=regime_score,
                    has_catalyst=sig.get("entry_type") == "full",
                    entry_type=sig.get("entry_type", "full"),
                )
                log(f"Win tracker logged: {sig.get('ticker')} entry")
            except Exception as e:
                log(f"Win tracker log error: {e}")

        for sig in exits:
            try:
                log_recommendation(
                    ticker=sig.get("ticker", ""),
                    action="exit",
                    price_at_recommendation=0,
                    reason=sig.get("reason", ""),
                    conviction_score=sig.get("conviction", 0),
                    run_type="morning",
                    regime_score=regime_score,
                    exit_reason_category=sig.get("exit_type", ""),
                )
                log(f"Win tracker logged: {sig.get('ticker')} exit")
            except Exception as e:
                log(f"Win tracker log error: {e}")
    except Exception as e:
        log(f"Rules engine error (non-fatal): {e}")

    # Step 8 — Generate briefing via Claude (rules_output now available)
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
            earnings_calendar=earnings_calendar,
            rules_output=rules_output,
            recent_earnings_results=recent_earnings_results,
            catalyst_opportunities=catalyst_opportunities,
        )
    except Exception as e:
        log(f"Briefing generation error: {e}")

    # Step 8b — Save morning snapshot for afternoon comparison
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
            rules_output=rules_output,
        )
    except Exception as e:
        log(f"Telegram error: {e}")
        send_telegram(f"⚠️ V4 briefing error: {str(e)[:200]}")

    # Step 10 — Write dashboard data
    log("Writing dashboard data...")
    try:
        cost_basis = sum(p.get("cost_basis", 0) for p in positions)
        write_dashboard_data(
            macro=macro,
            industry_results=industry_results,
            news_package=news_package,
            positions=positions,
            briefing=briefing,
            run_type="morning",
            today=str(today),
            cost_basis=cost_basis,
            intraday=intraday_data,
            rules_output=rules_output,
            catalyst_opportunities=catalyst_opportunities,
        )
        log("Dashboard data written successfully.")
    except Exception as e:
        log(f"Dashboard write error: {e}")

    elapsed = time.time() - start
    log(f"=== V4 Morning Complete: {today} | Runtime: {elapsed:.1f}s ===")


if __name__ == "__main__":
    main()
