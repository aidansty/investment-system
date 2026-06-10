import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
from utils.logger import log
from config.signals import SIGNAL_CONFIG


def fetch_implied_move(ticker: str, catalyst_date: str) -> dict:
    """
    Calculate implied earnings move from ATM options straddle.
    Only called for Strong candidates with confirmed catalyst within 20 days.

    Returns dict with implied_move_pct and compatibility check.
    """
    result = {
        "implied_move_pct": None,
        "implied_move_check": "Not Checked",
        "implied_move_note": "",
    }

    try:
        from datetime import date, datetime
        cat_date = date.fromisoformat(catalyst_date)
        today = date.today()

        if (cat_date - today).days > 30:
            result["implied_move_note"] = "Catalyst too far out for reliable options data"
            return result

        stock = yf.Ticker(ticker)

        # Get available expiration dates
        expirations = stock.options
        if not expirations:
            result["implied_move_note"] = "No options data available"
            return result

        # Find nearest expiration after catalyst date
        target_expiry = None
        for exp in expirations:
            exp_date = date.fromisoformat(exp)
            if exp_date >= cat_date:
                target_expiry = exp
                break

        if not target_expiry:
            # Use last available expiration
            target_expiry = expirations[-1]

        # Fetch options chain
        chain = stock.option_chain(target_expiry)
        calls = chain.calls
        puts = chain.puts

        if calls.empty or puts.empty:
            result["implied_move_note"] = "Empty options chain"
            return result

        # Get current price
        info = stock.fast_info
        current_price = info.last_price if hasattr(info, "last_price") else None

        if not current_price:
            hist = stock.history(period="1d")
            if hist.empty:
                result["implied_move_note"] = "Could not get current price"
                return result
            current_price = hist["Close"].iloc[-1]

        # Find ATM strike
        strikes = calls["strike"].values
        atm_strike = min(strikes, key=lambda x: abs(x - current_price))

        # Get ATM call and put prices
        atm_call = calls[calls["strike"] == atm_strike]["lastPrice"].values
        atm_put = puts[puts["strike"] == atm_strike]["lastPrice"].values

        if len(atm_call) == 0 or len(atm_put) == 0:
            result["implied_move_note"] = "ATM strike not found in chain"
            return result

        straddle_price = float(atm_call[0]) + float(atm_put[0])
        implied_move_pct = (straddle_price / current_price) * 100

        result["implied_move_pct"] = round(implied_move_pct, 1)
        result["implied_move_note"] = f"ATM straddle on {target_expiry}"

        return result

    except Exception as e:
        result["implied_move_note"] = f"Options fetch error: {e}"
        log(f"Implied move error for {ticker}: {e}")
        return result


def check_implied_move_compatibility(implied_move_pct: float, atr_stop_pct: float) -> str:
    """
    Compare implied move to ATR stop distance.
    Returns OK / Warning / Mismatch classification.
    """
    if implied_move_pct is None or atr_stop_pct is None:
        return "Not Checked"

    warning_mult = SIGNAL_CONFIG["implied_move_warning_multiplier"]
    mismatch_mult = SIGNAL_CONFIG["implied_move_mismatch_multiplier"]

    if implied_move_pct > atr_stop_pct * mismatch_mult:
        return "Mismatch"
    elif implied_move_pct > atr_stop_pct * warning_mult:
        return "Warning"
    else:
        return "OK"
