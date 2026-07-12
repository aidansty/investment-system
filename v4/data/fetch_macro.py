import os
import requests
from v4.utils.logger import log

FRED_KEY = os.environ.get("FRED_KEY", "")
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")


def fetch_macro_data() -> dict:
    """
    Fetch macro indicators: VIX, SPY data, economic calendar.
    Returns structured macro context dict.
    """
    macro = {}

    # VIX
    vix = _fetch_vix()
    macro["vix"] = vix
    macro["vix_regime"] = _classify_vix(vix)

    # VIX history for trend
    vix_history = _fetch_vix_history()
    macro["vix_history"] = vix_history
    macro["vix_5d_avg"] = round(sum(vix_history[-5:]) / 5, 2) if len(vix_history) >= 5 else vix
    macro["vix_trend"] = _get_vix_trend(vix, macro["vix_5d_avg"])

    # Economic calendar
    macro["economic_events"] = _fetch_economic_events()

    log(f"Macro: VIX {vix} ({macro['vix_regime']}) | Trend: {macro['vix_trend']}")
    return macro


def _fetch_vix() -> float:
    """Fetch current VIX from yfinance (near-real-time) instead of FRED (previous day close)."""
    try:
        import yfinance as yf
        vix_data = yf.download("^VIX", period="2d", progress=False)
        if not vix_data.empty:
            vix = round(float(vix_data["Close"].iloc[-1]), 2)
            log(f"VIX fetched from yfinance: {vix}")
            return vix
    except Exception as e:
        log(f"VIX yfinance error: {e}")
    try:
        if FRED_KEY:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id=VIXCLS&api_key={FRED_KEY}&file_type=json&limit=1&sort_order=desc"
            r = requests.get(url, timeout=10)
            obs = r.json().get("observations", [])
            if obs and obs[0].get("value", ".") != ".":
                vix = round(float(obs[0]["value"]), 2)
                log(f"VIX fetched from FRED (fallback): {vix}")
                return vix
    except Exception:
        pass
    log("WARNING: Could not fetch VIX — using fallback 20.0")
    return 20.0


def _fetch_vix_history(days: int = 30) -> list:
    try:
        import yfinance as yf
        vix_data = yf.download("^VIX", period="2mo", progress=False)
        if not vix_data.empty:
            values = [round(float(v), 2) for v in vix_data["Close"].dropna().tolist()]
            log(f"VIX history fetched from yfinance: {len(values)} days")
            return values[-days:]
    except Exception as e:
        log(f"VIX history yfinance error: {e}")
    try:
        if FRED_KEY:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id=VIXCLS&api_key={FRED_KEY}&file_type=json&limit={days}&sort_order=desc"
            r = requests.get(url, timeout=10)
            obs = r.json().get("observations", [])
            values = [float(o["value"]) for o in reversed(obs) if o.get("value", ".") != "."]
            return values
    except Exception:
        pass
    return []


def _classify_vix(vix: float) -> str:
    if vix < 18:
        return "Green"
    elif vix < 25:
        return "Yellow"
    else:
        return "Red"


def _get_vix_trend(vix: float, vix_5d_avg: float) -> str:
    if vix_5d_avg == 0:
        return "Flat"
    change_pct = (vix - vix_5d_avg) / vix_5d_avg * 100
    if change_pct > 20:
        return "Spiking"
    elif change_pct > 5:
        return "Rising"
    elif change_pct < -5:
        return "Falling"
    return "Flat"


def _fetch_economic_events() -> list:
    """Fetch today economic calendar events from Finnhub."""
    if not FINNHUB_KEY:
        return []
    try:
        from datetime import date
        today = date.today().isoformat()
        url = f"https://finnhub.io/api/v1/calendar/economic?token={FINNHUB_KEY}"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        events = data.get("economicCalendar", [])
        today_events = []
        for e in events:
            if e.get("time", "").startswith(today):
                impact = e.get("impact", "")
                if impact in ("high", "medium"):
                    today_events.append({
                        "name": e.get("event", ""),
                        "impact": impact,
                        "time": e.get("time", ""),
                        "actual": e.get("actual", ""),
                        "estimate": e.get("estimate", ""),
                    })
        log(f"Economic events today: {len(today_events)}")
        return today_events
    except Exception as e:
        log(f"Economic calendar error: {e}")
        return []


