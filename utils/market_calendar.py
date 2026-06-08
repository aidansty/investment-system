from datetime import date
import pandas_market_calendars as mcal


def is_trading_day(check_date: date) -> bool:
    """
    Returns True if the given date is a NYSE trading day.
    Handles all US market holidays automatically.
    """
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(
        start_date=check_date.isoformat(),
        end_date=check_date.isoformat()
    )
    return not schedule.empty
