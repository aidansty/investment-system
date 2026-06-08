import os
import requests
import yfinance as yf
import warnings
from utils.logger import log

warnings.filterwarnings("ignore")

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
FRED_KEY = os.environ.get("FRED_KEY", "")


def fetch_vix():
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol=^VIX&token={FINNHUB_KEY}"
        r = requests.get(url, timeout=10)
        data = r.json()
        vix = data.get("c")
        if vix and vix > 0:
            log(f"VIX fetched: {vix}")
            return float(vix)
        return _fetch_vix_fred()
    except Exception as e:
        log(f"VIX fetch error: {e}")
        return _fetch_vix_fred()


def _fetch_vix_fred():
    try:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id=VIXCLS&api_key={FRED_KEY}"
            "&sort_order=desc&limit=1&file_type=json"
        )
        r = requests.get(url, timeout=10)
        obs = r.json().get("observations", [])
        if obs and obs[0].get("value") != ".":
            vix = float(obs[0]["value"])
            log(f"VIX fetched from FRED: {vix}")
            return vix
    except Exception as e:
        log(f"VIX FRED fallback error: {e}")
    return None


def fetch_vix_history(days=10):
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="1mo")
        if hist.empty:
            return None
        closes = hist["Close"].dropna().tolist()
        log(f"VIX history fetched: {len(closes)} days")
        return closes[-days:] if len(closes) >= days else closes
    except Exception as e:
        log(f"VIX history fetch error: {e}")
        return None


def fetch_spy_prices():
    try:
        spy = yf.Ticker("SPY")
        hist = spy.history(period="11mo")
        if hist.empty:
            return None
        closes = hist["Close"].tolist()
        log(f"SPY prices fetched: {len(closes)} days")
        return closes
    except Exception as e:
        log(f"SPY price fetch error: {e}")
        return None


def calculate_sma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def fetch_recent_economic_releases():
    """
    Check recent FRED observation dates for high-impact macro series.
    Returns recently released macroeconomic data from the last 1-2 days.
    This is NOT a forward-looking calendar - it identifies what just came out.
    """
    HIGH_IMPACT_SERIES = {
        "CPIAUCSL": "CPI (Consumer Price Index)",
        "PPIACO": "PPI (Producer Price Index)",
        "UNRATE": "Unemployment Rate",
        "PAYEMS": "Non-Farm Payrolls",
        "FEDFUNDS": "Federal Funds Rate",
        "GDP": "GDP Growth Rate",
        "RSAFS": "Retail Sales",
    }

    try:
        from datetime import datetime
        today = datetime.now().date()
        releases = []

        for series_id, name in HIGH_IMPACT_SERIES.items():
            try:
                url = (
                    "https://api.stlouisfed.org/fred/series/observations"
                    f"?series_id={series_id}&api_key={FRED_KEY}"
                    "&sort_order=desc&limit=1&file_type=json"
                )
                r = requests.get(url, timeout=5)
                if r.status_code != 200:
                    continue
                obs = r.json().get("observations", [])
                if not obs:
                    continue
                latest_date_str = obs[0].get("date", "")
                if not latest_date_str:
                    continue
                latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d").date()
                days_ago = (today - latest_date).days
                if days_ago <= 1:
                    releases.append({
                        "name": name,
                        "date": latest_date_str,
                        "status": "Released today" if days_ago == 0 else "Released yesterday"
                    })
            except Exception:
                continue

        if releases:
            log(f"Economic releases: {len(releases)} recent releases found")
        else:
            log("Economic releases: none today")

        return releases

    except Exception as e:
        log(f"Economic releases fetch error: {e}")
        return []


def fetch_macro_data():
    """
    Fetch all macro data needed for regime detection and daily briefing.
    Returns structured dict or None if critical data missing.
    """
    log("Fetching macro data...")

    spy_prices = fetch_spy_prices()
    if not spy_prices or len(spy_prices) < 200:
        log("ERROR: Insufficient SPY price history")
        return None

    vix = fetch_vix()
    if vix is None:
        log("WARNING: Could not fetch VIX — using fallback value of 20.0")
        log("Regime will be marked as degraded")
        vix = 20.0  # Neutral assumption — neither bullish nor bearish

    vix_history = fetch_vix_history(days=10)
    vix_5d_avg = None
    if vix_history and len(vix_history) >= 5:
        vix_5d_avg = sum(vix_history[-5:]) / 5
        log(f"VIX 5-day average: {vix_5d_avg:.2f}")

    spy_sma_50 = calculate_sma(spy_prices, 50)
    spy_sma_200 = calculate_sma(spy_prices, 200)
    spy_close = spy_prices[-1]

    if spy_sma_50 is None or spy_sma_200 is None:
        log("ERROR: Could not calculate SMAs")
        return None

    economic_releases = fetch_recent_economic_releases()

    macro = {
        "spy_close": spy_close,
        "spy_sma_50": spy_sma_50,
        "spy_sma_200": spy_sma_200,
        "vix": vix,
        "vix_5d_avg": vix_5d_avg,
        "breadth_pct": None,
        "economic_calendar": economic_releases,
    }

    vix_5d_str = f"{vix_5d_avg:.2f}" if vix_5d_avg else "N/A"
    log(f"Macro ready - SPY: ${spy_close:.2f} | 50d: ${spy_sma_50:.2f} | 200d: ${spy_sma_200:.2f} | VIX: {vix:.1f} | VIX 5d avg: {vix_5d_str}")

    return macro
