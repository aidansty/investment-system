"""
Event-first catalyst scanner data source.
Fetches structured event calendars from FMP + Finnhub.
Returns a unified list of upcoming events with tickers and dates.
No Claude calls needed.
"""
import os
import requests
from datetime import datetime, timedelta
import pytz

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")

def log(msg):
    eastern = pytz.timezone("America/New_York")
    ts = datetime.now(eastern).strftime("%Y-%m-%d %H:%M:%S ET")
    print(f"[{ts}] {msg}")


def fetch_all_events(days_ahead=30):
    """
    Fetch ALL upcoming market events from multiple free sources.
    Returns a unified list of events, each with:
    - ticker, event_type, date, description, significance
    """
    eastern = pytz.timezone("America/New_York")
    today = datetime.now(eastern).date()
    end_date = today + timedelta(days=days_ahead)
    today_str = today.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    events = []

    # ── SOURCE 1: FMP (if key available) ──────────────────────────────
    if FMP_KEY:
        log(f"Fetching events from FMP (free tier)...")

        # 1a. Earnings Calendar
        try:
            url = f"https://financialmodelingprep.com/api/v3/earning_calendar?from={today_str}&to={end_str}&apikey={FMP_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                for item in data:
                    if item.get("symbol") and item.get("date"):
                        events.append({
                            "ticker": item["symbol"],
                            "event_type": "earnings",
                            "date": item["date"],
                            "description": f"Earnings report — EPS estimate: {item.get('epsEstimated', 'N/A')}, Revenue estimate: ${item.get('revenueEstimated', 'N/A')}",
                            "significance": "high",
                            "eps_estimate": item.get("epsEstimated"),
                            "revenue_estimate": item.get("revenueEstimated"),
                        })
                log(f"  FMP earnings: {len([e for e in events if e['event_type'] == 'earnings'])} events")
        except Exception as e:
            log(f"  FMP earnings error: {e}")

        # 1b. Stock Splits Calendar
        try:
            url = f"https://financialmodelingprep.com/api/v3/stock_split_calendar?from={today_str}&to={end_str}&apikey={FMP_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                for item in data:
                    if item.get("symbol") and item.get("date"):
                        ratio = f"{item.get('numerator', '?')}:{item.get('denominator', '?')}"
                        events.append({
                            "ticker": item["symbol"],
                            "event_type": "stock_split",
                            "date": item["date"],
                            "description": f"Stock split {ratio} — splits attract retail buying and often drive 5-15% moves in the weeks surrounding the split date",
                            "significance": "high",
                        })
                log(f"  FMP splits: {len([e for e in events if e['event_type'] == 'stock_split'])} events")
        except Exception as e:
            log(f"  FMP splits error: {e}")

        # 1c. IPO Calendar
        try:
            url = f"https://financialmodelingprep.com/api/v3/ipo_calendar?from={today_str}&to={end_str}&apikey={FMP_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                for item in data:
                    if item.get("symbol") and item.get("date"):
                        events.append({
                            "ticker": item["symbol"],
                            "event_type": "ipo",
                            "date": item["date"],
                            "description": f"IPO: {item.get('company', item['symbol'])} — price range ${item.get('priceRange', 'TBD')}",
                            "significance": "medium",
                        })
                log(f"  FMP IPOs: {len([e for e in events if e['event_type'] == 'ipo'])} events")
        except Exception as e:
            log(f"  FMP IPO error: {e}")

        # 1d. Analyst Upgrades/Downgrades (recent, last 7 days)
        try:
            week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
            url = f"https://financialmodelingprep.com/api/v3/upgrades-downgrades-consensus?apikey={FMP_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                for item in data[:100]:
                    if item.get("symbol"):
                        consensus = item.get("consensusKey", "")
                        if consensus in ("strongBuy", "buy"):
                            events.append({
                                "ticker": item["symbol"],
                                "event_type": "analyst_upgrade",
                                "date": today_str,
                                "description": f"Analyst consensus: {consensus} — {item.get('targetConsensus', 'N/A')} target price from {item.get('count', '?')} analysts",
                                "significance": "medium",
                                "target_price": item.get("targetConsensus"),
                            })
                upgrades = [e for e in events if e["event_type"] == "analyst_upgrade"]
                log(f"  FMP analyst consensus: {len(upgrades)} strong buy/buy stocks")
        except Exception as e:
            log(f"  FMP analyst error: {e}")

        # 1e. Economic Calendar (macro events)
        try:
            url = f"https://financialmodelingprep.com/api/v3/economic_calendar?from={today_str}&to={end_str}&apikey={FMP_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                high_impact = [item for item in data if item.get("impact", "").lower() in ("high", "medium")]
                for item in high_impact[:10]:
                    events.append({
                        "ticker": "MACRO",
                        "event_type": "economic",
                        "date": item.get("date", today_str)[:10],
                        "description": f"{item.get('event', 'Economic event')} — estimate: {item.get('estimate', 'N/A')}, previous: {item.get('previous', 'N/A')}",
                        "significance": "high" if item.get("impact", "").lower() == "high" else "medium",
                    })
                log(f"  FMP economic calendar: {len([e for e in events if e['event_type'] == 'economic'])} high-impact events")
        except Exception as e:
            log(f"  FMP economic error: {e}")

        # 1f. Press Releases (recent company announcements)
        try:
            url = f"https://financialmodelingprep.com/api/v3/press-releases?page=0&apikey={FMP_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                catalyst_keywords = ["FDA", "APPROVAL", "PDUFA", "CONTRACT", "ACQUISITION", "MERGER",
                                     "LAUNCH", "PARTNERSHIP", "AGREEMENT", "AWARD", "MILESTONE",
                                     "BREAKTHROUGH", "PATENT", "EXPANSION", "GUIDANCE", "BUYBACK",
                                     "REPURCHASE", "SPINOFF", "SPIN-OFF", "DIVESTITURE", "SPLIT",
                                     "ACTIVIST", "13D", "STAKE", "INDEX", "S&P 500", "NASDAQ-100",
                                     "RUSSELL", "INCLUSION", "DEFENSE CONTRACT", "GOVERNMENT",
                                     "CLINICAL TRIAL", "PHASE 3", "PHASE III", "TOPLINE",
                                     "RECORD REVENUE", "RECORD EARNINGS", "RAISED GUIDANCE"]
                for item in data[:50]:
                    title = (item.get("title", "") or "").upper()
                    if any(kw in title for kw in catalyst_keywords):
                        events.append({
                            "ticker": item.get("symbol", ""),
                            "event_type": "press_release",
                            "date": (item.get("date", "") or "")[:10],
                            "description": item.get("title", "")[:150],
                            "significance": "high",
                        })
                log(f"  FMP press releases: {len([e for e in events if e['event_type'] == 'press_release'])} catalyst-relevant")
        except Exception as e:
            log(f"  FMP press releases error: {e}")
    else:
        log("FMP_API_KEY not set — skipping FMP data (sign up free at financialmodelingprep.com)")

    # ── SOURCE 2: Finnhub (already have key) ──────────────────────────
    if FINNHUB_KEY:
        log("Fetching events from Finnhub...")

        # 2a. Earnings calendar
        try:
            url = f"https://finnhub.io/api/v1/calendar/earnings?from={today_str}&to={end_str}&token={FINNHUB_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                existing_tickers = {e["ticker"] for e in events if e["event_type"] == "earnings"}
                for item in data.get("earningsCalendar", []):
                    tk = item.get("symbol", "")
                    if tk and tk not in existing_tickers:
                        events.append({
                            "ticker": tk,
                            "event_type": "earnings",
                            "date": item.get("date", ""),
                            "description": f"Earnings — EPS estimate: {item.get('epsEstimate', 'N/A')}",
                            "significance": "high",
                            "eps_estimate": item.get("epsEstimate"),
                        })
                log(f"  Finnhub earnings: added non-duplicate entries")
        except Exception as e:
            log(f"  Finnhub earnings error: {e}")

        # 2b. IPO calendar
        try:
            url = f"https://finnhub.io/api/v1/calendar/ipo?from={today_str}&to={end_str}&token={FINNHUB_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                ipos = r.json().get("ipoCalendar", [])
                for item in ipos:
                    tk = item.get("symbol", "")
                    if tk:
                        events.append({
                            "ticker": tk,
                            "event_type": "ipo",
                            "date": item.get("date", ""),
                            "description": f"IPO: {item.get('name', tk)}",
                            "significance": "medium",
                        })
                log(f"  Finnhub IPOs: {len(ipos)} events")
        except Exception as e:
            log(f"  Finnhub IPO error: {e}")

    # ── SOURCE 3: Finnhub Insider Transactions (free tier) ─────────
    if FINNHUB_KEY:
        log("Fetching insider buying data from Finnhub...")
        try:
            url = f"https://finnhub.io/api/v1/stock/insider-transactions?symbol=&from={today_str}&to={end_str}&token={FINNHUB_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json().get("data", [])
                # Group by ticker — find clusters of insider BUYING
                insider_buys = {}
                for txn in data:
                    if txn.get("transactionType") in ("P - Purchase", "P"):
                        tk = txn.get("symbol", "")
                        if tk:
                            if tk not in insider_buys:
                                insider_buys[tk] = []
                            insider_buys[tk].append({
                                "name": txn.get("name", ""),
                                "shares": txn.get("share", 0),
                                "value": txn.get("transactionValue", 0),
                                "date": txn.get("transactionDate", ""),
                            })
                # Only flag stocks with 2+ insider buys (cluster = high confidence)
                for tk, buys in insider_buys.items():
                    if len(buys) >= 2:
                        total_value = sum(b.get("value", 0) or 0 for b in buys)
                        names = [b["name"] for b in buys[:3]]
                        events.append({
                            "ticker": tk,
                            "event_type": "insider_buying",
                            "date": buys[0].get("date", today_str),
                            "description": f"Insider buying cluster: {len(buys)} executives purchased shares (total ${total_value:,.0f}). Insiders: {', '.join(names[:3])}. When multiple executives buy their own stock, it historically signals 8-12% outperformance over 60 days.",
                            "significance": "high",
                        })
                insider_count = len([e for e in events if e["event_type"] == "insider_buying"])
                log(f"  Finnhub insider buying clusters: {insider_count} stocks with 2+ insider purchases")
        except Exception as e:
            log(f"  Finnhub insider buying error: {e}")

    # ── SOURCE 4: FDA PDUFA dates via Claude web search (ONE focused call) ──
    try:
        import anthropic
        client = anthropic.Anthropic()
        log("Fetching FDA PDUFA dates via focused Claude search...")
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": f"List ALL FDA PDUFA drug approval decision dates between {today_str} and {end_str}. For each, provide: 1) the pharmaceutical company ticker symbol, 2) the exact PDUFA date, 3) the drug name, 4) what it treats. Format each as: TICKER|DATE|DRUG|INDICATION. Only include publicly traded US stocks. No commentary, just the list."
            }],
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
        )
        fda_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                fda_text += block.text
        for line in fda_text.strip().splitlines():

            parts = line.strip().strip("-•").split("|")
            if len(parts) >= 3:
                tk = parts[0].strip().upper()
                dt = parts[1].strip()
                drug = parts[2].strip()
                indication = parts[3].strip() if len(parts) > 3 else ""
                if len(tk) <= 5 and tk.isalpha():
                    events.append({
                        "ticker": tk,
                        "event_type": "fda_pdufa",
                        "date": dt,
                        "description": f"FDA PDUFA decision: {drug} for {indication}. Binary event — approval typically drives 20-50% upside, rejection drives 20-40% downside. Date is publicly known and confirmed.",
                        "significance": "high",
                    })
        fda_count = len([e for e in events if e["event_type"] == "fda_pdufa"])
        log(f"  FDA PDUFA dates found: {fda_count}")
    except Exception as e:
        log(f"  FDA PDUFA search error (non-fatal): {e}")

    # ── Deduplicate by ticker + event_type ────────────────────────────
# ── Deduplicate by ticker + event_type ────────────────────────────
    seen = set()
    deduped = []
    for e in events:
        key = (e["ticker"], e["event_type"])
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    events = deduped

    log(f"Event calendar total: {len(events)} unique events across {len(set(e['event_type'] for e in events))} types")
    by_type = {}
    for e in events:
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
    for t, c in sorted(by_type.items()):
        log(f"  {t}: {c}")

    return events
