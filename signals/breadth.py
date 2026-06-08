from utils.logger import log


def calculate_breadth(prices: dict) -> float | None:
    """
    Calculate market breadth: percentage of universe stocks
    currently trading above their 200-day simple moving average.

    This is a key regime health indicator — a broad rally
    is healthier than one driven by a handful of large caps.

    Returns float between 0.0 and 1.0, or None if insufficient data.
    """
    period = 200
    above = 0
    below = 0
    skipped = 0

    for ticker, ticker_prices in prices.items():
        if ticker == "SPY":
            continue
        if len(ticker_prices) < period:
            skipped += 1
            continue

        sma_200 = sum(ticker_prices[-period:]) / period
        current = ticker_prices[-1]

        if current > sma_200:
            above += 1
        else:
            below += 1

    total = above + below
    if total == 0:
        log("ERROR: No tickers had sufficient history for breadth calculation")
        return None

    breadth_pct = above / total
    log(f"Breadth: {above}/{total} stocks above 200d SMA ({breadth_pct:.1%})")

    if skipped > 0:
        log(f"Breadth: {skipped} tickers skipped (insufficient history)")

    return breadth_pct
