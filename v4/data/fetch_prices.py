import time
import yfinance as yf
import pandas as pd
from datetime import date, timedelta
from v4.utils.logger import log
from v4.config.settings import INDUSTRY_ETF_MAP, BENCHMARK_ETF, ALL_INDUSTRY_ETFS, MOMENTUM_LOOKBACK_DAYS, ALL_STOCKS


def fetch_etf_prices(lookback_days: int = 90) -> dict:
    """
    Fetch price history for all 25 industry ETFs plus SPY benchmark.
    Returns dict: {ticker: [price_list]} sorted oldest to newest.
    """
    tickers = ALL_INDUSTRY_ETFS + [BENCHMARK_ETF]
    # Remove duplicates
    tickers = list(set(tickers))

    log(f"Fetching prices for {len(tickers)} ETFs ({lookback_days} days)...")

    # "3mo" period was returning exactly 62 trading days — 1 day short of the
    # 63-day MOMENTUM_LOOKBACK_DAYS threshold, causing every single ETF to fail.
    # Extended to "4mo" for a reliable safety margin, same fix applied to stocks.
    period_map = {
        63:  "4mo",
        90:  "4mo",
        126: "6mo",
        252: "1y",
    }
    period = period_map.get(lookback_days, "4mo")

    results = {}
    failed = []

    try:
        data = yf.download(
            tickers,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=True
        )

        if data.empty:
            log("ERROR: No ETF price data returned")
            return {}

        close = data["Close"] if "Close" in data.columns else data

        for ticker in tickers:
            try:
                if ticker in close.columns:
                    series = close[ticker].dropna()
                    if len(series) >= MOMENTUM_LOOKBACK_DAYS:
                        results[ticker] = series.tolist()
                    else:
                        log(f"{ticker}: insufficient history ({len(series)} days)")
                        failed.append(ticker)
                else:
                    failed.append(ticker)
            except Exception as e:
                log(f"{ticker} price error: {e}")
                failed.append(ticker)

    except Exception as e:
        log(f"ETF price fetch error: {e}")
        return {}

    coverage = len(results) / len(tickers) * 100
    log(f"ETF prices: {len(results)}/{len(tickers)} fetched ({coverage:.0f}% coverage)")
    if failed:
        log(f"Failed ETFs: {failed}")

    return results


def fetch_current_etf_prices(tickers: list) -> dict:
    """
    Fetch current prices for a list of ETF tickers.
    Returns dict: {ticker: current_price}
    """
    results = {}
    try:
        data = yf.download(
            tickers,
            period="2d",
            auto_adjust=True,
            progress=False,
            threads=True
        )
        close = data["Close"] if "Close" in data.columns else data
        for ticker in tickers:
            if ticker in close.columns:
                series = close[ticker].dropna()
                if not series.empty:
                    results[ticker] = round(float(series.iloc[-1]), 2)
    except Exception as e:
        log(f"Current price fetch error: {e}")
    return results


def fetch_stock_prices(tickers: list, lookback_days: int = 90) -> dict:
    """
    Fetch price history for individual stocks within top industries.
    Used for stock-level analysis after industry selection.
    Uses "4mo" period (not "3mo") to reliably get 63+ trading days —
    "3mo" calendar days often yields only ~60-62 trading days, which was
    silently failing the >=63 day requirement in score_stock_leaders().
    """
    if not tickers:
        return {}

    log(f"Fetching stock prices for {len(tickers)} tickers...")

    period_map = {63: "4mo", 90: "4mo", 126: "6mo", 252: "1y"}
    period = period_map.get(lookback_days, "4mo")

    results = {}
    skipped_too_short = []
    # Batch in groups of 50 to avoid rate limits
    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            data = yf.download(
                batch,
                period=period,
                auto_adjust=True,
                progress=False,
                threads=True
            )
            if data.empty:
                continue
            close = data["Close"] if "Close" in data.columns else data
            for ticker in batch:
                if ticker in close.columns:
                    series = close[ticker].dropna()
                    if len(series) >= 63:
                        results[ticker] = series.tolist()
                    elif len(series) >= 30:
                        skipped_too_short.append(ticker)
        except Exception as e:
            log(f"Stock price batch error: {e}")
    if skipped_too_short:
        log(f"Stock prices: {len(skipped_too_short)} tickers had 30-62 days (below 63-day threshold), excluded: {skipped_too_short[:10]}")
        time.sleep(0.5)

    log(f"Stock prices fetched: {len(results)}/{len(tickers)}")
    return results
