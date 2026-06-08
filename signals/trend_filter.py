from utils.logger import log
from config.signals import SIGNAL_CONFIG


def passes_trend_filter(prices: list) -> bool:
    """
    Returns True if the stock is currently above its 50-day SMA.
    Eliminates downtrending stocks regardless of RS score.
    """
    period = SIGNAL_CONFIG["trend_sma_period"]

    if len(prices) < period:
        return False

    sma_50 = sum(prices[-period:]) / period
    current_price = prices[-1]

    return current_price > sma_50


def apply_trend_filter(prices: dict, candidates: list) -> list:
    """
    Apply 50-day SMA trend filter to a list of RS-qualified tickers.
    Returns only tickers currently in an uptrend.
    """
    passed = []
    failed = []

    for ticker in candidates:
        if ticker not in prices:
            failed.append(ticker)
            continue

        if passes_trend_filter(prices[ticker]):
            passed.append(ticker)
        else:
            failed.append(ticker)

    log(f"Trend filter: {len(passed)} passed | {len(failed)} eliminated")
    return passed