def fetch_earnings_calendar(tickers: list) -> dict:
    import requests, os, pytz
    from datetime import datetime, timedelta
    FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
    if not FINNHUB_KEY:
        return {}
    eastern = pytz.timezone("America/New_York")
    today = datetime.now(eastern).date()
    end = today + timedelta(days=90)
    from_str = today.strftime("%Y-%m-%d")
    to_str = end.strftime("%Y-%m-%d")
    crypto = {"BTC", "ETH", "XRP", "ZEC", "BNB", "SOL", "DOGE"}
    results = {}
    for ticker in tickers:
        if ticker in crypto:
            continue
        try:
            url = f"https://finnhub.io/api/v1/calendar/earnings?symbol={ticker}&from={from_str}&to={to_str}&token={FINNHUB_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            earnings_list = data.get("earningsCalendar", [])
            if earnings_list:
                next_e = earnings_list[0]
                results[ticker] = {
                    "date": next_e.get("date", ""),
                    "hour": next_e.get("hour", ""),
                    "eps_estimate": next_e.get("epsEstimate"),
                    "revenue_estimate": next_e.get("revenueEstimate"),
                }
        except Exception:
            continue
    return results


def fetch_recent_earnings_results(tickers: list, lookback_days: int = 14) -> dict:
    """
    Fetch ACTUAL reported earnings results (not estimates) for the past N days.
    This tells the system whether a recent earnings report was good or bad —
    so it never has to tell the user to go check results themselves.
    """
    import requests, os, pytz
    from datetime import datetime, timedelta
    FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
    if not FINNHUB_KEY:
        return {}
    eastern = pytz.timezone("America/New_York")
    today = datetime.now(eastern).date()
    start = today - timedelta(days=lookback_days)
    from_str = start.strftime("%Y-%m-%d")
    to_str = today.strftime("%Y-%m-%d")
    crypto = {"BTC", "ETH", "XRP", "ZEC", "BNB", "SOL", "DOGE"}
    results = {}
    for ticker in tickers:
        if ticker in crypto:
            continue
        try:
            url = f"https://finnhub.io/api/v1/calendar/earnings?symbol={ticker}&from={from_str}&to={to_str}&token={FINNHUB_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            earnings_list = data.get("earningsCalendar", [])
            for e in earnings_list:
                eps_actual = e.get("epsActual")
                eps_estimate = e.get("epsEstimate")
                rev_actual = e.get("revenueActual")
                rev_estimate = e.get("revenueEstimate")
                if eps_actual is not None and eps_estimate is not None:
                    eps_surprise_pct = round((eps_actual - eps_estimate) / abs(eps_estimate) * 100, 1) if eps_estimate != 0 else 0
                    rev_surprise_pct = None
                    if rev_actual is not None and rev_estimate is not None and rev_estimate != 0:
                        rev_surprise_pct = round((rev_actual - rev_estimate) / abs(rev_estimate) * 100, 1)
                elif e.get("date"):
                    # Finnhub hasn't backfilled actuals yet — try yfinance as fallback
                    try:
                        import yfinance as yf
                        yf_ticker = yf.Ticker(ticker)
                        yf_earnings = yf_ticker.earnings_dates
                        if yf_earnings is not None and not yf_earnings.empty:
                            report_date_str = e.get("date")
                            for idx, row in yf_earnings.iterrows():
                                if str(idx.date()) == report_date_str:
                                    yf_eps_actual = row.get("Reported EPS")
                                    yf_eps_estimate = row.get("EPS Estimate")
                                    if yf_eps_actual == yf_eps_actual and yf_eps_estimate == yf_eps_estimate:  # not NaN
                                        eps_actual = float(yf_eps_actual)
                                        eps_estimate = float(yf_eps_estimate)
                                        eps_surprise_pct = round((eps_actual - eps_estimate) / abs(eps_estimate) * 100, 1) if eps_estimate != 0 else 0
                                        rev_actual = None
                                        rev_estimate = None
                                        rev_surprise_pct = None
                                    break
                    except Exception:
                        pass
                    if eps_actual is None:
                        continue
                    verdict = "BEAT" if eps_surprise_pct > 2 else "MISS" if eps_surprise_pct < -2 else "IN-LINE"
                    results[ticker] = {
                        "report_date": e.get("date", ""),
                        "eps_actual": eps_actual,
                        "eps_estimate": eps_estimate,
                        "eps_surprise_pct": eps_surprise_pct,
                        "revenue_actual": rev_actual,
                        "revenue_estimate": rev_estimate,
                        "revenue_surprise_pct": rev_surprise_pct,
                        "verdict": verdict,
                    }
        except Exception:
            continue
    return results
