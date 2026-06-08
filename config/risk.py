# All risk parameters in one place

RISK_CONFIG = {
    "max_risk_per_trade_pct": 0.02,
    "stop_loss_normal_pct": 0.08,
    "stop_loss_bearish_pct": 0.06,
    "partial_exit_trigger_pct": 0.15,
    "trail_stop_pct": 0.10,
    "max_positions": {
        "Bullish": 3,
        "Neutral": 2,
        "Bearish": 1
    },
    "min_cash_pct": {
        "Bullish": 0.10,
        "Neutral": 0.30,
        "Bearish": 0.60
    },
    "max_position_size_pct": {
        "Bullish": 0.20,
        "Neutral": 0.15,
        "Bearish": 0.10
    },
    # Hard cap: no single position exceeds 10% of total portfolio
    # Overrides stop-based sizing for low-volatility stocks
    "hard_position_cap_pct": 0.10
}


# Pre-earnings exit rule
# If a held position has earnings within this many trading days,
# the morning briefing flags it as mandatory EXIT before open.
# This eliminates overnight gap risk entirely.
# Re-entry is allowed after a confirmed beat — buying post-announcement drift.
PRE_EARNINGS_EXIT_DAYS = 3
