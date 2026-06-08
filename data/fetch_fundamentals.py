import os
import requests
from datetime import date, timedelta
from utils.logger import log
from utils.rate_limiter import finnhub_limiter

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")

# Data sanitation guardrails — not signal logic
# These prevent bad API data from corrupting downstream calculations
# Do not use these thresholds in any earnings scoring or alpha logic
MIN_ESTIMATE_ABS = 0.05    # Ignore near-zero estimates (data quality issue)
MAX_SURPRISE_PCT = 500.0   # Cap extreme surprises (data quality issue)

# Soft cap on fundamentals fetch
# Prevents runaway runtime on days with unusually high RS qualifiers
# Only the top N by RS score are evaluated for fundamentals
# Increase in V2 if coverage feels insufficient
MAX_TICKERS_TO_FETCH = 150


def fetch_earnings_surprises(ticker: str) -> tuple:
    """
    Fetch last 6 quarters of earnings surprise data for one ticker.
    Returns (results_list, status_string).

    Status values:
        "success"      - data returned and parsed
        "no_data"      - API returned empty or unusable quarters
        "api_error"    - non-200 response or exception
        "rate_limited" - HTTP 429 received
    """
    try:
        finnhub_limiter.wait()
        url = (
            f"https://finnhub.io/api/v1/stock/earnings"
            f"?symbol={ticker}&limit=6&token={FINNHUB_KEY}"
        )
        r = requests.get(url, timeout=10)

        if r.status_code == 429:
            log(f"Rate limited on {ticker}")
            return [], "rate_limited"

        if r.status_code != 200:
            return [], "api_error"

        data = r.json()
        if not data or not isinstance(data, list):
            return [], "no_data"

        results = []
        for quarter in data:
            actual = quarter.get("actual")
            estimate = quarter.get("estimate")

            if actual is None or estimate is None:
                continue

            # Sanitation guardrail: skip near-zero estimates
            if abs(estimate) < MIN_ESTIMATE_ABS:
                continue

            surprise_pct = ((actual - estimate) / abs(estimate)) * 100

            # Sanitation guardrail: cap extreme values
            surprise_pct = max(-MAX_SURPRISE_PCT,
                               min(MAX_SURPRISE_PCT, surprise_pct))

            results.append({
                "period": quarter.get("period", ""),
                "actual": round(actual, 4),
                "estimate": round(estimate, 4),
                "surprise_pct": round(surprise_pct, 2),
                "beat": actual > estimate
            })

        if not results:
            return [], "no_data"

        return results, "success"

    except Exception as e:
        log(f"Earnings surprise fetch error for {ticker}: {e}")
        return [], "api_error"


def fetch_earnings_calendar(ticker: str) -> tuple:
    """
    Fetch upcoming earnings dates for one ticker (next 60 days).
    Per-symbol call required — global calendar is capped at 1500
    events and cannot guarantee full universe coverage.

    Returns (calendar_list, status_string).
    """
    try:
        finnhub_limiter.wait()
        today = date.today()
        end = today + timedelta(days=60)

        url = (
            f"https://finnhub.io/api/v1/calendar/earnings"
            f"?from={today.isoformat()}&to={end.isoformat()}"
            f"&symbol={ticker}&token={FINNHUB_KEY}"
        )
        r = requests.get(url, timeout=10)

        if r.status_code == 429:
            return [], "rate_limited"

        if r.status_code != 200:
            return [], "api_error"

        data = r.json()
        calendar = data.get("earningsCalendar", [])
        return calendar, "success"

    except Exception as e:
        log(f"Calendar fetch error for {ticker}: {e}")
        return [], "api_error"


def fetch_fundamentals_batch(tickers: list) -> dict:
    """
    Fetch earnings surprises and calendar for all qualified tickers.
    Sequential with rate limiter — deliberate V1 simplicity choice.
    If universe expands significantly, revisit async batching in V2.

    Tickers should arrive pre-sorted by RS score (strongest first).
    Soft cap of MAX_TICKERS_TO_FETCH protects against high-volatility
    days where RS qualifiers spike well above typical 100-120 range.

    Runtime estimate:
        tickers * 2 calls / 55 calls_per_min = runtime in minutes
        Typical (100 tickers):  ~3.6 minutes
        Worst case (150 cap):   ~5.5 minutes
        Without cap (180+):     ~7+ minutes (prevented by cap)
    """
    # Apply soft cap — tickers must arrive sorted by RS score descending
    original_count = len(tickers)
    if len(tickers) > MAX_TICKERS_TO_FETCH:
        tickers = tickers[:MAX_TICKERS_TO_FETCH]
        log(f"Soft cap applied: {original_count} → {len(tickers)} tickers "
            f"(max {MAX_TICKERS_TO_FETCH})")

    estimated_minutes = (len(tickers) * 2) / 55
    log(f"Fetching fundamentals for {len(tickers)} tickers | "
        f"~{len(tickers) * 2} API calls | "
        f"estimated {estimated_minutes:.1f} minutes...")

    results = {}
    status_counts = {
        "success": 0,
        "no_data": 0,
        "api_error": 0,
        "rate_limited": 0
    }

    for i, ticker in enumerate(tickers):
        earnings, e_status = fetch_earnings_surprises(ticker)
        calendar, c_status = fetch_earnings_calendar(ticker)

        # Overall status: success if either returned data
        if e_status == "success":
            status = "success"
        elif c_status == "success":
            status = "success"
        elif "rate_limited" in [e_status, c_status]:
            status = "rate_limited"
        elif "api_error" in [e_status, c_status]:
            status = "api_error"
        else:
            status = "no_data"

        results[ticker] = {
            "earnings": earnings,
            "calendar": calendar,
            "status": status
        }

        status_counts[status] += 1

        if (i + 1) % 25 == 0:
            log(f"Fundamentals progress: {i+1}/{len(tickers)}")

    log(f"Fundamentals complete: "
        f"{status_counts['success']} success | "
        f"{status_counts['no_data']} no_data | "
        f"{status_counts['api_error']} api_error | "
        f"{status_counts['rate_limited']} rate_limited")

    # Warn if systemic failure rate is high
    failure_rate = (status_counts['api_error'] +
                    status_counts['rate_limited']) / max(len(tickers), 1)
    if failure_rate > 0.10:
        log(f"WARNING: High failure rate {failure_rate:.0%} — "
            f"check API status")

    return results
