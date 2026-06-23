import json
import os
from datetime import datetime
import pytz
from v4.utils.logger import log

TRACKER_FILE = "data/win_rate_tracker.json"


def load_tracker() -> dict:
    """Load the win rate tracker from disk."""
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(TRACKER_FILE):
        return {"recommendations": [], "summary": {}}
    try:
        with open(TRACKER_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"recommendations": [], "summary": {}}


def log_recommendation(
    ticker: str,
    action: str,
    price_at_recommendation: float,
    reason: str,
    conviction_score: int,
    run_type: str = "morning",
) -> None:
    """
    Log every recommendation the system makes.
    Called whenever the briefing recommends Hold/Watch/Trim/Exit/Buy/Buy More.
    """
    eastern = pytz.timezone("America/New_York")
    now = datetime.now(eastern)

    tracker = load_tracker()

    rec = {
        "id": len(tracker["recommendations"]) + 1,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M ET"),
        "ticker": ticker,
        "action": action,
        "price_at_recommendation": price_at_recommendation,
        "reason": reason,
        "conviction_score": conviction_score,
        "run_type": run_type,
        "outcome_price": None,
        "outcome_date": None,
        "outcome_pct": None,
        "spy_return_same_period": None,
        "beat_spy": None,
        "resolved": False,
    }

    tracker["recommendations"].append(rec)
    _save_tracker(tracker)
    log(f"Recommendation logged: {action} {ticker} @ ${price_at_recommendation} (conviction {conviction_score}/100)")


def resolve_recommendation(rec_id: int, current_price: float, spy_return_pct: float) -> None:
    """
    Resolve a past recommendation — fill in the outcome.
    Called daily to check if any open recommendations can be scored.
    """
    tracker = load_tracker()
    eastern = pytz.timezone("America/New_York")
    today = datetime.now(eastern).strftime("%Y-%m-%d")

    for rec in tracker["recommendations"]:
        if rec["id"] == rec_id and not rec["resolved"]:
            entry_price = rec["price_at_recommendation"]
            if entry_price and entry_price > 0:
                pct_change = round((current_price - entry_price) / entry_price * 100, 2)
                rec["outcome_price"] = current_price
                rec["outcome_date"] = today
                rec["outcome_pct"] = pct_change
                rec["spy_return_same_period"] = spy_return_pct
                rec["beat_spy"] = pct_change > spy_return_pct
                rec["resolved"] = True

    _save_tracker(tracker)
    _update_summary(tracker)


def get_win_rate_summary() -> dict:
    """
    Return win rate statistics for the briefing context.
    Only meaningful after 10+ resolved recommendations.
    """
    tracker = load_tracker()
    resolved = [r for r in tracker["recommendations"] if r["resolved"]]

    if len(resolved) < 5:
        return {
            "total_recommendations": len(tracker["recommendations"]),
            "resolved": len(resolved),
            "win_rate": None,
            "avg_return": None,
            "avg_spy_return": None,
            "alpha": None,
            "message": f"Tracking {len(tracker['recommendations'])} recommendations — need 10+ resolved to calculate win rate"
        }

    beat_spy = [r for r in resolved if r.get("beat_spy")]
    win_rate = round(len(beat_spy) / len(resolved) * 100, 1)
    avg_return = round(sum(r["outcome_pct"] for r in resolved) / len(resolved), 2)
    avg_spy = round(sum(r["spy_return_same_period"] for r in resolved if r["spy_return_same_period"]) / len(resolved), 2)
    alpha = round(avg_return - avg_spy, 2)

    return {
        "total_recommendations": len(tracker["recommendations"]),
        "resolved": len(resolved),
        "win_rate": win_rate,
        "avg_return": avg_return,
        "avg_spy_return": avg_spy,
        "alpha": alpha,
        "message": f"{win_rate}% of recommendations beat SPY | avg alpha {alpha:+.1f}%"
    }


def _save_tracker(tracker: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(TRACKER_FILE, "w") as f:
        json.dump(tracker, f, indent=2, default=str)


def _update_summary(tracker: dict) -> None:
    resolved = [r for r in tracker["recommendations"] if r["resolved"]]
    if not resolved:
        return
    beat = [r for r in resolved if r.get("beat_spy")]
    tracker["summary"] = {
        "total": len(tracker["recommendations"]),
        "resolved": len(resolved),
        "beat_spy": len(beat),
        "win_rate_pct": round(len(beat) / len(resolved) * 100, 1) if resolved else 0,
    }
    _save_tracker(tracker)
