# All risk parameters in one place
# First calibration review: after 30 completed trades

RISK_CONFIG = {
    # Core position risk
    "max_risk_per_trade_pct": 0.02,
    "stop_loss_normal_pct": 0.08,      # Legacy — replaced by ATR stop in scanner
    "stop_loss_bearish_pct": 0.06,     # Legacy — replaced by ATR stop in scanner
    "partial_exit_trigger_pct": 0.175, # Take half off at 17.5% gain
    "trail_stop_pct": 0.10,            # Legacy trail stop
    "atr_trail_multiplier": 1.5,       # ATR-based trail stop after Tier 1

    # Position limits by regime
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

    # Hard position cap — overrides stop-based sizing for safety
    "hard_position_cap_pct": 0.10,

    # Maximum position size by regime
    "max_position_size_pct": {
        "Bullish": 0.20,
        "Neutral": 0.15,
        "Bearish": 0.10
    },

    # Pre-earnings exit rule
    "pre_earnings_exit_days": 3,

    # Position sizing floor
    # If stacked penalties reduce size below 50% of base, move to Watch
    # This prevents untradeable micro-positions
    "position_size_floor_multiplier": 0.50,

    # Conviction tier base sizes (observation only until 30-trade review)
    # These are logged but do NOT currently influence actual position sizing
    "conviction_tier_sizes": {
        "A": 1.0,    # Full position
        "B": 0.75,   # 75% — displayed as Half
        "C": 0.50,   # 50% — displayed as Quarter
    },

    # Candidate Analysis Notion database ID
    "candidate_analysis_db": "34c25f29-1aea-4416-bb9f-89421bf2dabc",
}
