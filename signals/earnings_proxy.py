from utils.logger import log
from config.signals import SIGNAL_CONFIG


def get_beat_streak(earnings_history: list) -> int:
    """
    Count consecutive quarters of beating EPS estimates.
    Sorts by period descending before evaluation — deterministic
    regardless of API return order.

    V1 design: strict hard reset on any miss.
    Revisit after 30 trades if early-cycle names are being missed.
    """
    if not earnings_history:
        return 0

    sorted_history = sorted(
        earnings_history,
        key=lambda q: q.get("period", ""),
        reverse=True
    )

    streak = 0
    for quarter in sorted_history:
        if quarter.get("beat", False):
            streak += 1
        else:
            break

    return streak


def earnings_score_from_streak(streak: int) -> float:
    """
    Convert beat streak to a 0.0-1.0 score.
    Partial credit for shorter streaks — allows early-cycle names
    to remain candidates when RS and catalyst signals are strong.

    0 beats  -> 0.0 (hard eliminated — no demonstrated execution)
    1 beat   -> 0.3
    2 beats  -> 0.6
    3 beats  -> 0.8
    4+ beats -> 1.0

    These mappings are documented assumptions, not calibrated values.
    First calibration review: after 30 completed trades.
    """
    if streak == 0:
        return 0.0
    if streak == 1:
        return 0.3
    if streak == 2:
        return 0.6
    if streak == 3:
        return 0.8
    return 1.0


def apply_earnings_scoring(fundamentals: dict, candidates: list) -> tuple:
    """
    Score all candidates on earnings dimension.
    No binary pass/fail except for zero-beat candidates.

    Returns (scored_dict, diagnostics_dict)

    scored_dict: {
        ticker: {
            "streak": int,
            "earnings_score": float,
            "qualifies": bool  (earnings_score > 0)
        }
    }

    diagnostics: breakdown for calibration visibility
    """
    scored = {}
    diagnostics = {
        "total_evaluated": 0,
        "qualifies": 0,
        "eliminated_zero_beats": 0,
        "no_history": 0,
        "fetch_failed": 0,
        "not_in_fundamentals": 0,
        "streak_distribution": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, "5+": 0},
        "score_distribution": {
            "1.0": 0,
            "0.8": 0,
            "0.6": 0,
            "0.3": 0,
            "0.0": 0
        }
    }

    for ticker in candidates:

        if ticker not in fundamentals:
            diagnostics["not_in_fundamentals"] += 1
            continue

        fund = fundamentals[ticker]
        status = fund.get("status", "unknown")
        earnings = fund.get("earnings", [])

        if status in ("api_error", "rate_limited"):
            diagnostics["fetch_failed"] += 1
            continue

        if not earnings:
            diagnostics["no_history"] += 1
            continue

        diagnostics["total_evaluated"] += 1

        streak = get_beat_streak(earnings)
        score = earnings_score_from_streak(streak)
        qualifies = score > 0.0

        scored[ticker] = {
            "streak": streak,
            "earnings_score": score,
            "qualifies": qualifies
        }

        # Update distributions
        if streak >= 5:
            diagnostics["streak_distribution"]["5+"] += 1
        else:
            diagnostics["streak_distribution"][streak] += 1

        score_key = str(score)
        if score_key in diagnostics["score_distribution"]:
            diagnostics["score_distribution"][score_key] += 1

        if qualifies:
            diagnostics["qualifies"] += 1
        else:
            diagnostics["eliminated_zero_beats"] += 1

    # Log summary
    log(f"Earnings scoring: {diagnostics['qualifies']} qualify | "
        f"{diagnostics['eliminated_zero_beats']} zero beats | "
        f"{diagnostics['no_history']} no history | "
        f"{diagnostics['fetch_failed']} fetch failed")

    # Log streak distribution for calibration visibility
    dist = diagnostics["streak_distribution"]
    log(f"Streak distribution: "
        f"0={dist[0]} | 1={dist[1]} | 2={dist[2]} | "
        f"3={dist[3]} | 4={dist[4]} | 5+={dist['5+']}")

    # Warn if scoring is collapsing unexpectedly
    total = len(candidates)
    qualify_rate = diagnostics["qualifies"] / max(total, 1)
    if qualify_rate < 0.30 and total > 20:
        log(f"WARNING: Only {qualify_rate:.0%} of candidates have "
            f"any beat history — consider data quality check")

    return scored, diagnostics
