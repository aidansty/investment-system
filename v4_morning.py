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
        stock_result = fetch_stock_prices(tickers=ALL_STOCKS, lookback_days=90)
        if isinstance(stock_result, tuple):
            stock_prices, volume_data = stock_result
        else:
            stock_prices, volume_data = stock_result, {}
        log(f"Stock prices fetched: {len(stock_prices)} tickers, volume data for {len(volume_data)} tickers")
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

                    # Only include if the catalyst is genuinely significant
                    # Earnings are inherently significant (can move stocks 5-15%)
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
                        "significance": "high",
                    })

        # PHASE 2: Non-earnings catalysts from forward_catalysts and enriched news
        # These cover: FDA decisions, index inclusions, product launches, M&A,
        # contract wins, analyst upgrades, share buybacks, guidance raises,
        # conference presentations, regulatory decisions, partnerships — everything
        # that moves stock prices beyond just earnings.
        try:
            for fc in (forward_catalysts or []):
                affected = fc.get("affected_holdings", []) or fc.get("tickers", [])
                if not isinstance(affected, list):
                    affected = []
                fc_date = fc.get("date", "") or fc.get("event_date", "")
                fc_event = fc.get("event", "") or fc.get("description", "")
                fc_action = fc.get("action", "")

                for tk in affected:
                    # Check if this ticker has momentum data
                    tk_momentum = None
                    for s in stocks_with_momentum:
                        if s["ticker"] == tk:
                            tk_momentum = s
                            break

                    # Skip if already in catalyst_opportunities from earnings scan
                    already_listed = any(c["ticker"] == tk for c in catalyst_opportunities)
                    if already_listed:
                        continue

                    if tk_momentum:
                        stock_industry = ""
                        for ind_name, tickers in INDUSTRY_STOCK_LEADERS.items():
                            if tk in tickers:
                                stock_industry = ind_name
                                break

                        days_until = 30
                        if fc_date:
                            try:
                                fc_dt = datetime.strptime(fc_date, "%Y-%m-%d").date()
                                days_until = (fc_dt - today_dt).days
                            except Exception:
                                pass

                        if 0 <= days_until <= 45:
                            catalyst_opportunities.append({
                                "ticker": tk,
                                "industry": stock_industry,
                                "earnings_date": fc_date,
                                "eps_estimate": None,
                                "excess_21d": tk_momentum["excess_21d"],
                                "price": tk_momentum["price"],
                                "has_news": True,
                                "news_headlines": [fc_event[:100]],
                                "catalyst_type": fc_action or "event",
                                "days_until": days_until,
                            })

            # PHASE 3: News-driven catalysts — positive sentiment news affecting
            # stocks with momentum, even without a specific future date
            for n_item in (news or []):
                sentiment = (n_item.get("sentiment", "") or "").lower()
                if sentiment != "bullish":
                    continue
                affected = n_item.get("affected_tickers", [])
                if not isinstance(affected, list):
                    continue
                for tk in affected:
                    already_listed = any(c["ticker"] == tk for c in catalyst_opportunities)
                    if already_listed:
                        continue
                    tk_momentum = None
                    for s in stocks_with_momentum:
                        if s["ticker"] == tk:
                            tk_momentum = s
                            break
                    if tk_momentum and tk_momentum["excess_21d"] > 5:
                        stock_industry = ""
                        for ind_name, tickers in INDUSTRY_STOCK_LEADERS.items():
                            if tk in tickers:
                                stock_industry = ind_name
                                break
                        # Only include if the news is genuinely significant (not minor analyst notes)
                        news_headline_upper = n_item.get("headline", "").upper()
                        noise_words = ["PRICE TARGET", "MAINTAINS", "REITERATES", "INITIATES", "MINOR", "SLIGHT", "MODEST"]
                        sig_words = ["EARNINGS", "FDA", "APPROV", "ACQUI", "MERGER", "CONTRACT", "LAUNCH", "UPGRADE",
                                     "DOWNGRADE", "RECORD", "BEAT", "MISS", "GUIDANCE", "SPLIT", "BUYBACK", "INDEX"]
                        is_sig_news = any(sw in news_headline_upper for sw in sig_words) and not any(nw in news_headline_upper for nw in noise_words)
                        if is_sig_news:
                            catalyst_opportunities.append({
                                "ticker": tk,
                                "industry": stock_industry,
                                "earnings_date": "",
                                "eps_estimate": None,
                                "excess_21d": tk_momentum["excess_21d"],
                                "price": tk_momentum["price"],
                                "has_news": True,
                                "news_headlines": [n_item.get("headline", "")[:100]],
                                "catalyst_type": n_item.get("category", "news"),
                                "days_until": 0,
                                "significance": "high",
                            })
        except Exception as e:
            log(f"Catalyst scanner phase 2/3 error (non-fatal): {e}")

        # PHASE 4: POST-CATALYST CONFIRMATION (replaces pre-catalyst guessing)
        # Find stocks where a catalyst ALREADY happened and CONFIRMED with:
        # - Day-1 return > 4% (catalyst delivered)
        # - RVOL > 2.5x for mega-caps or > 1.5x for mid/small-caps
        # This captures 2-3 week post-catalyst drift with high probability.
        try:
            vol_data = volume_data if "volume_data" in dir() else {}
            for ticker, price_list in prices.items():
                if ticker == "SPY" or len(price_list) < 5:
                    continue
                already_listed = any(c["ticker"] == ticker for c in catalyst_opportunities)
                if already_listed:
                    continue
                day1_return = (price_list[-1] / price_list[-2] - 1) * 100 if price_list[-2] > 0 else 0
                if day1_return < 4.0:
                    continue
                tk_vol = vol_data.get(ticker, {})
                rvol = tk_vol.get("rvol", 0)
                avg_vol = tk_vol.get("avg_50d", 0)
                is_mega_cap = avg_vol > 10_000_000
                required_rvol = 2.5 if is_mega_cap else 1.5
                if rvol < required_rvol and avg_vol > 0:
                    continue
                if 0 < avg_vol < 500_000:
                    continue
                tk_excess = 0
                if len(price_list) >= 21 and len(spy_prices_cat) >= 21:
                    stk_21d = (price_list[-1] / price_list[-21] - 1) * 100 if price_list[-21] > 0 else 0
                    tk_excess = round(stk_21d - spy_21d, 1)
                stock_industry = ""
                for ind_name, tickers_list in INDUSTRY_STOCK_LEADERS.items():
                    if ticker in tickers_list:
                        stock_industry = ind_name
                        break
                ticker_news = []
                for n in news:
                    affected = n.get("affected_tickers", [])
                    if isinstance(affected, list) and ticker in affected:
                        ticker_news.append(n.get("headline", ""))
                    elif ticker in n.get("headline", "").upper():
                        ticker_news.append(n.get("headline", ""))
                cap_label = "mega-cap" if is_mega_cap else "mid/small-cap"
                catalyst_opportunities.append({
                    "ticker": ticker, "industry": stock_industry, "earnings_date": "",
                    "eps_estimate": None, "excess_21d": tk_excess,
                    "price": round(price_list[-1], 2), "has_news": len(ticker_news) > 0,
                    "news_headlines": ticker_news[:2], "catalyst_type": "post-catalyst-confirmed",
                    "days_until": 0, "day1_return": round(day1_return, 1),
                    "rvol": rvol, "significance": "high",
                })
                log(f"  POST-CATALYST: {ticker} ({cap_label}) Day-1: +{day1_return:.1f}%, RVOL: {rvol:.1f}x" + (f", news: {ticker_news[0][:50]}" if ticker_news else ""))
        except Exception as e:
            log(f"Catalyst scanner phase 4 error (non-fatal): {e}")

        # PHASE 5: Strong catalyst, no momentum required
        # Stocks with confirmed Tier 1 catalysts (FDA, major earnings, index inclusion,
        # M&A, major contract) get evaluated even without existing momentum.
        # The catalyst alone can be the reason to enter.
        try:
            tier1_keywords = ["EARNINGS", "FDA", "PDUFA", "APPROV", "INDEX", "INCLUSION",
                "REBALANCE", "ACQUISITION", "MERGER", "BUYOUT", "CONTRACT WIN",
                "STOCK SPLIT", "BUYBACK", "RECORD REVENUE", "GUIDANCE RAISE"]
            for fc in (forward_catalysts or []):
                affected = fc.get("affected_holdings", []) or fc.get("tickers", [])
                if not isinstance(affected, list):
                    affected = []
                fc_event = fc.get("event", "") or fc.get("description", "")
                fc_date = fc.get("date", "") or fc.get("event_date", "")

                is_tier1 = any(kw in fc_event.upper() for kw in tier1_keywords)
                if not is_tier1:
                    continue

                days_until = 99
                if fc_date:
                    try:
                        fc_dt = datetime.strptime(fc_date, "%Y-%m-%d").date()
                        days_until = (fc_dt - today_dt).days
                    except Exception:
                        continue
                if days_until < 0 or days_until > 30:
                    continue

                for tk in affected:
                    already_listed = any(c["ticker"] == tk for c in catalyst_opportunities)
                    if already_listed:
                        continue

                    # Get price if available — momentum NOT required
                    tk_price = 0
                    tk_excess = 0
                    if tk in prices and len(prices[tk]) >= 2:
                        tk_price = round(prices[tk][-1], 2)
                        if len(prices[tk]) >= 21 and len(spy_prices_cat) >= 21:
                            stk_21d = (prices[tk][-1] / prices[tk][-21] - 1) * 100 if prices[tk][-21] > 0 else 0
                            tk_excess = round(stk_21d - spy_21d, 1)

                    # Filter out micro-caps using volume data
                    vol_info = volume_data.get(tk, {}) if "volume_data" in dir() else {}
                    avg_vol = vol_info.get("avg_50d", 0)
                    if 0 < avg_vol < 500_000:
                        continue

                    stock_industry = ""
                    for ind_name, tickers_list in INDUSTRY_STOCK_LEADERS.items():
                        if tk in tickers_list:
                            stock_industry = ind_name
                            break

                    catalyst_opportunities.append({
                        "ticker": tk,
                        "industry": stock_industry,
                        "earnings_date": fc_date,
                        "eps_estimate": None,
                        "excess_21d": tk_excess,
                        "price": tk_price,
                        "has_news": True,
                        "news_headlines": [fc_event[:100]],
                        "catalyst_type": "strong-catalyst-reduced",
                        "days_until": days_until,
                        "significance": "high",
                        "reduced_sizing": True,
                    })
                    log(f"  STRONG CATALYST (reduced sizing): {tk} — {fc_event[:60]} in {days_until} days")
        except Exception as e:
            log(f"Catalyst scanner phase 5 error (non-fatal): {e}")

        # Tag high-volatility stocks (avg daily range > 4% of price)
        # These get half position size + double stop distance (same dollar risk)
        for c in catalyst_opportunities:
            tk = c.get("ticker", "")
            if tk in prices and len(prices[tk]) >= 20:
                price_list = prices[tk]
                # Calculate average daily range as % of price over last 20 days
                daily_ranges = []
                for i in range(-20, -1):
                    if price_list[i] > 0:
                        day_range = abs(price_list[i] - price_list[i-1]) / price_list[i] * 100
                        daily_ranges.append(day_range)
                if daily_ranges:
                    avg_range = sum(daily_ranges) / len(daily_ranges)
                    c["avg_daily_range"] = round(avg_range, 2)
                    c["high_volatility"] = avg_range > 4.0
                    if c["high_volatility"]:
                        log(f"  HIGH-VOL: {tk} avg daily range {avg_range:.1f}% — half size, wider stop")

        # Tag high-volatility stocks (avg daily range > 4%)
        for c in catalyst_opportunities:
            tk = c.get("ticker", "")
            if tk in prices and len(prices[tk]) >= 20:
                price_list = prices[tk]
                daily_ranges = []
                for i in range(-20, -1):
                    if price_list[i] > 0:
                        day_range = abs(price_list[i] - price_list[i-1]) / price_list[i] * 100
                        daily_ranges.append(day_range)
                if daily_ranges:
                    avg_range = sum(daily_ranges) / len(daily_ranges)
                    c["avg_daily_range"] = round(avg_range, 2)
                    c["high_volatility"] = avg_range > 4.0
                    if c["high_volatility"]:
                        log(f"  HIGH-VOL: {tk} avg daily range {avg_range:.1f}% — half size, wider stop")

        # Deduplicate by ticker, keep highest momentum entry
        seen_tickers = set()
        deduped = []
        for c in catalyst_opportunities:
            if c["ticker"] not in seen_tickers:
                seen_tickers.add(c["ticker"])
                deduped.append(c)
        catalyst_opportunities = deduped

        catalyst_opportunities.sort(key=lambda x: (-x["excess_21d"], x["days_until"]))
        catalyst_opportunities = catalyst_opportunities[:8]
        # ── NON-EARNINGS CATALYST SOURCES (Finnhub + yfinance, zero Claude cost) ──
        try:
            import requests, os
            _FK = os.environ.get("FINNHUB_KEY", "")
            if _FK:
                # Finnhub: Analyst recommendation changes (upgrades/downgrades)
                for s in top_momentum[:15]:
                    tk = s["ticker"]
                    already = any(c["ticker"] == tk for c in catalyst_opportunities)
                    if already:
                        continue
                    try:
                        url = f"https://finnhub.io/api/v1/stock/recommendation?symbol={tk}&token={_FK}"
                        r = requests.get(url, timeout=5)
                        if r.status_code == 200:
                            recs = r.json()
                            if len(recs) >= 2:
                                latest = recs[0]
                                prev = recs[1]
                                buy_change = (latest.get("buy", 0) + latest.get("strongBuy", 0)) - (prev.get("buy", 0) + prev.get("strongBuy", 0))
                                if buy_change >= 3:
                                    stock_industry = ""
                                    for ind_name, tickers_list in INDUSTRY_STOCK_LEADERS.items():
                                        if tk in tickers_list:
                                            stock_industry = ind_name
                                            break
                                    catalyst_opportunities.append({
                                        "ticker": tk,
                                        "industry": stock_industry,
                                        "earnings_date": "",
                                        "eps_estimate": None,
                                        "excess_21d": s["excess_21d"],
                                        "price": s["price"],
                                        "has_news": True,
                                        "news_headlines": [f"Analyst upgrades: {buy_change} more buy ratings this month"],
                                        "catalyst_type": "analyst_upgrade",
                                        "days_until": 0,
                                        "significance": "high",
                                    })
                                    log(f"  ANALYST UPGRADE: {tk} — {buy_change} new buy ratings")
                    except Exception:
                        continue

                # Finnhub: IPO calendar for upcoming IPOs in our universe
                try:
                    from datetime import timedelta
                    _from = today_dt.strftime("%Y-%m-%d")
                    _to = (today_dt + timedelta(days=30)).strftime("%Y-%m-%d")
                    url = f"https://finnhub.io/api/v1/calendar/ipo?from={_from}&to={_to}&token={_FK}"
                    r = requests.get(url, timeout=5)
                    if r.status_code == 200:
                        ipos = r.json().get("ipoCalendar", [])
                        for ipo in ipos[:5]:
                            ipo_ticker = ipo.get("symbol", "")
                            if ipo_ticker and ipo_ticker in prices:
                                already = any(c["ticker"] == ipo_ticker for c in catalyst_opportunities)
                                if not already:
                                    catalyst_opportunities.append({
                                        "ticker": ipo_ticker,
                                        "industry": "",
                                        "earnings_date": ipo.get("date", ""),
                                        "eps_estimate": None,
                                        "excess_21d": 0,
                                        "price": round(prices[ipo_ticker][-1], 2) if ipo_ticker in prices else 0,
                                        "has_news": True,
                                        "news_headlines": [f"IPO/lockup event: {ipo.get('name', ipo_ticker)}"],
                                        "catalyst_type": "ipo_event",
                                        "days_until": 0,
                                        "significance": "high",
                                    })
                                    log(f"  IPO EVENT: {ipo_ticker}")
                except Exception:
                    pass

            # Volume spike fallback — if forward_catalysts is empty, find stocks
            # with 3x+ volume spikes in last 2 days (something happened)
            if not forward_catalysts:
                log("Forward catalysts empty — using volume spike fallback")
                vol_data_fb = volume_data if "volume_data" in dir() else {}
                for tk, vd in vol_data_fb.items():
                    if tk == "SPY" or any(c["ticker"] == tk for c in catalyst_opportunities):
                        continue
                    if vd.get("rvol", 0) >= 3.0 and tk in prices:
                        price_list = prices[tk]
                        if len(price_list) >= 2:
                            day1_ret = (price_list[-1] / price_list[-2] - 1) * 100
                            if day1_ret > 2:
                                stk_21d = 0
                                if len(price_list) >= 21 and len(spy_prices_cat) >= 21:
                                    stk_21d = (price_list[-1] / price_list[-21] - 1) * 100 - spy_21d
                                stock_industry = ""
                                for ind_name, tl in INDUSTRY_STOCK_LEADERS.items():
                                    if tk in tl:
                                        stock_industry = ind_name
                                        break
                                catalyst_opportunities.append({
                                    "ticker": tk,
                                    "industry": stock_industry,
                                    "earnings_date": "",
                                    "eps_estimate": None,
                                    "excess_21d": round(stk_21d, 1),
                                    "price": round(price_list[-1], 2),
                                    "has_news": False,
                                    "news_headlines": [f"Volume spike: {vd['rvol']:.1f}x normal with +{day1_ret:.1f}% move"],
                                    "catalyst_type": "volume_spike",
                                    "days_until": 0,
                                    "significance": "medium",
                                })
                                log(f"  VOLUME SPIKE: {tk} RVOL {vd['rvol']:.1f}x, +{day1_ret:.1f}%")
                                if len([c for c in catalyst_opportunities if c["catalyst_type"] == "volume_spike"]) >= 5:
                                    break
        except Exception as e:
            log(f"Non-earnings catalyst sources error (non-fatal): {e}")

        log(f"Catalyst scanner: {len(catalyst_opportunities)} total opportunities (earnings + events + news + upgrades + volume)")
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
        # Add catalyst_opportunities to rules_output so Telegram can access them
        rules_output["catalyst_opportunities"] = catalyst_opportunities
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
            cash=cash_balance,
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
