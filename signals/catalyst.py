from utils.logger import log
from utils.market_calendar import is_trading_day
from config.signals import SIGNAL_CONFIG
from datetime import date, timedelta


def _count_trading_days(start: date, end: date) -> int:
    """Count trading days between two dates (exclusive of start)."""
    count = 0
    current = start + timedelta(days=1)
    while current <= end:
        if is_trading_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def get_catalyst_score(calendar: list, today: date = None) -> dict:
    """
    Evaluate catalyst quality from earnings calendar entries.
    Returns dict with score and supporting data.

    Catalyst scoring:
        No catalyst or outside window -> 0.0
        Confirmed, 21-42 trading days -> 0.5
        Confirmed, 5-20 trading days  -> 1.0

    Window boundaries from config:
        catalyst_min_days: 5  (inside = binary event risk, skip)
        catalyst_max_days: 42 (outside = too far, no timing edge)
    """
    if today is None:
        today = date.today()

    min_days = SIGNAL_CONFIG["catalyst_min_days"]
    max_days = SIGNAL_CONFIG["catalyst_max_days"]

    if not calendar:
        return {
            "catalyst_score": 0.0,
            "has_catalyst": False,
            "days_to_catalyst": None,
            "catalyst_date": None,
            "catalyst_type": "none"
        }

    best_score = 0.0
    best_days = None
    best_date = None

    for entry in calendar:
        raw_date = entry.get("date")
        if not raw_date:
            continue

        try:
            catalyst_date = date.fromisoformat(raw_date)
        except ValueError:
            continue

        if catalyst_date <= today:
            continue

        trading_days = _count_trading_days(today, catalyst_date)

        if trading_days < min_days or trading_days > max_days:
            continue

        # Score based on proximity
        if trading_days <= 20:
            score = 1.0
        else:
            score = 0.5

        if score > best_score:
            best_score = score
            best_days = trading_days
            best_date = raw_date

    return {
        "catalyst_score": best_score,
        "has_catalyst": best_score > 0,
        "days_to_catalyst": best_days,
        "catalyst_date": best_date,
        "catalyst_type": "earnings" if best_score > 0 else "none"
    }


def apply_catalyst_scoring(fundamentals: dict, candidates: list) -> dict:
    """
    Score all candidates on catalyst dimension.
    Returns {ticker: catalyst_result_dict}
    """
    scored = {}
    has_catalyst = 0
    no_catalyst = 0

    today = date.today()

    for ticker in candidates:
        if ticker not in fundamentals:
            scored[ticker] = {
                "catalyst_score": 0.0,
                "has_catalyst": False,
                "days_to_catalyst": None,
                "catalyst_date": None,
                "catalyst_type": "none"
            }
            no_catalyst += 1
            continue

        calendar = fundamentals[ticker].get("calendar", [])
        result = get_catalyst_score(calendar, today)
        scored[ticker] = result

        if result["has_catalyst"]:
            has_catalyst += 1
        else:
            no_catalyst += 1

    log(f"Catalyst scoring: {has_catalyst} have catalyst | "
        f"{no_catalyst} no catalyst in window")

    return scored
