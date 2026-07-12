"""
V4 Rules Engine — The decision layer.
Quantitative rules decide. Claude explains.
"""

import os
import json
from datetime import datetime, timedelta
from v4.utils.logger import log

MIN_CONVICTION_FULL_ENTRY = 65
MIN_CONVICTION_REDUCED_ENTRY = 75
MIN_CONVICTION_HOLD = 40
MIN_REGIME_SCORE = 40
MIN_POSITION_DOLLARS = 250  # Minimum $ per position — will increase as capital grows past checkpoints
THESIS_BREAK_DAYS = 10
MIN_CASH_RESERVE_PCT = 0.12
MAX_CASH_RESERVE_PCT = 0.18
MAX_CRYPTO_PCT_GREEN = 0.20
MAX_CRYPTO_PCT_RED = 0.10
LEVERAGED_ETF_MAX_DAYS = 21

PERMANENT_HOLDS = {"SPY", "BTC", "ETH", "XRP", "ZEC"}
LEVERAGED_ETFS = {"SCO", "SOXS", "SPXS", "UVXY", "SQQQ"}
CRYPTO_TICKERS = {"BTC", "ETH", "XRP", "ZEC", "BNB", "SOL"}


def calculate_regime_score(macro: dict) -> int:
    score = 0
    spy_trend = macro.get("spy_trend", "neutral")
    if spy_trend == "above": score += 25
    elif spy_trend == "neutral": score += 12

    breadth = macro.get("market_breadth", 0.5)
    if breadth >= 0.65: score += 25
    elif breadth >= 0.50: score += 18
    elif breadth >= 0.35: score += 10

    vix = macro.get("vix", 20)
    vix_trend = macro.get("vix_trend", "Flat")
    if vix < 16 and vix_trend in ("Falling", "Flat"): score += 20
    elif vix < 20: score += 15
    elif vix < 25: score += 10
    elif vix < 30: score += 5

    spy_21d = macro.get("spy_21d_return", 0)
    if spy_21d > 0.03: score += 15
    elif spy_21d > 0: score += 10
    elif spy_21d > -0.03: score += 5

    vix_regime = macro.get("vix_regime", "Yellow")
    if vix_regime == "Green": score += 15
    elif vix_regime == "Yellow": score += 8

    return min(100, max(0, score))


def regime_label(score: int) -> str:
    if score >= 60: return "Green"
    elif score >= 40: return "Yellow"
    else: return "Red"


def get_active_positions(positions: list) -> list:
    return [
        p for p in positions
        if p.get("ticker") not in PERMANENT_HOLDS
        and p.get("ticker") not in CRYPTO_TICKERS
        and p.get("type", "").lower() != "crypto"
    ]


