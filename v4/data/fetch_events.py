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
            url = f"https://financialmodelingprep.com/stable/earnings-calendar?from={today_str}&to={end_str}&apikey={FMP_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                log(f"  API HTTP {r.status_code} for {url.split('?')[0].split('/')[-1]}: {r.text[:90]}")
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
            url = f"https://financialmodelingprep.com/stable/splits-calendar?from={today_str}&to={end_str}&apikey={FMP_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                log(f"  API HTTP {r.status_code} for {url.split('?')[0].split('/')[-1]}: {r.text[:90]}")
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
            url = f"https://financialmodelingprep.com/stable/ipos-calendar?from={today_str}&to={end_str}&apikey={FMP_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                log(f"  API HTTP {r.status_code} for {url.split('?')[0].split('/')[-1]}: {r.text[:90]}")
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

        # (analyst consensus block removed — upgrades dropped from system)

        # 1e. Economic Calendar — FRED (free; FMP economic is paywalled)
        try:
            import os as _os
            _fred = _os.environ.get("FRED_KEY", "")
            if _fred:
                # Key recurring high-impact US releases via FRED release dates
                _WANT = ["consumer price index", "employment situation", "producer price",
                         "gross domestic product", "retail sales", "fomc", "federal open market"]
                try:
                    _u = f"https://api.stlouisfed.org/fred/releases/dates?api_key={_fred}&file_type=json&realtime_start={today_str}&sort_order=asc&limit=200&include_release_dates_with_no_data=true"
                    _r = requests.get(_u, timeout=10)
                    if _r.status_code == 200:
                        _seen_rel = set()
                        for _rd in _r.json().get("release_dates", []):
                            _d, _nm = _rd.get("date", ""), (_rd.get("release_name", "") or "")
                            if not (today_str <= _d <= end_str):
                                continue
                            if not any(w in _nm.lower() for w in _WANT):
                                continue
                            if _nm in _seen_rel:
                                continue
                            _seen_rel.add(_nm)
                            events.append({"ticker": "MACRO", "event_type": "economic", "date": _d,
                                           "description": f"{_nm} — market-wide release.",
                                           "significance": "high"})
                    else:
                        log(f"  FRED HTTP {_r.status_code}")
                except Exception as _fe:
                    log(f"  FRED error: {_fe}")
                log(f"  FRED economic calendar: {len([e for e in events if e['event_type'] == 'economic'])} upcoming releases")
            else:
                log("  FRED_KEY not set — skipping economic calendar")
        except Exception as e:
            log(f"  FRED economic error: {e}")

        # 1f. Press releases handled by Finnhub sweep (see fetch_catalyst_press_releases)
        #     FMP press-releases endpoint is paywalled on free tier.

    else:
        log("FMP_API_KEY not set — skipping FMP data (sign up free at financialmodelingprep.com)")

    # ── SOURCE 2: Finnhub (already have key) ──────────────────────────
    if FINNHUB_KEY:
        log("Fetching events from Finnhub...")

        # 2a. Earnings calendar
        try:
            url = f"https://finnhub.io/api/v1/calendar/earnings?from={today_str}&to={end_str}&token={FINNHUB_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                log(f"  API HTTP {r.status_code} for {url.split('?')[0].split('/')[-1]}: {r.text[:90]}")
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
            if r.status_code != 200:
                log(f"  API HTTP {r.status_code} for {url.split('?')[0].split('/')[-1]}: {r.text[:90]}")
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
            if r.status_code != 200:
                log(f"  API HTTP {r.status_code} for {url.split('?')[0].split('/')[-1]}: {r.text[:90]}")
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

    # FDA PDUFA dates — merged into forward_catalysts call to save $0.50-0.80/day
    # See fetch_news.py fetch_forward_catalysts() which now includes FDA search


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


def fetch_catalyst_press_releases(tickers: list, days_back: int = 3) -> list:
    """Free press-release substitute: Finnhub company-news swept across the
    given tickers (scanner momentum candidates), filtered to real catalysts.
    Replaces the paywalled FMP press-release stream. Ticker-targeted = higher
    signal-to-noise than a firehose."""
    import os, requests
    from datetime import datetime, timedelta
    key = os.environ.get("FINNHUB_KEY", "")
    if not key or not tickers:
        return []
    KEYWORDS = ["FDA", "APPROVAL", "PDUFA", "CONTRACT", "ACQUISITION", "MERGER",
                "ACQUIRE", "LAUNCH", "PARTNERSHIP", "AWARD", "MILESTONE",
                "BREAKTHROUGH", "PATENT", "BUYBACK", "REPURCHASE", "SPINOFF",
                "SPIN-OFF", "DIVESTITURE", "ACTIVIST", "13D", "STAKE", "INDEX",
                "S&P 500", "NASDAQ-100", "RUSSELL", "INCLUSION", "DEFENSE",
                "GOVERNMENT CONTRACT", "PHASE 3", "PHASE III", "TOPLINE",
                "RAISED GUIDANCE", "RAISES GUIDANCE", "RECORD REVENUE",
                "WINS", "AWARDED", "SETTLEMENT", "APPROVES", "ANTITRUST",
                "FTC", "DOJ", "SPECIAL DIVIDEND", "INITIATES DIVIDEND"]
    frm = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    to = datetime.utcnow().strftime("%Y-%m-%d")
    out, seen = [], set()
    for tk in tickers[:40]:  # cap API calls
        try:
            r = requests.get(f"https://finnhub.io/api/v1/company-news?symbol={tk}&from={frm}&to={to}&token={key}", timeout=8)
            if r.status_code != 200:
                continue
            for item in r.json()[:10]:
                hl = (item.get("headline") or "")
                up = hl.upper()
                # Reject market-wrap / listicle noise
                NOISE = ["TOP GAINERS", "LOSERS", "STOCK MARKET TODAY", "MARKET WRAP",
                         "STOCKS TO WATCH", "BEST STOCKS", "WHY IS", "IS UP", "IS DOWN",
                         "HERE'S WHAT", "INSIDE THE", "EXPLORE THE", "MOVERS", "PREMARKET",
                         "3 STOCKS", "5 STOCKS", "JIM CRAMER", "MOTLEY FOOL"]
                if any(nz in up for nz in NOISE):
                    continue
                # Index keywords only count with real inclusion phrasing
                INDEXY = ["S&P 500", "NASDAQ-100", "RUSSELL", "INDEX"]
                if any(ix in up for ix in INDEXY) and not any(
                        ph in up for ph in ["ADDED TO", "WILL JOIN", "JOINS THE", "INCLUSION IN", "TO JOIN THE"]):
                    if not any(kw in up for kw in ["FDA", "CONTRACT", "ACQUISITION", "MERGER",
                                                   "BUYBACK", "PHASE 3", "APPROVAL", "AWARDED"]):
                        continue
                if not any(kw in up for kw in KEYWORDS):
                    continue
                # Company must be named in the headline
                if tk.upper() not in up and not any(kw in up for kw in ["FDA", "CONTRACT", "AWARDED", "ACQUISITION"]):
                    continue
                if tk in seen:
                    continue
                seen.add(tk)
                out.append({
                    "ticker": tk,
                    "event_type": "press_release",
                    "date": datetime.utcfromtimestamp(item.get("datetime", 0)).strftime("%Y-%m-%d") if item.get("datetime") else to,
                    "description": hl[:150],
                    "significance": "high",
                })
                break
        except Exception:
            continue
    return out
