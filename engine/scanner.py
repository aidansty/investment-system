from utils.logger import log
from config.signals import SIGNAL_CONFIG
from config.risk import RISK_CONFIG
from config.sector_map import get_sector_info, detect_sector_overlaps
from signals.relative_strength import calculate_relative_strength, get_rs_qualified
from signals.trend_filter import apply_trend_filter
from signals.earnings_proxy import apply_earnings_scoring
from signals.catalyst import apply_catalyst_scoring
from signals.advanced_signals import (
    calculate_atr, calculate_atr_stop, calculate_freshness,
    calculate_earnings_reaction, get_conviction_tier,
    get_vix_regime, calculate_profit_targets
)

RS_WEIGHT = 0.40
EARNINGS_WEIGHT = 0.35
CATALYST_WEIGHT = 0.25

STRONG_THRESHOLD = 0.65
DEVELOPING_THRESHOLD = 0.45


def _normalize_rs_scores(rs_scores, qualified):
    if not qualified:
        return {}
    scores = [rs_scores[t]["rs_score"] for t in qualified]
    min_score = min(scores)
    max_score = max(scores)
    score_range = max_score - min_score
    normalized = {}
    for ticker in qualified:
        raw = rs_scores[ticker]["rs_score"]
        normalized[ticker] = 1.0 if score_range == 0 else (raw - min_score) / score_range
    return normalized


def _get_missing_signals(earnings_data, catalyst_data, composite):
    missing = []
    if earnings_data is None:
        missing.append("No earnings history available")
    elif not earnings_data.get("qualifies", False):
        streak = earnings_data.get("streak", 0)
        if streak == 0:
            missing.append("No consecutive earnings beats")
        else:
            needed = SIGNAL_CONFIG["min_consecutive_beats"]
            missing.append(f"Earnings streak too short ({streak} beat, need {needed})")
    if not catalyst_data.get("has_catalyst", False):
        missing.append("No confirmed catalyst in 5-42 day window")
    if composite < STRONG_THRESHOLD and composite >= DEVELOPING_THRESHOLD:
        if not missing:
            missing.append(f"Composite score {composite:.3f} below Strong threshold ({STRONG_THRESHOLD})")
    return ", ".join(missing) if missing else "Below composite threshold"


