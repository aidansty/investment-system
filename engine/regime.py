from utils.logger import log
from config.risk import RISK_CONFIG


def _score_condition(is_bullish: bool, is_bearish: bool) -> tuple:
    """Returns (bullish_point, bearish_point) for a single condition."""
    if is_bullish:
        return (1, 0)
    if is_bearish:
        return (0, 1)
    return (0, 0)


def determine_regime(macro_data: dict) -> dict:
    """
    Apply five-condition scoring model to determine market regime.
    Completely mechanical — same inputs always produce same output.

    Conditions:
    1. SPY vs 50-day SMA
    2. SPY 50-day vs 200-day SMA
    3. VIX absolute level (bullish <20, bearish >28)
    4. VIX 5-day trend (bullish if falling, bearish if +15%)
    5. Breadth (bullish >55%, bearish <40%)

    Regime:
        Bullish:  bullish_points >= 3 AND bearish_points <= 1
        Bearish:  bearish_points >= 3 AND bullish_points <= 1
        Neutral:  everything else

    Confidence:
        gap >= 3: High
        gap == 2: Medium
        gap <= 1: Low
    """
    spy_close = macro_data.get("spy_close")
    spy_sma_50 = macro_data.get("spy_sma_50")
    spy_sma_200 = macro_data.get("spy_sma_200")
    vix = macro_data.get("vix")
    vix_5d_avg = macro_data.get("vix_5d_avg")
    breadth_pct = macro_data.get("breadth_pct")

    conditions = {}
    bullish_total = 0
    bearish_total = 0
    degraded = False

    # Condition 1: SPY vs 50-day SMA
    if spy_close and spy_sma_50:
        b, br = _score_condition(
            is_bullish=spy_close > spy_sma_50,
            is_bearish=spy_close < spy_sma_50
        )
        bullish_total += b
        bearish_total += br
        conditions["spy_vs_50d"] = {
            "bullish": bool(b),
            "bearish": bool(br),
            "value": f"${spy_close:.2f} vs SMA ${spy_sma_50:.2f}"
        }

    # Condition 2: Golden/Death cross
    if spy_sma_50 and spy_sma_200:
        b, br = _score_condition(
            is_bullish=spy_sma_50 > spy_sma_200,
            is_bearish=spy_sma_50 < spy_sma_200
        )
        bullish_total += b
        bearish_total += br
        conditions["sma_cross"] = {
            "bullish": bool(b),
            "bearish": bool(br),
            "value": f"50d ${spy_sma_50:.2f} vs 200d ${spy_sma_200:.2f}"
        }

    # Condition 3: VIX absolute level
    if vix:
        b, br = _score_condition(
            is_bullish=vix < 20,
            is_bearish=vix > 28
        )
        bullish_total += b
        bearish_total += br
        conditions["vix_level"] = {
            "bullish": bool(b),
            "bearish": bool(br),
            "value": f"VIX {vix:.1f}"
        }

    # Condition 4: VIX 5-day trend (asymmetric by design)
    if vix and vix_5d_avg:
        vix_change_pct = (vix - vix_5d_avg) / vix_5d_avg
        b, br = _score_condition(
            is_bullish=vix_change_pct < 0,
            is_bearish=vix_change_pct > 0.15
        )
        bullish_total += b
        bearish_total += br
        conditions["vix_trend"] = {
            "bullish": bool(b),
            "bearish": bool(br),
            "value": f"VIX {vix:.1f} vs 5d avg {vix_5d_avg:.1f} ({vix_change_pct*100:+.1f}%)"
        }
    else:
        conditions["vix_trend"] = {
            "bullish": False,
            "bearish": False,
            "value": "VIX 5d history unavailable — neutral"
        }
        degraded = True
        log("WARNING: VIX 5-day average unavailable — regime running on 4 conditions")

    # Condition 5: Breadth
    if breadth_pct is not None:
        b, br = _score_condition(
            is_bullish=breadth_pct > 0.55,
            is_bearish=breadth_pct < 0.40
        )
        bullish_total += b
        bearish_total += br
        conditions["breadth"] = {
            "bullish": bool(b),
            "bearish": bool(br),
            "value": f"{breadth_pct:.1%} above 200d SMA"
        }
    else:
        conditions["breadth"] = {
            "bullish": False,
            "bearish": False,
            "value": "Breadth pending — neutral"
        }
        degraded = True
        log("WARNING: Breadth unavailable — regime running without breadth condition")

    # Determine regime label
    if bullish_total >= 3 and bearish_total <= 1:
        label = "Bullish"
    elif bearish_total >= 3 and bullish_total <= 1:
        label = "Bearish"
    else:
        label = "Neutral"

    # Confidence
    gap = abs(bullish_total - bearish_total)
    if gap >= 3:
        confidence = "High"
    elif gap == 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    regime = {
        "label": label,
        "confidence": confidence,
        "degraded": degraded,
        "bullish_points": bullish_total,
        "bearish_points": bearish_total,
        "conditions": conditions,
        "max_positions": RISK_CONFIG["max_positions"][label],
        "min_cash_pct": RISK_CONFIG["min_cash_pct"][label],
        "stop_loss_pct": (
            RISK_CONFIG["stop_loss_bearish_pct"]
            if label == "Bearish"
            else RISK_CONFIG["stop_loss_normal_pct"]
        )
    }

    log(f"Regime: {label} ({confidence} confidence) "
        f"{'[DEGRADED]' if degraded else ''} | "
        f"Bullish: {bullish_total} | Bearish: {bearish_total} | "
        f"Max positions: {regime['max_positions']}")

    return regime
