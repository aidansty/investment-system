import warnings
warnings.filterwarnings("ignore")

from config.signals import SIGNAL_CONFIG
from utils.logger import log


def calculate_atr(prices: list, period: int = 14) -> float | None:
    """
    Calculate Average True Range as percentage of current price.
    Uses simplified ATR (high-low range from daily closes as proxy
    since we only have closing prices, not OHLC).
    Falls back to standard deviation of daily returns * sqrt(period).
    """
    if len(prices) < period + 1:
        return None

    try:
        recent = prices[-(period + 1):]
        daily_ranges = []
        for i in range(1, len(recent)):
            high = max(recent[i], recent[i-1])
            low = min(recent[i], recent[i-1])
            true_range = (high - low) / recent[i-1]
            daily_ranges.append(true_range)

        if not daily_ranges:
            return None

        atr = sum(daily_ranges) / len(daily_ranges)
        return atr

    except Exception:
        return None


def calculate_atr_stop(current_price: float, atr_pct: float) -> dict:
    """
    Calculate ATR-based stop loss price and percentage.
    Formula: Stop % = MIN(ceiling, MAX(floor, multiplier x ATR))
    Returns dict with stop_pct and stop_price.
    """
    multiplier = SIGNAL_CONFIG["atr_multiplier"]
    floor_pct = SIGNAL_CONFIG["atr_stop_floor_pct"] / 100
    ceiling_pct = SIGNAL_CONFIG["atr_stop_ceiling_pct"] / 100

    raw_stop_pct = atr_pct * multiplier
    stop_pct = min(ceiling_pct, max(floor_pct, raw_stop_pct))
    stop_price = current_price * (1 - stop_pct)

    return {
        "atr_pct": round(atr_pct * 100, 2),
        "stop_pct": round(stop_pct * 100, 2),
        "stop_price": round(stop_price, 2),
    }


def calculate_freshness(prices: list) -> dict:
    """
    Calculate 5-day and 10-day returns and classify entry freshness.

    Classifications:
    - FRESH: 5-day return below extended threshold
    - EXTENDED: 5-day return between extended and watch thresholds
    - WATCH: 5-day return above watch threshold (remove from Strong)
    - PULLING BACK: 5-day return below pullback threshold (potential better entry)
    """
    if len(prices) < 11:
        return {
            "five_day_return": None,
            "ten_day_return": None,
            "freshness": "Fresh",
            "freshness_note": "Insufficient history"
        }

    try:
        current = prices[-1]
        price_5d_ago = prices[-6]
        price_10d_ago = prices[-11]

        five_day_return = ((current - price_5d_ago) / price_5d_ago) * 100
        ten_day_return = ((current - price_10d_ago) / price_10d_ago) * 100

        extended_threshold = SIGNAL_CONFIG["freshness_extended_pct"]
        watch_threshold = SIGNAL_CONFIG["freshness_watch_pct"]
        pullback_threshold = SIGNAL_CONFIG["freshness_pullback_pct"]

        if five_day_return > watch_threshold:
            freshness = "Watch"
            note = f"Up {five_day_return:.1f}% in 5 days — wait for pullback"
        elif five_day_return > extended_threshold:
            freshness = "Extended"
            note = f"Up {five_day_return:.1f}% in 5 days — extended but tradeable"
        elif five_day_return < pullback_threshold:
            freshness = "Pulling Back"
            note = f"Down {five_day_return:.1f}% in 5 days while 63d momentum positive"
        else:
            freshness = "Fresh"
            note = "Clean entry — no short-term extension"

        return {
            "five_day_return": round(five_day_return, 2),
            "ten_day_return": round(ten_day_return, 2),
            "freshness": freshness,
            "freshness_note": note,
        }

    except Exception as e:
        return {
            "five_day_return": None,
            "ten_day_return": None,
            "freshness": "Fresh",
            "freshness_note": f"Calculation error: {e}"
        }


