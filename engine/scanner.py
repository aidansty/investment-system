from utils.logger import log
from config.signals import SIGNAL_CONFIG
from config.risk import RISK_CONFIG
from signals.relative_strength import calculate_relative_strength, get_rs_qualified
from signals.trend_filter import apply_trend_filter
from signals.earnings_proxy import apply_earnings_scoring
from signals.catalyst import apply_catalyst_scoring

# Composite score weights
# score = (rs_normalized * 0.40) + (earnings_score * 0.35) + (catalyst_score * 0.25)
# First calibration review: after 30 completed trades.
RS_WEIGHT = 0.40
EARNINGS_WEIGHT = 0.35
CATALYST_WEIGHT = 0.25

STRONG_THRESHOLD = 0.65
DEVELOPING_THRESHOLD = 0.45


def _normalize_rs_scores(rs_scores, qualified):
    if not qualified:
        return {}
    scores = [rs_scores[t]["rs_score"] for t in qualified]
    min_score = min(scores)
    max_score = max(scores)
    score_range = max_score - min_score
    normalized = {}
    for ticker in qualified:
        raw = rs_scores[ticker]["rs_score"]
        normalized[ticker] = 1.0 if score_range == 0 else (raw - min_score) / score_range
    return normalized


def _get_missing_signals(earnings_data, catalyst_data, composite):
    """
    Produce a plain English explanation of why a candidate is Developing
    rather than Strong. Every candidate gets an explicit reason — never Unknown.
    """
    missing = []

    if earnings_data is None:
        missing.append("No earnings history available")
    elif not earnings_data.get("qualifies", False):
        streak = earnings_data.get("streak", 0)
        if streak == 0:
            missing.append("No consecutive earnings beats")
        else:
            needed = SIGNAL_CONFIG["min_consecutive_beats"]
            missing.append(f"Earnings streak too short ({streak} beat, need {needed})")

    if not catalyst_data.get("has_catalyst", False):
        missing.append("No confirmed catalyst in 5-42 day window")

    if composite < STRONG_THRESHOLD and composite >= DEVELOPING_THRESHOLD:
        if not missing:
            missing.append(f"Composite score {composite:.3f} below Strong threshold ({STRONG_THRESHOLD})")

    return ", ".join(missing) if missing else "Below composite threshold"


def run_full_scan(prices, fundamentals, regime):
    """
    Run the complete two-stage candidate identification pipeline.

    Composite score formula:
        score = (rs_normalized * 0.40) + (earnings_score * 0.35) + (catalyst_score * 0.25)
    """
    log("=== Starting full universe scan ===")

    rs_scores = calculate_relative_strength(prices)
    rs_qualified = get_rs_qualified(rs_scores)
    trend_qualified = apply_trend_filter(prices, rs_qualified)

    log(f"Stage 1 complete: {len(trend_qualified)} technically qualified")
    log(f"Coverage checkpoint: RS qualified={len(rs_qualified)} | Trend qualified={len(trend_qualified)}")

    if not trend_qualified:
        log("No technically qualified candidates — scan complete")
        return _empty_result(regime)

    earnings_scored, earnings_diagnostics = apply_earnings_scoring(fundamentals, trend_qualified)
    catalyst_scored = apply_catalyst_scoring(fundamentals, trend_qualified)
    rs_normalized = _normalize_rs_scores(rs_scores, trend_qualified)

    candidates = []

    for ticker in trend_qualified:
        rs_norm = rs_normalized.get(ticker, 0.0)
        earnings_data = earnings_scored.get(ticker)
        catalyst_data = catalyst_scored.get(ticker, {})

        e_score = earnings_data["earnings_score"] if earnings_data else 0.0
        c_score = catalyst_data.get("catalyst_score", 0.0)

        composite = (
            rs_norm * RS_WEIGHT +
            e_score * EARNINGS_WEIGHT +
            c_score * CATALYST_WEIGHT
        )

        # Hard gate: zero beats go to Watch
        qualifies = earnings_data is not None and earnings_data.get("qualifies", False)

        if not qualifies:
            tier = "Watch"
            missing = _get_missing_signals(earnings_data, catalyst_data, composite)
        elif composite >= STRONG_THRESHOLD:
            tier = "Strong"
            missing = "None — all signals present"
        elif composite >= DEVELOPING_THRESHOLD:
            tier = "Developing"
            missing = _get_missing_signals(earnings_data, catalyst_data, composite)
        else:
            tier = "Watch"
            missing = _get_missing_signals(earnings_data, catalyst_data, composite)

        candidates.append({
            "ticker": ticker,
            "tier": tier,
            "composite_score": round(composite, 3),
            "rs_score": rs_scores[ticker]["rs_score"],
            "rs_normalized": round(rs_norm, 3),
            "rs_return": rs_scores[ticker]["ticker_return"],
            "earnings_score": e_score,
            "beat_streak": earnings_data["streak"] if earnings_data else 0,
            "catalyst_score": c_score,
            "has_catalyst": catalyst_data.get("has_catalyst", False),
            "days_to_catalyst": catalyst_data.get("days_to_catalyst"),
            "catalyst_date": catalyst_data.get("catalyst_date"),
            "catalyst_type": catalyst_data.get("catalyst_type", "none"),
            "spy_return": rs_scores[ticker]["spy_return"],
            "missing_signal": missing,
        })

    candidates.sort(key=lambda x: x["composite_score"], reverse=True)

    strong = [c for c in candidates if c["tier"] == "Strong"]
    developing = [c for c in candidates if c["tier"] == "Developing"]
    watch = [c for c in candidates if c["tier"] == "Watch"]

    # Coverage diagnostics — flag data quality issues early
    fundamentals_success = sum(
        1 for t in trend_qualified
        if t in fundamentals and fundamentals[t].get("status") == "success"
    )
    beat_history_available = sum(
        1 for t in trend_qualified
        if t in earnings_scored
    )
    beat_coverage_pct = beat_history_available / max(len(trend_qualified), 1) * 100

    log(f"Coverage report:")
    log(f"  RS qualified:          {len(rs_qualified)}")
    log(f"  Trend qualified:       {len(trend_qualified)}")
    log(f"  Fundamentals success:  {fundamentals_success}")
    log(f"  Beat history available: {beat_history_available}")
    log(f"  Beat history coverage: {beat_coverage_pct:.0f}%")

    if beat_coverage_pct < 70:
        log(f"WARNING: Beat history coverage {beat_coverage_pct:.0f}% is below 70% — "
            f"check Finnhub data quality or earnings parsing logic")

    log(f"Scan complete: {len(strong)} Strong | {len(developing)} Developing | {len(watch)} Watch")

    return {
        "strong": strong,
        "developing": developing,
        "watch": watch,
        "all_scored": candidates,
        "regime_label": regime["label"],
        "scan_stats": {
            "universe_size": len(prices) - 1,
            "rs_qualified": len(rs_qualified),
            "trend_qualified": len(trend_qualified),
            "earnings_qualified": earnings_diagnostics["qualifies"],
            "strong_count": len(strong),
            "developing_count": len(developing),
            "earnings_diagnostics": earnings_diagnostics
        }
    }


def _empty_result(regime):
    return {
        "strong": [],
        "developing": [],
        "watch": [],
        "all_scored": [],
        "regime_label": regime["label"],
        "scan_stats": {}
    }
