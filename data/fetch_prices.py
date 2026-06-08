import os
import json
import yfinance as yf
import warnings
from datetime import datetime
from utils.logger import log

warnings.filterwarnings('ignore')

CACHE_DIR = "data/cache"
CACHE_FILE = os.path.join(CACHE_DIR, "prices.json")
MIN_DAYS_REQUIRED = 200
MIN_UNIVERSE_COVERAGE = 0.90
BATCH_SIZE = 100


def fetch_all_prices(tickers: list) -> dict:
    """
    Download 300 trading days of closing prices for all universe tickers.
    Validates coverage before returning.
    Saves to local cache for downstream signal modules to read.
    Returns dict: {ticker: [float, ...]} oldest to newest.
    Returns None if coverage is below minimum threshold.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    log(f"Fetching 300 days of prices for {len(tickers)} tickers...")

    prices = {}
    failed_tickers = []
    total_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        log(f"Price batch {batch_num}/{total_batches} ({len(batch)} tickers)...")

        try:
            data = yf.download(
                " ".join(batch),
                period="15mo",
                auto_adjust=True,
                progress=False,
                threads=True
            )

            if data.empty:
                log(f"Batch {batch_num} returned empty — marking all as failed")
                failed_tickers.extend(batch)
                continue

            if len(batch) == 1:
                ticker = batch[0]
                series = data["Close"].dropna().tolist()
                if len(series) >= MIN_DAYS_REQUIRED:
                    prices[ticker] = series
                else:
                    log(f"{ticker} insufficient history: {len(series)} days")
                    failed_tickers.append(ticker)
            else:
                if hasattr(data["Close"], "columns"):
                    returned = set(data["Close"].columns.tolist())
                    for ticker in batch:
                        if ticker not in returned:
                            failed_tickers.append(ticker)
                        else:
                            series = data["Close"][ticker].dropna().tolist()
                            if len(series) >= MIN_DAYS_REQUIRED:
                                prices[ticker] = series
                            else:
                                log(f"{ticker} insufficient history: {len(series)} days")
                                failed_tickers.append(ticker)
                else:
                    failed_tickers.extend(batch)

        except Exception as e:
            log(f"Batch {batch_num} error: {e} — marking batch as failed")
            failed_tickers.extend(batch)
            continue

    # Validate coverage
    coverage = len(prices) / len(tickers)
    log(f"Coverage: {len(prices)}/{len(tickers)} tickers ({coverage:.1%})")

    # Log failed tickers
    if failed_tickers:
        log(f"Failed tickers ({len(failed_tickers)}): {sorted(failed_tickers)}")
    else:
        log("All tickers returned clean data")

    if coverage < MIN_UNIVERSE_COVERAGE:
        log(f"ABORT: Coverage {coverage:.1%} below {MIN_UNIVERSE_COVERAGE:.0%} minimum")
        log("Daily scan cancelled — insufficient price data")
        return None

    # Save to cache with metadata
    cache_data = {
        "timestamp": datetime.now().isoformat(),
        "ticker_count": len(prices),
        "failed_count": len(failed_tickers),
        "failed_tickers": sorted(failed_tickers),
        "coverage_pct": round(coverage * 100, 1),
        "prices": prices
    }

    with open(CACHE_FILE, "w") as f:
        json.dump(cache_data, f)

    log(f"Price cache saved — {len(prices)} tickers, {len(failed_tickers)} failed")
    return prices


def load_price_cache() -> dict:
    """
    Load price data from local cache.
    Called by signal modules instead of re-downloading.
    Returns the prices dict or None if cache missing.
    """
    if not os.path.exists(CACHE_FILE):
        log("ERROR: Price cache not found")
        return None

    with open(CACHE_FILE, "r") as f:
        cache_data = json.load(f)

    log(f"Price cache loaded: {cache_data['ticker_count']} tickers | "
        f"{cache_data['failed_count']} failed | "
        f"coverage {cache_data['coverage_pct']}% | "
        f"fetched {cache_data['timestamp']}")

    if cache_data["failed_tickers"]:
        log(f"Known failed tickers: {cache_data['failed_tickers']}")

    return cache_data["prices"]


def fetch_current_prices(tickers: list) -> dict:
    """
    Fetch real-time current price for a small list of tickers.
    Used only for open position P&L calculations.
    Not cached — always fresh.
    Returns dict: {ticker: float}
    """
    if not tickers:
        return {}

    current = {}
    try:
        data = yf.download(
            " ".join(tickers),
            period="1d",
            auto_adjust=True,
            progress=False,
            threads=True
        )

        if data.empty:
            return {}

        if len(tickers) == 1:
            ticker = tickers[0]
            if not data.empty:
                current[ticker] = float(data["Close"].iloc[-1])
        else:
            if hasattr(data["Close"], "columns"):
                for ticker in tickers:
                    if ticker in data["Close"].columns:
                        val = data["Close"][ticker].dropna()
                        if not val.empty:
                            current[ticker] = float(val.iloc[-1])

    except Exception as e:
        log(f"Current price fetch error: {e}")

    return current
