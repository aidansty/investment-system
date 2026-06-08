from utils.logger import log
from config.signals import SIGNAL_CONFIG


def calculate_annualized_volatility(prices: list, period: int = 63) -> float | None:
    """
    Calculate annualized volatility from daily returns.
    Used to normalize RS score — separates steady institutional trends
    from erratic speculative spikes that inflate raw momentum scores.
    """
    if len(prices) < period + 1:
        return None

    recent = prices[-(period + 1):]
    daily_returns = []
    for i in range(1, len(recent)):
        if recent[i-1] > 0:
            daily_returns.append((recent[i] - recent[i-1]) / recent[i-1])

    if len(daily_returns) < period // 2:
        return None

    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean) ** 2 for r in daily_returns) / len(daily_returns)
    daily_vol = variance ** 0.5
    annualized = daily_vol * (252 ** 0.5)

    # Guard against zero or near-zero volatility
    return annualized if annualized > 0.01 else None


def calculate_relative_strength(prices: dict) -> dict:
    """
    Calculate volatility-normalized relative strength for all tickers vs SPY.

    Formula: (stock_return - spy_return) / annualized_volatility

    Dividing by volatility separates steady institutional accumulation trends
    from high-beta speculative spikes. A stock that returned 40% steadily
    scores higher than one that returned 40% erratically.

    Only tickers that outperformed SPY (RS > 0 before normalization) qualify.

    Returns dict: {
        ticker: {
            "rs_score": float (volatility-normalized excess return),
            "raw_rs": float (raw excess return percentage points),
            "ticker_return": float,
            "spy_return": float,
            "volatility": float,
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
            raw_excess = ticker_return - spy_return

            # Hard gate: must outperform SPY
            if raw_excess <= 0:
                continue

            # Volatility normalization
            vol = calculate_annualized_volatility(ticker_prices, lookback)

            if vol:
                rs_score = raw_excess / vol
            else:
                # Fallback to raw excess if volatility unavailable
                rs_score = raw_excess * 100

            rs_scores[ticker] = {
                "rs_score": round(rs_score, 4),
                "raw_rs": round(raw_excess * 100, 2),
                "ticker_return": round(ticker_return * 100, 2),
                "spy_return": round(spy_return * 100, 2),
                "volatility": round(vol, 4) if vol else None,
                "qualified": True
            }

        except Exception as e:
            log(f"RS calculation error for {ticker}: {e}")
            continue

    qualified_count = len(rs_scores)
    log(f"RS calculated: {len(prices) - 1} tickers scored | "
        f"SPY 63d return: {spy_return*100:.1f}% | "
        f"Outperforming SPY: {qualified_count} tickers (vol-normalized)")

    return rs_scores


def get_rs_qualified(rs_scores: dict) -> list:
    """
    Return tickers that outperformed SPY, sorted by vol-normalized RS score.
    Strongest steady momentum first.
    """
    qualified = [t for t, d in rs_scores.items() if d["qualified"]]
    qualified.sort(key=lambda t: rs_scores[t]["rs_score"], reverse=True)
    log(f"RS qualified: {len(qualified)} tickers outperforming SPY")
    return qualified
