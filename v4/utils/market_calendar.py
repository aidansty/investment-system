from datetime import date
import exchange_calendars as xcals
from v4.utils.logger import log

_calendar = None

def _get_calendar():
    global _calendar
    if _calendar is None:
        _calendar = xcals.get_calendar("XNYS")
    return _calendar

def is_trading_day(d: date = None) -> bool:
    if d is None:
        import pytz
        from datetime import datetime
        d = datetime.now(pytz.timezone("America/New_York")).date()
    try:
        cal = _get_calendar()
        return cal.is_session(str(d))
    except Exception as e:
        log(f"Calendar check error: {e}")
        # Fallback: Monday-Friday
        return d.weekday() < 5

def get_trading_date() -> date:
    import pytz
    from datetime import datetime
    eastern = pytz.timezone("America/New_York")
    return datetime.now(eastern).date()