def evaluate_entry(opportunity, positions, macro, regime_score, portfolio_value, cash_balance):
    # Use the Layer 2 two-layer recommendation (stock or ETF, whichever scored higher)
    # instead of always defaulting to the ETF — this is what actually gets recommended
    # on the dashboard, so the rules engine must agree with it.
    rec_type = opportunity.get("recommended_type", "etf")
    ticker = opportunity.get("recommended_security") or opportunity.get("etf") or opportunity.get("ticker", "")
    conviction = opportunity.get("recommended_conviction", opportunity.get("conviction_score", 0))
    industry = opportunity.get("industry", "")
    in_layer1 = opportunity.get("in_layer2", False)
    has_catalyst = bool(opportunity.get("catalyst") or opportunity.get("relevant_news"))
    active_positions = get_active_positions(positions)
    current_tickers = {p.get("ticker") for p in positions}

    if ticker in current_tickers:
        return {"action": "hold", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": "Already holding.", "size_pct": 0}

    cash_pct = cash_balance / portfolio_value if portfolio_value > 0 else 0
    if cash_pct <= MIN_CASH_RESERVE_PCT:
        return {"action": "no_entry", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": f"Cash reserve at {cash_pct:.1%} — below minimum {MIN_CASH_RESERVE_PCT:.0%}.", "size_pct": 0}

    if regime_score < MIN_REGIME_SCORE:
        return {"action": "no_entry", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": f"Regime score {regime_score}/100 — Red regime. No new entries.", "size_pct": 0}

    if not in_layer1:
        return {"action": "no_entry", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": "Industry not outperforming SPY over 63 days.", "size_pct": 0}

    if conviction < MIN_CONVICTION_FULL_ENTRY and conviction < MIN_CONVICTION_REDUCED_ENTRY:
        return {"action": "no_entry", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": f"Conviction {conviction}/100 below minimum {MIN_CONVICTION_FULL_ENTRY}.", "size_pct": 0}

    # Wash-sale 30-day cooldown with override for exceptional catalysts
    import json as _json, os as _os
    try:
        _tracker_path = "data/win_rate_tracker.json"
        if _os.path.exists(_tracker_path):
            with open(_tracker_path) as _tf:
                _tracker = _json.load(_tf)
            from datetime import datetime, timedelta
            import pytz
            _eastern = pytz.timezone("America/New_York")
            _today = datetime.now(_eastern).date()
            for rec in _tracker.get("recommendations", []):
                if rec.get("ticker") == ticker and rec.get("action") == "exit":
                    _exit_date_str = rec.get("date", "")
                    _exit_pnl = rec.get("pnl_pct", 0) or rec.get("pct_change", 0)
                    if _exit_date_str and _exit_pnl < 0:
                        try:
                            _exit_date = datetime.strptime(_exit_date_str, "%Y-%m-%d").date()
                            _days_since = (_today - _exit_date).days
                            if 0 < _days_since <= 30:
                                if conviction >= 75 and has_catalyst:
                                    return {"action": "enter_full", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": f"WASH SALE WARNING: {ticker} exited at a loss {_days_since} days ago. Re-entering triggers wash sale. However, conviction {conviction}/100 with confirmed catalyst — expected gain outweighs tax impact.", "size_pct": size_pct, "entry_type": "full", "wash_sale_override": True}
                                else:
                                    return {"action": "no_entry", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": f"WASH SALE COOLDOWN: {ticker} exited at a loss {_days_since} days ago. Blocked for {30 - _days_since} more days.", "size_pct": 0}
                        except Exception:
                            pass
    except Exception:
        pass

    # Check minimum position size — naturally limits position count based on capital
    if conviction >= 85: size_pct = 0.25
    elif conviction >= 75: size_pct = 0.20
    elif conviction >= 65: size_pct = 0.15
    else: size_pct = 0.10
    position_dollars = portfolio_value * size_pct if portfolio_value else 0
    if position_dollars < MIN_POSITION_DOLLARS and cash_balance < MIN_POSITION_DOLLARS:
        return {"action": "no_entry", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": f"Insufficient capital: position would be ${position_dollars:.0f} (minimum ${MIN_POSITION_DOLLARS}). Available cash: ${cash_balance:.0f}.", "size_pct": 0}

    if conviction >= MIN_CONVICTION_FULL_ENTRY:
        if has_catalyst:
            return {"action": "enter_full", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": f"All entry conditions met. Conviction {conviction}/100, Layer 1 qualified, regime {regime_score}/100 ({regime_label(regime_score)}), catalyst confirmed. Position size: ${position_dollars:.0f} ({size_pct:.0%} of active sleeve).", "size_pct": size_pct, "entry_type": "full", "position_dollars": round(position_dollars)}
        elif conviction >= MIN_CONVICTION_REDUCED_ENTRY:
            return {"action": "enter_reduced", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": f"Conviction {conviction}/100 — all signals green but no confirmed catalyst. Reduced 3-5% entry. Full size when catalyst confirms.", "size_pct": 0.04, "entry_type": "reduced"}
        else:
            return {"action": "no_entry", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": f"Conviction {conviction}/100 — no catalyst confirmed. Requires ≥{MIN_CONVICTION_REDUCED_ENTRY} for catalyst-free entry.", "size_pct": 0}

    return {"action": "no_entry", "ticker": ticker, "industry": industry, "conviction": conviction, "reason": "Entry conditions not fully met.", "size_pct": 0}


def evaluate_exit(position, macro, regime_score, position_review, consecutive_low_conviction_days=0, consecutive_layer1_miss_days=0, earnings_calendar=None):
    ticker = position.get("ticker", "")
    entry = position.get("entry", 0) or position.get("entry_price", 0) or 0
    current = position.get("current_price", 0) or 0
    pct_change = round((current - entry) / entry * 100, 2) if entry > 0 else 0
    what_to_do = position.get("what_to_do", "")
    conviction = position_review.get("conviction_score", 50)
    thesis_break = position_review.get("thesis_break", False)

    # ── Catalyst Position Exit Logic ──────────────────────────────────────────
    # If this position was entered for a specific catalyst, check if that event
    # has passed and whether there's still a reason to hold.
    catalyst_date_str = position.get("catalyst_date", "")
    catalyst_type = position.get("catalyst_type", "")
    entry_phase = position.get("entry_phase", "")

    # Phase 1 pre-earnings exit: force exit before earnings day
    if entry_phase == "phase1_runup" and catalyst_date_str:
        try:
            from datetime import datetime
            import pytz
            eastern = pytz.timezone("America/New_York")
            today_p1 = datetime.now(eastern).date()
            earn_date = datetime.strptime(catalyst_date_str, "%Y-%m-%d").date()
            days_to_earnings = (earn_date - today_p1).days
            if 0 <= days_to_earnings <= 1:
                return {
                    "action": "exit", "ticker": ticker, "exit_type": "phase1_pre_earnings",
                    "conviction": conviction,
                    "reason": f"PHASE 1 EXIT: {ticker} entered as pre-earnings run-up. Earnings {'today' if days_to_earnings == 0 else 'tomorrow'}. Exit to lock in +{pct_change:.1f}% — do not hold through binary event.",
                    "pct_change": pct_change,
                }
        except Exception:
            pass

    if catalyst_date_str and catalyst_type:
        try:
            from datetime import datetime, timedelta
            import pytz
            eastern = pytz.timezone("America/New_York")
            today = datetime.now(eastern).date()
            catalyst_date = datetime.strptime(catalyst_date_str, "%Y-%m-%d").date()
            days_since_catalyst = (today - catalyst_date).days

            if days_since_catalyst >= 1:
                # Catalyst event has passed — evaluate based on outcome
                has_next_catalyst = False
                if earnings_calendar and ticker in (earnings_calendar or {}):
                    next_earn_date = (earnings_calendar or {}).get(ticker, {}).get("date", "")
                    if next_earn_date:
                        try:
                            next_dt = datetime.strptime(next_earn_date, "%Y-%m-%d").date()
                            if 0 < (next_dt - today).days <= 30:
                                has_next_catalyst = True
                        except Exception:
                            pass

                if pct_change <= -3:
                    # Down after catalyst — thesis failed, exit immediately
                    return {
                        "action": "exit",
                        "ticker": ticker,
                        "conviction": conviction,
                        "reason": f"CATALYST EXIT: {catalyst_type} event on {catalyst_date_str} has passed and position is DOWN {pct_change:+.1f}%. The catalyst did not produce the expected move — thesis failed. Exit to preserve capital for the next opportunity.",
                        "exit_type": "catalyst_failed",
                        "pct_change": pct_change,
                    }
                elif pct_change < 2:
                    # Flat after catalyst — didn't deliver, no reason to hold
                    return {
                        "action": "exit",
                        "ticker": ticker,
                        "conviction": conviction,
                        "reason": f"CATALYST EXIT: {catalyst_type} event on {catalyst_date_str} has passed and position is FLAT ({pct_change:+.1f}%). The expected move did not materialize. Exit and redeploy capital into a higher-conviction opportunity.",
                        "exit_type": "catalyst_flat",
                        "pct_change": pct_change,
                    }
                elif pct_change >= 2 and not has_next_catalyst:
                    # Up after catalyst but no next catalyst — lock in gains
                    return {
                        "action": "exit",
                        "ticker": ticker,
                        "conviction": conviction,
                        "reason": f"CATALYST EXIT: {catalyst_type} event on {catalyst_date_str} has passed and position is UP {pct_change:+.1f}%. No next catalyst within 30 days — lock in gains now before the post-catalyst drift erodes them. Redeploy into the next high-conviction setup.",
                        "exit_type": "catalyst_profit_take",
                        "pct_change": pct_change,
                    }
                elif pct_change >= 2 and has_next_catalyst:
                    # Up after catalyst AND next catalyst exists — hold
                    return {
                        "action": "hold",
                        "ticker": ticker,
                        "conviction": conviction,
                        "reason": f"CATALYST HOLD: Position is UP {pct_change:+.1f}% after {catalyst_type} event AND another catalyst is confirmed within 30 days. Hold for the next event — the momentum has a forward driver.",
                        "pct_change": pct_change,
                    }
        except Exception:
            pass  # If date parsing fails, fall through to normal exit logic
    thesis_break_reason = position_review.get("thesis_break_reason", "")

    if ticker in PERMANENT_HOLDS:
        return {"action": "hold", "ticker": ticker, "exit_type": None, "reason": f"{ticker} is a permanent hold."}

    # Trailing stop: up 8%+ floor=breakeven, up 15%+ floor=+5%
    peak_pct = position.get("peak_pct", pct_change)
    if pct_change >= 8:
        trailing_floor = 0
        if peak_pct >= 15:
            trailing_floor = 5
        if pct_change <= trailing_floor:
            return {
                "action": "exit", "ticker": ticker, "exit_type": "trailing_stop",
                "conviction": conviction,
                "reason": f"TRAILING STOP: {ticker} hit peak of +{peak_pct:.1f}% but pulled back to +{pct_change:.1f}%. Floor was +{trailing_floor}%. Exit to lock in profit.",
                "pct_change": pct_change,
            }

    # ── Checkpoint Goal Evaluation ────────────────────────────────────────────
    # Every non-permanent, non-crypto stock position is evaluated against:
    # "Is this position actively helping us reach our growth checkpoints?"
    # Dead capital in positions with no catalyst and no momentum should be
    # redeployed into higher-conviction opportunities.
    #
    # SIGNIFICANCE PRINCIPLE: Only genuinely material events trigger action changes.
    # Minor analyst notes, small downgrades, generic negative commentary = noted as
    # context but do NOT change the action. Only events that can move a stock 5%+
    # (earnings miss, thesis break, major regulatory action, catalyst failure) trigger
    # an actual exit or watch signal.
    CRYPTO_TICKERS = {"BTC", "ETH", "XRP", "ZEC", "BNB", "SOL", "DOGE"}
    if ticker not in CRYPTO_TICKERS and ticker != "SPY":
        has_forward_catalyst = bool(position.get("catalyst_date") or position.get("catalyst_type"))

        # Check if there's an upcoming earnings date for this ticker
        if not has_forward_catalyst and earnings_calendar:
            earn_info = (earnings_calendar or {}).get(ticker, {})
            earn_date = earn_info.get("date", "")
            if earn_date:
                try:
                    from datetime import datetime, timedelta
                    import pytz
                    eastern = pytz.timezone("America/New_York")
                    today_ck = datetime.now(eastern).date()
                    earn_dt = datetime.strptime(earn_date, "%Y-%m-%d").date()
                    if 0 < (earn_dt - today_ck).days <= 30:
                        has_forward_catalyst = True
                except Exception:
                    pass

        # Evaluate: losing + no catalyst = dead capital
        if pct_change <= -8 and not has_forward_catalyst:
            return {
                "action": "exit",
                "ticker": ticker,
                "exit_type": "checkpoint",
                "urgency": "next_open",
                "conviction": conviction,
                "reason": f"CHECKPOINT REVIEW: Position is DOWN {pct_change:+.1f}% with no confirmed catalyst in the next 30 days. This capital is not helping reach the next checkpoint — redeploy into the highest-conviction catalyst opportunity to accelerate growth.",
                "pct_change": pct_change,
            }
        elif pct_change <= -5 and not has_forward_catalyst and conviction < 50:
            return {
                "action": "watch",
                "ticker": ticker,
                "exit_type": "checkpoint",
                "urgency": "monitor",
                "conviction": conviction,
                "reason": f"CHECKPOINT WARNING: Position is DOWN {pct_change:+.1f}% with low conviction ({conviction}/100) and no catalyst ahead. If no significant catalyst (earnings, FDA, major contract, product launch) emerges within the next week, exit and redeploy this capital. Minor analyst notes or generic industry commentary do not count as catalysts.",
                "pct_change": pct_change,
            }
        elif pct_change > 0 and pct_change < 3 and not has_forward_catalyst and conviction < 50:
            return {
                "action": "watch",
                "ticker": ticker,
                "exit_type": "checkpoint",
                "urgency": "monitor",
                "conviction": conviction,
                "reason": f"CHECKPOINT REVIEW: Position is barely positive ({pct_change:+.1f}%) with low conviction ({conviction}/100) and no forward catalyst. This capital may be better deployed in a higher-conviction setup with a specific growth driver.",
                "pct_change": pct_change,
            }

    if thesis_break and thesis_break_reason:
        return {"action": "exit", "ticker": ticker, "exit_type": "fast", "urgency": "immediate", "reason": f"THESIS BREAK: {thesis_break_reason}", "pct_change": pct_change}

    if what_to_do and any(word in what_to_do.upper() for word in ["CLOSE —", "EXIT —", "CLOSE THE POSITION"]):
        return {"action": "exit", "ticker": ticker, "exit_type": "fast", "urgency": "immediate", "reason": f"Rules engine confirms close: {what_to_do[:200]}", "pct_change": pct_change}

    if ticker in LEVERAGED_ETFS:
        entry_date_str = position.get("entry_date", "")
        if entry_date_str:
            try:
                entry_date = datetime.strptime(entry_date_str[:10], "%Y-%m-%d")
                days_held = (datetime.now() - entry_date).days
                if days_held >= LEVERAGED_ETF_MAX_DAYS:
                    if conviction >= 75:
                        return {"action": "re_evaluate", "ticker": ticker, "exit_type": "fast", "urgency": "today", "reason": f"Leveraged ETF held {days_held} days — close to reset decay, re-evaluate fresh entry if thesis intact.", "pct_change": pct_change}
                    else:
                        return {"action": "exit", "ticker": ticker, "exit_type": "fast", "urgency": "today", "reason": f"Leveraged ETF held {days_held} days — maximum reached. Exit today.", "pct_change": pct_change}
            except Exception:
                pass

    if conviction < MIN_CONVICTION_HOLD and consecutive_low_conviction_days >= THESIS_BREAK_DAYS:
        return {"action": "exit", "ticker": ticker, "exit_type": "slow", "urgency": "next_open", "reason": f"Conviction {conviction}/100 below {MIN_CONVICTION_HOLD} for {consecutive_low_conviction_days} consecutive days.", "pct_change": pct_change}
    elif conviction < MIN_CONVICTION_HOLD:
        days_remaining = THESIS_BREAK_DAYS - consecutive_low_conviction_days
        return {"action": "watch", "ticker": ticker, "exit_type": "slow", "urgency": "monitor", "reason": f"Conviction {conviction}/100 below {MIN_CONVICTION_HOLD}. Day {consecutive_low_conviction_days}/5 of exit window. {days_remaining} more days to exit if no recovery.", "pct_change": pct_change}

    if consecutive_layer1_miss_days >= 5:
        return {"action": "exit", "ticker": ticker, "exit_type": "slow", "urgency": "next_open", "reason": f"Industry out of Layer 1 for {consecutive_layer1_miss_days} consecutive days. Momentum broken.", "pct_change": pct_change}

    if what_to_do and "WATCH" in what_to_do.upper():
        return {"action": "watch", "ticker": ticker, "exit_type": None, "urgency": "monitor", "reason": what_to_do[:300], "pct_change": pct_change}

    return {"action": "hold", "ticker": ticker, "exit_type": None, "reason": f"All hold conditions met. Conviction {conviction}/100.", "pct_change": pct_change}


def calculate_tax_awareness(ticker, entry_date_str, conviction, expected_hold_weeks=12):
    try:
        entry_date = datetime.strptime(entry_date_str[:10], "%Y-%m-%d")
        long_term_date = entry_date + timedelta(days=366)
        days_to_long_term = (long_term_date - datetime.now()).days
        currently_short_term = datetime.now() < long_term_date
        if currently_short_term:
            if days_to_long_term <= 30:
                recommendation = f"⚠️ TAX: {days_to_long_term} days from long-term status ({long_term_date.strftime('%b %d')}). Consider holding."
                urgency = "high"
            elif days_to_long_term <= 90:
                recommendation = f"TAX NOTE: {days_to_long_term} days to long-term gains ({long_term_date.strftime('%b %d')})."
                urgency = "medium"
            else:
                recommendation = f"Short-term position. Long-term gain date: {long_term_date.strftime('%b %d, %Y')}."
                urgency = "low"
        else:
            recommendation = "Long-term gain status achieved."
            urgency = "none"
        return {"ticker": ticker, "currently_short_term": currently_short_term, "long_term_date": long_term_date.strftime("%Y-%m-%d"), "days_to_long_term": max(0, days_to_long_term), "tax_recommendation": recommendation, "urgency": urgency}
    except Exception:
        return {"ticker": ticker, "currently_short_term": True, "long_term_date": "unknown", "days_to_long_term": 999, "tax_recommendation": "Entry date not recorded — assume short-term.", "urgency": "low"}


def check_crypto_sizing(positions, portfolio_value, regime_score):
    crypto_positions = [p for p in positions if p.get("ticker") in CRYPTO_TICKERS or p.get("type", "").lower() == "crypto"]
    total_crypto_value = sum(p.get("current_price", 0) * p.get("qty", 0) for p in crypto_positions)
    crypto_pct = total_crypto_value / portfolio_value if portfolio_value > 0 else 0
    max_pct = MAX_CRYPTO_PCT_RED if regime_score < MIN_REGIME_SCORE else MAX_CRYPTO_PCT_GREEN
    return {"crypto_pct": round(crypto_pct, 3), "max_allowed_pct": max_pct, "over_limit": crypto_pct > max_pct, "regime": regime_label(regime_score), "warning": f"⚠️ Crypto {crypto_pct:.1%} exceeds {max_pct:.0%} limit in {regime_label(regime_score)} regime." if crypto_pct > max_pct else None}


def check_kill_criteria(portfolio_value, portfolio_peak, spy_return_pct, active_equity_return_pct, months_since_start):
    alerts = []
    triggered = False
    if portfolio_peak > 0:
        drawdown_pct = (portfolio_value - portfolio_peak) / portfolio_peak
        if drawdown_pct <= -0.15:
            alerts.append({"type": "drawdown", "severity": "critical", "message": f"🔴 KILL CRITERIA: Portfolio down {abs(drawdown_pct):.1%} from peak. Reduce active exposure immediately."})
            triggered = True
    if months_since_start <= 4:
        underperformance = active_equity_return_pct - spy_return_pct
        if underperformance <= -0.08:
            alerts.append({"type": "underperformance", "severity": "critical", "message": f"⚠️ KILL CRITERIA: Active equity underperforming SPY by {abs(underperformance):.1%} in first {months_since_start:.1f} months. Pause new entries."})
            triggered = True
    return {"triggered": triggered, "alerts": alerts, "drawdown_pct": round((portfolio_value - portfolio_peak) / portfolio_peak, 3) if portfolio_peak > 0 else 0, "vs_spy_pct": round(active_equity_return_pct - spy_return_pct, 3)}


def run_rules_engine(positions, industry_results, macro, position_reviews, portfolio_value, cash_balance, portfolio_peak=0, spy_return_pct=0, active_equity_return_pct=0, months_since_start=2.5):
    log("=== Rules Engine Starting ===")
    regime_score = calculate_regime_score(macro)
    regime = regime_label(regime_score)
    log(f"Regime score: {regime_score}/100 ({regime})")
    review_lookup = {r.get("ticker", ""): r for r in position_reviews}

    exit_signals = []
    for position in positions:
        ticker = position.get("ticker", "")
        review = review_lookup.get(ticker, {})
        consecutive_low = position.get("consecutive_low_conviction_days", 0)
        consecutive_l1_miss = position.get("consecutive_layer1_miss_days", 0)
        signal = evaluate_exit(position=position, macro=macro, regime_score=regime_score, position_review=review, consecutive_low_conviction_days=consecutive_low, consecutive_layer1_miss_days=consecutive_l1_miss)
        entry_date = position.get("entry_date", "")
        if entry_date and ticker not in CRYPTO_TICKERS:
            conviction = review.get("conviction_score", 50)
            signal["tax_awareness"] = calculate_tax_awareness(ticker, entry_date, conviction)
        exit_signals.append(signal)
        log(f"  {ticker}: {signal['action'].upper()} — {signal['reason'][:80]}")

    entry_signals = []
    for opportunity in industry_results.get("top_industries", [])[:5]:
        signal = evaluate_entry(opportunity=opportunity, positions=positions, macro=macro, regime_score=regime_score, portfolio_value=portfolio_value, cash_balance=cash_balance)
        if signal["action"] in ("enter_full", "enter_reduced"):
            signal["tax_note"] = "New position — short-term gain until held 12+ months."
            entry_signals.append(signal)
            log(f"  ENTRY: {signal['ticker']} ({signal['action']}) — {signal['reason'][:80]}")

    crypto_check = check_crypto_sizing(positions, portfolio_value, regime_score)
    if crypto_check["over_limit"]:
        log(f"  CRYPTO WARNING: {crypto_check['warning']}")

    kill_check = check_kill_criteria(portfolio_value=portfolio_value, portfolio_peak=portfolio_peak, spy_return_pct=spy_return_pct, active_equity_return_pct=active_equity_return_pct, months_since_start=months_since_start)
    if kill_check["triggered"]:
        for alert in kill_check["alerts"]:
            log(f"  {alert['message']}")

    log(f"Rules Engine complete: {len(exit_signals)} exit evals, {len(entry_signals)} entry signals")
    return {"regime_score": regime_score, "regime": regime, "exit_signals": exit_signals, "entry_signals": entry_signals, "crypto_check": crypto_check, "kill_criteria": kill_check, "summary": {"exits_triggered": [s for s in exit_signals if s["action"] == "exit"], "watches_triggered": [s for s in exit_signals if s["action"] == "watch"], "entries_available": entry_signals, "kill_triggered": kill_check["triggered"]}}