def calculate_earnings_reaction(earnings_history: list, prices: dict, ticker: str) -> dict:
    """
    Calculate average 1-day post-earnings return across last 4 quarters.
    Uses earnings dates from history and price cache to find next-day return.

    Observation only — logged but does not hard-gate or resize positions.
    """
    if not earnings_history or len(earnings_history) < 2:
        return {
            "avg_post_earnings_return": None,
            "reaction_quality": "Insufficient Data",
            "quarters_checked": 0,
        }

    ticker_prices = prices.get(ticker, [])
    if not ticker_prices or len(ticker_prices) < 30:
        return {
            "avg_post_earnings_return": None,
            "reaction_quality": "Insufficient Data",
            "quarters_checked": 0,
        }

    # We cannot easily map earnings dates to price indices without date index
    # Use earnings surprise magnitude as proxy for reaction quality
    # Future enhancement: add date-indexed price lookup
    reactions = []
    for q in earnings_history[:4]:
        surprise_pct = q.get("surprise_pct", 0) or 0
        beat = q.get("beat", False)
        # Approximate reaction: strong beats with high surprise = positive reaction
        # This is a proxy until we have date-indexed prices
        if beat and surprise_pct > 5:
            reactions.append(3.5)   # Approximate strong positive
        elif beat and surprise_pct > 0:
            reactions.append(1.0)   # Approximate mild positive
        else:
            reactions.append(-2.0)  # Approximate negative

    if not reactions:
        return {
            "avg_post_earnings_return": None,
            "reaction_quality": "Insufficient Data",
            "quarters_checked": 0,
        }

    avg_return = sum(reactions) / len(reactions)

    strong_threshold = SIGNAL_CONFIG["reaction_strong_threshold"]
    sells_news_threshold = SIGNAL_CONFIG["reaction_sells_news_threshold"]

    if avg_return > strong_threshold:
        quality = "Strong"
    elif avg_return < sells_news_threshold:
        quality = "Sells News"
    else:
        quality = "Neutral"

    return {
        "avg_post_earnings_return": round(avg_return, 2),
        "reaction_quality": quality,
        "quarters_checked": len(reactions),
    }


def get_conviction_tier(composite_score: float) -> str:
    """
    Classify composite score into conviction tier.
    Observation only — does NOT currently influence position sizing.
    After 30-trade review, activate if Tier A outperforms Tier C.
    """
    tier_a = SIGNAL_CONFIG["conviction_tier_a"]
    tier_b = SIGNAL_CONFIG["conviction_tier_b"]

    if composite_score >= tier_a:
        return "A"
    elif composite_score >= tier_b:
        return "B"
    else:
        return "C"


def get_vix_regime(vix: float, vix_5d_avg: float | None) -> dict:
    """
    Classify VIX into regime.
    Observation only — shown in briefing header but does NOT auto-resize positions.
    After 30-trade review, activate modifiers if regime correlated with outcomes.
    """
    green_threshold = SIGNAL_CONFIG["vix_green_threshold"]
    yellow_threshold = SIGNAL_CONFIG["vix_yellow_threshold"]

    if vix < green_threshold:
        regime = "Green"
    elif vix < yellow_threshold:
        regime = "Yellow"
    else:
        regime = "Red"

    # VIX trend modifier (observation only)
    trend = "Flat"
    if vix_5d_avg:
        change_pct = (vix - vix_5d_avg) / vix_5d_avg * 100
        if change_pct > 20:
            trend = "Spiking"
        elif change_pct > 5:
            trend = "Rising"
        elif change_pct < -5:
            trend = "Falling"

    return {
        "vix_regime": regime,
        "vix_trend": trend,
    }


def calculate_profit_targets(
    current_price: float,
    atr_pct: float,
    catalyst_date: str | None,
    today: str
) -> dict:
    """
    Calculate profit-taking levels and exit dates.
    Tier 1: Take half off at +17.5%
    Pre-earnings exit: 3 trading days before catalyst
    Time stop: 20 trading days from entry
    """
    tier1_target = round(current_price * (1 + SIGNAL_CONFIG["profit_target_tier1_pct"] / 100), 2)
    atr_trail_stop_pct = atr_pct * SIGNAL_CONFIG["atr_trail_multiplier"]

    # Calculate pre-earnings exit date
    pre_earnings_exit_date = None
    if catalyst_date:
        try:
            from datetime import date, timedelta
            from utils.market_calendar import is_trading_day

            cat_date = date.fromisoformat(catalyst_date)
            exit_days_needed = SIGNAL_CONFIG["pre_earnings_exit_days"]

            # Count back trading days from catalyst date
            exit_date = cat_date
            days_counted = 0
            while days_counted < exit_days_needed:
                exit_date -= timedelta(days=1)
                if is_trading_day(exit_date):
                    days_counted += 1

            pre_earnings_exit_date = exit_date.isoformat()
        except Exception:
            pass

    return {
        "tier1_target_price": tier1_target,
        "tier1_target_pct": SIGNAL_CONFIG["profit_target_tier1_pct"],
        "atr_trail_stop_pct": round(atr_trail_stop_pct * 100, 2),
        "pre_earnings_exit_date": pre_earnings_exit_date,
        "time_stop_days": SIGNAL_CONFIG["time_stop_days"],
    }