def run_full_scan(prices, fundamentals, regime):
    """
    Run complete candidate identification pipeline with all signal upgrades.
    All raw calculations stored in candidate dict for Notion audit trail.
    Briefing receives only conclusions.
    """
    log("=== Starting full universe scan ===")

    rs_scores = calculate_relative_strength(prices)
    rs_qualified = get_rs_qualified(rs_scores)
    trend_qualified = apply_trend_filter(prices, rs_qualified)

    log(f"Stage 1 complete: {len(trend_qualified)} technically qualified")
    log(f"Coverage checkpoint: RS qualified={len(rs_qualified)} | Trend qualified={len(trend_qualified)}")

    if not trend_qualified:
        log("No technically qualified candidates")
        return _empty_result(regime)

    earnings_scored, earnings_diagnostics = apply_earnings_scoring(fundamentals, trend_qualified)
    catalyst_scored = apply_catalyst_scoring(fundamentals, trend_qualified)
    rs_normalized = _normalize_rs_scores(rs_scores, trend_qualified)

    # VIX regime (observation only)
    vix = regime.get("conditions", {}).get("vix_level", {}).get("value", "")
    vix_val = None
    try:
        vix_val = float(str(vix).replace("VIX ", ""))
    except Exception:
        pass

    vix_5d_avg = None
    vix_regime_data = {"vix_regime": "Green", "vix_trend": "Flat"}
    if vix_val:
        from data.fetch_macro import fetch_vix_history
        try:
            hist = fetch_vix_history(days=10)
            if hist and len(hist) >= 5:
                vix_5d_avg = sum(hist[-5:]) / 5
        except Exception:
            pass
        vix_regime_data = get_vix_regime(vix_val, vix_5d_avg)

    # Sector overlap detection among all candidates
    all_candidate_list = [{"ticker": t} for t in trend_qualified]
    sector_overlaps = detect_sector_overlaps(all_candidate_list)

    candidates = []

    for ticker in trend_qualified:
        rs_norm = rs_normalized.get(ticker, 0.0)
        earnings_data = earnings_scored.get(ticker)
        catalyst_data = catalyst_scored.get(ticker, {})
        ticker_prices = prices.get(ticker, [])

        e_score = earnings_data["earnings_score"] if earnings_data else 0.0
        c_score = catalyst_data.get("catalyst_score", 0.0)

        composite = (
            rs_norm * RS_WEIGHT +
            e_score * EARNINGS_WEIGHT +
            c_score * CATALYST_WEIGHT
        )

        qualifies = earnings_data is not None and earnings_data.get("qualifies", False)

        if not qualifies:
            tier = "Watch"
            missing = _get_missing_signals(earnings_data, catalyst_data, composite)
        elif composite >= STRONG_THRESHOLD:
            tier = "Strong"
            missing = "None — all signals present"
        elif composite >= DEVELOPING_THRESHOLD:
            tier = "Developing"
            missing = _get_missing_signals(earnings_data, catalyst_data, composite)
        else:
            tier = "Watch"
            missing = _get_missing_signals(earnings_data, catalyst_data, composite)

        # Advanced signals
        current_price = ticker_prices[-1] if ticker_prices else 0

        # ATR stop
        atr_pct = calculate_atr(ticker_prices, SIGNAL_CONFIG["atr_period"])
        atr_stop_data = calculate_atr_stop(current_price, atr_pct) if atr_pct else {
            "atr_pct": None,
            "stop_pct": RISK_CONFIG["stop_loss_normal_pct"] * 100,
            "stop_price": round(current_price * (1 - RISK_CONFIG["stop_loss_normal_pct"]), 2)
        }

        # Freshness
        freshness_data = calculate_freshness(ticker_prices)

        # Earnings reaction (observation only)
        earnings_history = fundamentals.get(ticker, {}).get("earnings", [])
        reaction_data = calculate_earnings_reaction(earnings_history, prices, ticker)

        # Conviction tier (observation only)
        conviction_tier = get_conviction_tier(composite)

        # Base position size from conviction tier
        if conviction_tier == "A":
            base_size = "Full"
        elif conviction_tier == "B":
            base_size = "Half"
        else:
            base_size = "Quarter"

        # Apply freshness adjustment to final position size
        # Extended flag reduces by one level regardless of conviction tier
        freshness_val = freshness_data.get("freshness", "Fresh")
        if freshness_val == "Watch":
            final_size = "Watch"  # Removed from Strong, do not enter
        elif freshness_val == "Extended":
            # Reduce one level
            if base_size == "Full":
                final_size = "Half"
            elif base_size == "Half":
                final_size = "Quarter"
            else:
                final_size = "Watch"  # Already at minimum, move to Watch
        else:
            final_size = base_size

        # Sector info
        sector, sub_industry = get_sector_info(ticker)
        overlap_with = sector_overlaps.get(ticker)

        # Profit targets
        catalyst_date = catalyst_data.get("catalyst_date")
        from datetime import date
        profit_data = calculate_profit_targets(
            current_price,
            atr_stop_data.get("stop_pct", 8.0) / 100,
            catalyst_date,
            date.today().isoformat()
        )

        # Freshness removes Watch-level extended stocks from Strong
        if tier == "Strong" and freshness_data["freshness"] == "Watch":
            tier = "Developing"
            missing = "Extended move — 5-day return above 15%, wait for pullback"

        # Build flags list (for briefing FLAGS line — conclusions only)
        flags = []
        if freshness_data["freshness"] == "Extended":
            flags.append("Extended — consider smaller size")
        if freshness_data["freshness"] == "Watch":
            flags.append("Overextended — wait for pullback")
        if reaction_data["reaction_quality"] == "Sells News":
            flags.append("Sells the news pattern")
        if overlap_with:
            flags.append(f"Sector overlap with {overlap_with}")
        flags_str = " | ".join(flags) if flags else "No flags"

        # Coverage reporting diagnostic
        beat_history_available = 1 if earnings_history else 0

        candidate = {
            # Core identification
            "ticker": ticker,
            "tier": tier,
            "composite_score": round(composite, 3),
            "missing_signal": missing,

            # RS signals
            "rs_score": rs_scores[ticker]["rs_score"],
            "rs_normalized": round(rs_norm, 3),
            "rs_return": rs_scores[ticker]["ticker_return"],
            "raw_rs": rs_scores[ticker].get("raw_rs", rs_scores[ticker]["rs_score"]),
            "spy_return": rs_scores[ticker]["spy_return"],

            # Earnings signals
            "earnings_score": e_score,
            "beat_streak": earnings_data["streak"] if earnings_data else 0,

            # Catalyst signals
            "catalyst_score": c_score,
            "has_catalyst": catalyst_data.get("has_catalyst", False),
            "days_to_catalyst": catalyst_data.get("days_to_catalyst"),
            "catalyst_date": catalyst_date,
            "catalyst_type": catalyst_data.get("catalyst_type", "none"),
            "catalyst_confirmed": catalyst_data.get("is_confirmed", False),

            # ATR stop (replaces flat 8%)
            "atr_14d_pct": atr_stop_data.get("atr_pct"),
            "atr_stop_pct": atr_stop_data.get("stop_pct"),
            "atr_stop_price": atr_stop_data.get("stop_price"),
            "current_price": round(current_price, 2),

            # Freshness filter
            "five_day_return": freshness_data.get("five_day_return"),
            "ten_day_return": freshness_data.get("ten_day_return"),
            "freshness": freshness_data.get("freshness"),
            "freshness_note": freshness_data.get("freshness_note"),

            # Earnings reaction (observation only)
            "avg_post_earnings_return": reaction_data.get("avg_post_earnings_return"),
            "reaction_quality": reaction_data.get("reaction_quality"),

            # Conviction tier (observation only)
            "conviction_tier": conviction_tier,

            # VIX regime (observation only)
            "vix_regime": vix_regime_data.get("vix_regime"),
            "vix_at_scan": vix_val,

            # Sector
            "sector": sector,
            "sub_industry": sub_industry,
            "sector_overlap_with": overlap_with,

            # Profit targets
            "tier1_target_price": profit_data.get("tier1_target_price"),
            "pre_earnings_exit_date": profit_data.get("pre_earnings_exit_date"),
            "time_stop_days": profit_data.get("time_stop_days"),

            # Insider (placeholder — populated by post-scan enrichment)
            "insider_net_90d": None,
            "insider_flag": "Not Checked",

            # Implied move (placeholder — populated by post-scan enrichment)
            "implied_move_pct": None,
            "implied_move_check": "Not Checked",

            # Briefing output (conclusions only)
            "flags_str": flags_str,
            "base_position_size": base_size,
            "final_position_size": final_size,
        }

        candidates.append(candidate)

    candidates.sort(key=lambda x: x["composite_score"], reverse=True)

    strong = [c for c in candidates if c["tier"] == "Strong"]
    developing = [c for c in candidates if c["tier"] == "Developing"]
    watch = [c for c in candidates if c["tier"] == "Watch"]

    # Post-scan enrichment for Strong candidates only
    # Insider activity and implied move — Strong candidates only
    try:
        from data.fetch_insider import fetch_insider_activity
        from data.fetch_options import fetch_implied_move, check_implied_move_compatibility

        for c in strong:
            ticker = c["ticker"]

            # Insider activity
            insider_data = fetch_insider_activity(ticker)
            c["insider_net_90d"] = insider_data.get("insider_net_90d")
            c["insider_flag"] = insider_data.get("insider_flag", "Not Checked")

            # Implied move — only for confirmed catalyst within 20 days
            if c.get("has_catalyst") and c.get("days_to_catalyst") and c["days_to_catalyst"] <= 20 and c.get("catalyst_confirmed"):
                implied_data = fetch_implied_move(ticker, c["catalyst_date"])
                c["implied_move_pct"] = implied_data.get("implied_move_pct")
                compatibility = check_implied_move_compatibility(
                    c["implied_move_pct"],
                    c.get("atr_stop_pct")
                )
                c["implied_move_check"] = compatibility

                if compatibility in ("Warning", "Mismatch"):
                    if "flags_str" in c and c["flags_str"] != "No flags":
                        c["flags_str"] += f" | Earnings implied move ±{c['implied_move_pct']}%"
                    else:
                        c["flags_str"] = f"Earnings implied move ±{c['implied_move_pct']}%"

    except Exception as e:
        log(f"Post-scan enrichment error: {e}")

    # Coverage diagnostics
    beat_history_count = sum(1 for t in trend_qualified if t in earnings_scored)
    beat_coverage_pct = beat_history_count / max(len(trend_qualified), 1) * 100

    log(f"Coverage report:")
    log(f"  RS qualified:           {len(rs_qualified)}")
    log(f"  Trend qualified:        {len(trend_qualified)}")
    log(f"  Fundamentals success:   {len(earnings_scored)}")
    log(f"  Beat history available: {beat_history_count}")
    log(f"  Beat history coverage:  {beat_coverage_pct:.0f}%")

    if beat_coverage_pct < 70:
        log(f"WARNING: Beat history coverage {beat_coverage_pct:.0f}% is below 70%")

    log(f"Scan complete: {len(strong)} Strong | {len(developing)} Developing | {len(watch)} Watch")
    log(f"VIX Regime: {vix_regime_data.get('vix_regime')} | Trend: {vix_regime_data.get('vix_trend')}")

    return {
        "strong": strong,
        "developing": developing,
        "watch": watch,
        "all_scored": candidates,
        "regime_label": regime["label"],
        "vix_regime": vix_regime_data.get("vix_regime"),
        "scan_stats": {
            "universe_size": len(prices) - 1,
            "rs_qualified": len(rs_qualified),
            "trend_qualified": len(trend_qualified),
            "earnings_qualified": earnings_diagnostics["qualifies"],
            "strong_count": len(strong),
            "developing_count": len(developing),
            "earnings_diagnostics": earnings_diagnostics,
        }
    }


def _empty_result(regime):
    return {
        "strong": [], "developing": [], "watch": [], "all_scored": [],
        "regime_label": regime["label"],
        "vix_regime": "Green",
        "scan_stats": {}
    }
