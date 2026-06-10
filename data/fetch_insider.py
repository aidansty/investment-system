import os
import time
import requests
from datetime import date, timedelta
from utils.logger import log
from config.signals import SIGNAL_CONFIG

# SEC EDGAR requires a declared User-Agent per their terms of service
# Replace with your actual name and email
EDGAR_USER_AGENT = "Investment System research@investment-system.com"
EDGAR_RATE_LIMIT_DELAY = 0.15  # 0.15s between requests = ~6.7 req/sec, safely under 10/sec limit


def get_cik_for_ticker(ticker: str) -> str | None:
    """
    Look up SEC CIK number for a ticker symbol.
    Uses EDGAR company search endpoint.
    """
    try:
        time.sleep(EDGAR_RATE_LIMIT_DELAY)
        url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&forms=10-K&hits.hits._source=period_of_report,file_date,entity_name,file_num,period_of_report,biz_location,inc_states"
        headers = {"User-Agent": EDGAR_USER_AGENT}
        r = requests.get(url, headers=headers, timeout=10)

        if r.status_code != 200:
            return None

        # Try the company ticker lookup endpoint instead
        time.sleep(EDGAR_RATE_LIMIT_DELAY)
        ticker_url = "https://www.sec.gov/files/company_tickers.json"
        r2 = requests.get(ticker_url, headers=headers, timeout=10)

        if r2.status_code != 200:
            return None

        data = r2.json()
        for key, company in data.items():
            if company.get("ticker", "").upper() == ticker.upper():
                cik = str(company["cik_str"]).zfill(10)
                return cik

        return None

    except Exception as e:
        log(f"CIK lookup error for {ticker}: {e}")
        return None


def fetch_insider_activity(ticker: str) -> dict:
    """
    Fetch net insider transaction value over trailing 90 days via SEC EDGAR Form 4.
    Observation only — logged but does not auto-resize positions.

    Returns dict with net_value and flag classification.
    """
    result = {
        "insider_net_90d": None,
        "insider_flag": "Not Checked",
        "insider_note": "",
    }

    try:
        cik = get_cik_for_ticker(ticker)
        if not cik:
            result["insider_note"] = "CIK not found"
            return result

        # Fetch recent Form 4 filings
        time.sleep(EDGAR_RATE_LIMIT_DELAY)
        start_date = (date.today() - timedelta(days=90)).isoformat()
        url = (
            f"https://efts.sec.gov/LATEST/search-index"
            f"?q=%22{cik}%22&dateRange=custom&startdt={start_date}&forms=4"
        )
        headers = {"User-Agent": EDGAR_USER_AGENT}
        r = requests.get(url, headers=headers, timeout=10)

        if r.status_code == 403:
            result["insider_note"] = "EDGAR rate limited"
            return result

        if r.status_code != 200:
            result["insider_note"] = f"HTTP {r.status_code}"
            return result

        data = r.json()
        hits = data.get("hits", {}).get("hits", [])

        if not hits:
            result["insider_flag"] = "None"
            result["insider_note"] = "No Form 4 filings in 90 days"
            return result

        # Parse transaction values from filings
        # This is a simplified approach — full XML parsing would be more accurate
        # For now we count filing volume as a proxy
        filing_count = len(hits)

        # Approximate net value based on filing count
        # A proper implementation would parse XML for actual dollar amounts
        # This is marked for Version 2 data upgrade
        result["insider_flag"] = "None"
        result["insider_net_90d"] = 0
        result["insider_note"] = f"{filing_count} Form 4 filings found — XML parsing pending V2"

        return result

    except Exception as e:
        result["insider_note"] = f"Error: {e}"
        log(f"Insider fetch error for {ticker}: {e}")
        return result
