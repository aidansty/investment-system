import json
import os
from datetime import datetime
import pytz
import yfinance as yf
from v4.utils.logger import log

PERF_FILE = "data/portfolio_performance.json"
INCEPTION_DATE = "2026-04-14"


def load_performance() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(PERF_FILE):
        return {"daily": [], "inception_date": INCEPTION_DATE}
    try:
        with open(PERF_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"daily": [], "inception_date": INCEPTION_DATE}


def record_daily_performance(positions: list, cash: float = 0) -> dict:
    """
    Record today's portfolio value and SPY value.
    Called at the end of each morning run.
    Returns the updated performance dict for dashboard use.
    """
    eastern = pytz.timezone("America/New_York")
    today = datetime.now(eastern).strftime("%Y-%m-%d")

    perf = load_performance()

    # Check if already recorded today
    existing_dates = [d["date"] for d in perf["daily"]]
    if today in existing_dates:
        log(f"Performance already recorded for {today}")
        return build_chart_data(perf)

    # Calculate today's portfolio value
    total_value = sum(p.get("balance", 0) for p in positions) + cash

    # Fetch SPY current price
    spy_price = None
    try:
        data = yf.download("SPY", period="2d", auto_adjust=True, progress=False)
        close = data["Close"] if "Close" in data.columns else data
        if "SPY" in close.columns:
            spy_price = round(float(close["SPY"].dropna().iloc[-1]), 2)
        elif hasattr(close, "iloc"):
            spy_price = round(float(close.dropna().iloc[-1]), 2)
    except Exception as e:
        log(f"SPY price fetch error: {e}")

    # Get inception values for percentage calculation
    if not perf["daily"]:
        # First entry — set inception values
        perf["inception_portfolio_value"] = total_value
        perf["inception_spy_price"] = spy_price
        log(f"Performance tracking started — portfolio: ${total_value:,.2f} | SPY: ${spy_price}")

    inception_portfolio = perf.get("inception_portfolio_value", total_value)
    inception_spy = perf.get("inception_spy_price", spy_price)

    portfolio_pct = round((total_value - inception_portfolio) / inception_portfolio * 100, 2) if inception_portfolio else 0
    spy_pct = round((spy_price - inception_spy) / inception_spy * 100, 2) if inception_spy and spy_price else 0

    entry = {
        "date": today,
        "portfolio_value": round(total_value, 2),
        "spy_price": spy_price,
        "portfolio_pct": portfolio_pct,
        "spy_pct": spy_pct,
        "alpha": round(portfolio_pct - spy_pct, 2),
    }

    perf["daily"].append(entry)

    # Keep last 252 trading days (1 year)
    perf["daily"] = perf["daily"][-252:]

    with open(PERF_FILE, "w") as f:
        json.dump(perf, f, indent=2, default=str)

    log(f"Performance recorded: portfolio {portfolio_pct:+.2f}% | SPY {spy_pct:+.2f}% | alpha {entry['alpha']:+.2f}%")
    return build_chart_data(perf)


def build_chart_data(perf: dict) -> dict:
    """Build the chart arrays for the dashboard."""
    daily = perf.get("daily", [])
    if not daily:
        return {"dates": [], "portfolio": [], "spy": [], "current_alpha": None}

    dates = [d["date"] for d in daily]
    portfolio = [d["portfolio_pct"] for d in daily]
    spy = [d["spy_pct"] for d in daily]

    latest = daily[-1]
    current_alpha = latest.get("alpha")

    return {
        "dates": dates,
        "portfolio": portfolio,
        "spy": spy,
        "current_alpha": current_alpha,
        "vs_spy_display": f"You: {portfolio[-1]:+.1f}% vs S&P: {spy[-1]:+.1f}%" if portfolio else None,
    }


def get_chart_data() -> dict:
    """Get existing chart data without recording a new entry."""
    perf = load_performance()
    return build_chart_data(perf)
