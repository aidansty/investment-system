# All signal thresholds in one place
# Change a number here and it propagates everywhere
# All thresholds are documented assumptions — first calibration review after 30 trades

SIGNAL_CONFIG = {
    # Core signal parameters
    "rs_lookback_days": 63,
    "rs_top_percentile": 0.30,
    "trend_sma_period": 50,
    "min_consecutive_beats": 1,  # Minimum to avoid hard elimination (scoring handles the rest)
    "catalyst_min_days": 5,
    "catalyst_max_days": 42,
    "strong_signals_required": 3,
    "developing_signals_required": 2,

    # Freshness filter thresholds
    # Stocks that moved too much recently may be late entries
    "freshness_extended_pct": 10.0,   # 5-day return above this = EXTENDED
    "freshness_watch_pct": 15.0,       # 5-day return above this = WATCH (removed from Strong)
    "freshness_pullback_pct": -3.0,    # 5-day return below this = PULLING BACK

    # ATR stop loss parameters
    # Replaces flat 8% stop with volatility-adjusted stop
    "atr_period": 14,
    "atr_multiplier": 2.5,
    "atr_stop_floor_pct": 5.0,         # Never tighter than 5%
    "atr_stop_ceiling_pct": 15.0,      # Never wider than 15%

    # Earnings reaction quality thresholds
    # Average 1-day post-earnings return classification
    "reaction_strong_threshold": 3.0,   # Above +3% = Strong
    "reaction_sells_news_threshold": -1.0,  # Below -1% = Sells News

    # Conviction tier thresholds (composite score)
    # Observation only until 30-trade review confirms predictive accuracy
    "conviction_tier_a": 0.80,
    "conviction_tier_b": 0.70,
    "conviction_tier_c": 0.65,

    # Profit taking framework
    "profit_target_tier1_pct": 17.5,   # Take half off at this gain
    "atr_trail_multiplier": 1.5,        # Trailing stop after Tier 1 = 1.5x ATR
    "time_stop_days": 20,               # Reassess if no movement after this many trading days
    "pre_earnings_exit_days": 3,        # Exit this many trading days before earnings

    # VIX regime thresholds (observation only — does not auto-resize positions)
    "vix_green_threshold": 18.0,
    "vix_yellow_threshold": 25.0,

    # Implied move check
    "implied_move_warning_multiplier": 1.0,   # Flag if implied move > stop distance
    "implied_move_mismatch_multiplier": 2.0,  # Flag MISMATCH if implied move > 2x stop

    # Insider activity thresholds (observation only — logged but does not auto-resize)
    "insider_elevated_threshold": 50_000_000,   # $50M net selling = ELEVATED
    "insider_high_threshold": 100_000_000,      # $100M net selling = HIGH
}
