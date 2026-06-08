from utils.logger import log
from config.signals import SIGNAL_CONFIG


def calculate_relative_strength(prices: dict) -> dict:
    """
    Calculate 63-day relative strength for all tickers vs SPY.
    RS = stock 63-day return minus SPY 63-day return (excess return).
    Only tickers that outperformed SPY (RS > 0) are included in output.
    Returns dict: {
        ticker: {
            "rs_score": float (excess return vs SPY, percentage points),
            "ticker_return": float,
            "spy_return": float,
            "qualified": bool
        }
    }
    """
    lookback = SIGNAL_CONFIG["rs_lookback_days"]

    if "SPY" not in prices:
        log("ERROR: SPY not in price data — cannot calculate relative strength")
        return {}

    spy_prices = prices["SPY"]
    if len(spy_prices) < lookback:
        log(f"ERROR: SPY insufficient history: {len(spy_prices)} days")
        return {}

    spy_return = (spy_prices[-1] / spy_prices[-lookback]) - 1

    rs_scores = {}

    for ticker, ticker_prices in prices.items():
        if ticker == "SPY":
            continue
        if len(ticker_prices) < lookback:
            continue

        try:
            ticker_return = (ticker_prices[-1] / ticker_prices[-lookback]) - 1
            rs_score = ticker_return - spy_return

            rs_scores[ticker] = {
                "rs_score": round(rs_score * 100, 2),
                "ticker_return": round(ticker_return * 100, 2),
                "spy_return": round(spy_return * 100, 2),
                "qualified": rs_score > 0
            }
        except Exception as e:
            log(f"RS calculation error for {ticker}: {e}")
            continue

    qualified_count = sum(1 for t in rs_scores if rs_scores[t]["qualified"])

    log(f"RS calculated: {len(rs_scores)} tickers scored | "
        f"SPY 63d return: {spy_return*100:.1f}% | "
        f"Outperforming SPY: {qualified_count} tickers")

    return rs_scores


def get_rs_qualified(rs_scores: dict) -> list:
    """
    Return tickers that outperformed SPY over the 63-day lookback.
    Sorted by RS score descending — strongest momentum first.
    """
    qualified = [
        ticker for ticker, data in rs_scores.items()
        if data["qualified"]
    ]

    qualified.sort(key=lambda t: rs_scores[t]["rs_score"], reverse=True)

    log(f"RS qualified: {len(qualified)} tickers outperforming SPY")
    return qualified
