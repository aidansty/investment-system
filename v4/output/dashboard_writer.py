import json
import os
from datetime import datetime
import pytz
from v4.utils.logger import log


DASHBOARD_DATA_FILE = "dashboard_data.js"


def write_dashboard_data(
    macro: dict,
    industry_results: dict,
    news_package: dict,
    positions: list,
    briefing: dict,
    run_type: str,
    today,
    cash: float = 0,
    cost_basis: float = 0,
    performance_history: list = None,
    intraday: dict = None,
    rules_output: dict = None,
    catalyst_opportunities: list = None,
) -> None:
    """
    Write structured briefing data to dashboard_data.js.
    The dashboard reads this file on page load.
    run_type: "morning" or "afternoon"
    """
    eastern = pytz.timezone("America/New_York")
    now = datetime.now(eastern).strftime("%B %d, %Y %I:%M %p ET")

    # Macro
    vix = macro.get("vix")
    vix_avg = macro.get("vix_5d_avg")
    vix_trend = macro.get("vix_trend", "Flat")
    vix_regime = macro.get("vix_regime", "Yellow")
    regime_label = "Bullish" if vix_regime == "Green" else ("Bearish" if vix_regime == "Red" else "Neutral")

    # Market bullets from briefing
    sections_dict = briefing.get("sections", {}) if briefing else {}
    market_overview = (
        sections_dict.get("Market Snapshot Explanation") or
        sections_dict.get("Market Overview") or ""
    )
    if briefing:
        raw = briefing.get("raw_text", "")
        if raw:
            import re
            # Try multiple section name variants since Claude formatting can vary slightly
            for pattern in [r"## Market Snapshot.*?\n(.*?)(?=##|$)", r"## Market Overview.*?\n(.*?)(?=##|$)"]:
                m = re.search(pattern, raw, re.DOTALL | re.IGNORECASE)
                if m and len(m.group(1).strip()) > 30:
                    market_overview = m.group(1).strip()
                    break
    # Extract bullets from Market Overview — handle both dash bullets and prose sentences
    market_bullets = []
    if market_overview:
        for line in market_overview.split(chr(10)):
            stripped = line.strip().lstrip("-•*").strip()
            if len(stripped) > 20:
                market_bullets.append(stripped)
        if not market_bullets:
            # Fall back to sentence splitting
            market_bullets = [s.strip() + "." for s in market_overview.replace(chr(10), " ").split(".") if len(s.strip()) > 20][:5]
    # Last resort: if still empty OR too sparse to be useful, build from macro data directly
    if len(market_bullets) < 2 and macro:
        vix_val = macro.get("vix", 0)
        vix_regime = macro.get("vix_regime", "Yellow")
        vix_trend = macro.get("vix_trend", "Flat")
        trend_explainer = {
            "Falling": "fear is decreasing (bullish for entries)",
            "Rising": "fear is increasing (be more selective)",
            "Spiking": "sharp fear spike (avoid new entries today)",
            "Flat": "sentiment stable (no change in posture)",
        }.get(vix_trend, "")
        action_summary = {
            "Green": "Conditions support entering catalyst-driven positions at full conviction sizing. Deploy cash into top catalyst scanner opportunities.",
            "Yellow": "Conditions are mixed. Only enter positions with confirmed catalysts and conviction above 75. Hold existing positions.",
            "Red": "Defensive mode. No new entries until conditions stabilize. Monitor existing positions for thesis breaks and protect capital.",
        }.get(vix_regime, "")
        market_bullets = [
            f"Regime: {vix_regime} ({vix_val} VIX, trend {vix_trend.lower()} — {trend_explainer}).",
            action_summary,
        ]

    # News
    recent_news = news_package.get("recent_news", [])
    forward_catalysts = news_package.get("forward_catalysts", [])

    # News intelligence — ONLY show items that pass one of two tests:
    # Test 1: Affects a current holding (say which one and what to do)
    # Test 2: Creates a new investment opportunity (say what to buy)
    # Everything else is filtered OUT — max 5 items
    holding_tickers = {p.get("ticker", "") for p in positions} if positions else set()
    crypto_skip = {"BTC", "ETH", "XRP", "ZEC", "SOL", "BNB", "DOGE"}
    stock_holdings = holding_tickers - crypto_skip

    news_cards = []
    for n in recent_news[:15]:  # scan more, keep fewer
        affected = n.get("affected_tickers", []) or n.get("tickers", [])
        if not isinstance(affected, list):
            affected = []
        impact = n.get("portfolio_impact", "") or n.get("impact", "")
        sentiment = n.get("sentiment", "")
        summary = n.get("summary", "")
        headline = n.get("headline", "")

        # Check if this news actually affects a current holding
        affects_holding = any(tk in stock_holdings for tk in affected)
        # Or check if headline mentions a holding ticker
        if not affects_holding:
            for tk in stock_holdings:
                if tk and len(tk) >= 2 and tk in headline.upper():
                    affects_holding = True
                    if tk not in affected:
                        affected.append(tk)
                    break

        # Determine relevance category AND significance
        # Only include items significant enough to actually move a stock 5%+
        # Filter out noise: minor analyst notes, small partnerships, generic outlook pieces
        headline_upper = headline.upper()
        noise_keywords = ["PRICE TARGET", "ANALYST NOTE", "OUTLOOK", "MAINTAINS RATING",
                          "REITERATES", "INITIATES COVERAGE", "MINOR", "SLIGHT",
                          "MODEST", "STABLE", "STEADY", "UNCHANGED"]
        is_noise = any(kw in headline_upper for kw in noise_keywords) and not any(
            kw in headline_upper for kw in ["UPGRADE", "DOWNGRADE", "DOUBLE", "CUT", "RAISE", "BEAT", "MISS"]
        )
        if is_noise:
            continue  # Not significant enough to act on

        # Significance keywords — events that typically move stocks 5%+
        high_significance = ["EARNINGS", "FDA", "APPROV", "REJECT", "ACQUI", "MERGER",
                             "BUYOUT", "CONTRACT WIN", "RECORD REVENUE", "GUIDANCE RAISE",
                             "GUIDANCE CUT", "INDEX INCLUSION", "ADDED TO", "REMOVED FROM",
                             "STOCK SPLIT", "BUYBACK", "BEAT ESTIMATE", "MISS ESTIMATE",
                             "DOWNGRADE", "UPGRADE", "HALT", "CRASH", "SURGE", "PLUNGE",
                             "LAUNCH", "BREAKTHROUGH", "SANCTION", "TARIFF", "BAN ",
                             "INVESTIGATION", "FRAUD", "RECALL", "LAWSUIT"]
        is_significant = any(kw in headline_upper for kw in high_significance)
        # Also significant if the summary/impact mentions strong directional language
        impact_upper = (impact or "").upper()
        if not is_significant and impact_upper:
            is_significant = any(kw in impact_upper for kw in ["STRONG", "MAJOR", "SIGNIFICANT", "CRITICAL", "DIRECTLY AFFECT", "THESIS"])

        if affects_holding:
            # For holdings: only show if genuinely significant — not minor noise
            if is_significant or is_noise == False:
                relevance = "holding"
            else:
                continue
        elif sentiment == "bullish" and affected and is_significant:
            # For opportunities: MUST be significant — no minor positive fluff
            relevance = "opportunity"
        elif any(kw in headline_upper for kw in ["FED ", "FOMC", "CPI ", "RATE CUT", "RATE HIKE"]):
            relevance = "macro"
        else:
            continue  # Not significant enough to warrant your attention

        # Build bullets — lead with WHY THIS MATTERS TO YOU
        bullets = []
        if relevance == "holding":
            tickers_str = ", ".join([tk for tk in affected if tk in stock_holdings])
            # Bullet 1: What the news/event IS
            if summary:
                bullets.append(summary[:250])
            else:
                bullets.append(headline[:150])
            # Bullet 2: HOW it connects to and affects the specific holding
            if impact:
                bullets.append(f"How this affects {tickers_str}: {impact}")
            else:
                # Build a connection explanation from sentiment and category
                direction = "positively (bullish)" if sentiment == "bullish" else "negatively (bearish)" if sentiment == "bearish" else "directly"
                category = n.get("category", "")
                if category:
                    bullets.append(f"How this affects {tickers_str}: This {category} event impacts {tickers_str} {direction}. Review your position and consider whether action is needed.")
                else:
                    bullets.append(f"How this affects {tickers_str}: This development impacts {tickers_str} {direction}. Monitor for further developments.")
            # Bullet 3: Recommended action
            if sentiment == "bearish":
                bullets.append(f"Action: Watch {tickers_str} closely — if this develops further, consider trimming or exiting.")
            elif sentiment == "bullish":
                bullets.append(f"Action: Bullish for {tickers_str} — hold or consider adding if conviction is high.")
            else:
                bullets.append(f"Action: No immediate change needed for {tickers_str} — continue holding and monitor.")
        elif relevance == "opportunity":
            opp_tickers = ", ".join(affected[:3])
            # Bullet 1: What the news/event IS
            if summary:
                bullets.append(summary[:250])
            else:
                bullets.append(headline[:150])
            # Bullet 2: HOW this creates an opportunity and in what specifically
            if impact:
                bullets.append(f"Why this is an opportunity: {impact}")
            else:
                bullets.append(f"Why this is an opportunity: This event could drive significant price movement in {opp_tickers}. Check the catalyst scanner for entry timing.")
            # Bullet 3: Action to take
            bullets.append(f"Action: Research {opp_tickers} for potential entry — check catalyst dates and conviction score in the catalyst scanner below.")
        elif relevance == "macro":
            # Bullet 1: What happened
            if summary:
                bullets.append(summary[:250])
            else:
                bullets.append(headline[:150])
            # Bullet 2: How it affects all holdings
            direction = "positively" if sentiment == "bullish" else "negatively" if sentiment == "bearish" else ""
            bullets.append(f"Market-wide impact — affects all positions{' ' + direction if direction else ''}. This may change the regime and entry conditions for new positions.")

        news_cards.append({
            "headline": headline,
            "url": n.get("url", ""),
            "source": n.get("source", ""),
            "bullets": bullets[:3],
            "affected_tickers": affected,
            "sentiment": sentiment,
            "relevance": relevance,
        })

        if len(news_cards) >= 5:
            break

    # Also scan forward catalysts for items affecting holdings or creating opportunities
    for fc in (news_package.get("forward_catalysts", []) if news_package else []):
        if len(news_cards) >= 7:
            break
        affected = fc.get("affected_holdings", []) or fc.get("tickers", [])
        if not isinstance(affected, list):
            affected = []
        event = fc.get("event", "") or fc.get("description", "")
        fc_date = fc.get("date", "") or fc.get("event_date", "")
        action_tag = fc.get("action", "")

        affects_holding = any(tk in stock_holdings for tk in affected)
        if not affects_holding and not affected:
            continue

        # Skip if already covered by a news item with the same ticker
        already_covered = any(
            any(tk in (nc.get("affected_tickers", []) or []) for tk in affected)
            for nc in news_cards
        )
        if already_covered:
            continue

        bullets = []
        if affects_holding:
            tickers_str = ", ".join([tk for tk in affected if tk in stock_holdings])
            bullets.append(f"Your holdings affected ({tickers_str}): {event[:150]}")
            if action_tag:
                bullets.append(f"Recommended action: {action_tag}")
            relevance = "holding"
        else:
            bullets.append(f"Upcoming catalyst: {event[:150]}")
            if fc_date:
                bullets.append(f"Date: {fc_date}")
            relevance = "opportunity"

        news_cards.append({
            "headline": event[:80] if event else "Upcoming catalyst",
            "url": "",
            "source": "Forward catalyst scanner",
            "bullets": bullets[:3],
            "affected_tickers": affected,
            "sentiment": "bullish" if action_tag in ("Buy", "Hold") else "",
            "relevance": relevance,
        })

    # Also add recent earnings results that affect holdings
    re_results = briefing.get("recent_earnings_results", {}) if briefing else {}
    if not re_results and rules_output:
        re_results = rules_output.get("recent_earnings_results", {})
    for ticker, result in (re_results or {}).items():
        if len(news_cards) >= 7:
            break
        if ticker not in stock_holdings:
            continue
        already_covered = any(ticker in (nc.get("affected_tickers", []) or []) for nc in news_cards)
        if already_covered:
            continue
        verdict = result.get("verdict", "")
        eps_actual = result.get("eps_actual")
        eps_estimate = result.get("eps_estimate")
        eps_surprise = result.get("eps_surprise_pct", 0)
        report_date = result.get("report_date", "")
        bullets = [
            f"Earnings reported {report_date}: {verdict} — EPS actual {eps_actual} vs estimate {eps_estimate} ({eps_surprise:+.1f}% surprise)",
        ]
        if verdict == "BEAT":
            bullets.append(f"Action: This confirms the thesis — hold or add to position if conviction is high")
        elif verdict == "MISS":
            bullets.append(f"Action: Thesis weakened — review whether to reduce or exit this position")
        else:
            bullets.append(f"Action: In-line result — no change in thesis, continue holding")
        news_cards.append({
            "headline": f"{ticker} earnings: {verdict}",
            "url": "",
            "source": "Earnings results",
            "bullets": bullets,
            "affected_tickers": [ticker],
            "sentiment": "bullish" if verdict == "BEAT" else "bearish" if verdict == "MISS" else "neutral",
            "relevance": "holding",
        })

    # Position review from briefing — try multiple section name variants Claude might use
    sections = briefing.get("sections", {}) if briefing else {}
    pos_review_text = (
        sections.get("Open Position Review") or
        sections.get("Position Review") or
        sections.get("Portfolio Review") or
        sections.get("Holdings Review") or
        ""
    )
    # If section parsing failed, try extracting from raw briefing text
    if not pos_review_text and briefing:
        raw = briefing.get("raw_text", "")
        if raw:
            # Find the position review section in raw text
            import re
            match = re.search(r"##\s*(?:Open )?Position Review.*?(?=##|$)", raw, re.DOTALL | re.IGNORECASE)
            if match:
                pos_review_text = match.group(0)
    position_review = _parse_position_review(pos_review_text, positions)

    # Enrich each position with quant data and entry price from positions.json
    pos_lookup = {p.get("ticker"): p for p in positions}
    for pr in position_review:
        ticker = pr.get("ticker", "")
        raw = pos_lookup.get(ticker, {})
        pr["entry_price"] = raw.get("entry", 0) or raw.get("entry_price", 0)
        pr["term"] = raw.get("term", "")
        pr["industry"] = raw.get("industry", "")
        pr["what_to_do"] = raw.get("what_to_do", "")
        pr["summary"] = raw.get("summary", "")
        pr["catalyst"] = raw.get("catalyst", "")
        pr["why"] = raw.get("why", "")
        # Pull quant data if available
        quant = raw.get("quant", {})
        if quant:
            pr["revenue_growth"] = quant.get("revenue_growth_yoy")
            pr["fcf"] = quant.get("fcf")
            pr["avg_surprise"] = quant.get("avg_earnings_surprise_pct")
            pr["analyst_target"] = quant.get("analyst_price_target")

    # Smart override: rules engine controls the ACTION, Claude provides fresh context
    # When they agree → use Claude's fresh text (news-driven, updated daily)
    # When they disagree → show rules engine reason FIRST, then Claude's context
    re = rules_output or {}
    exit_signals = re.get("exit_signals", [])
    rules_decisions = {}
    for sig in exit_signals:
        rules_decisions[sig.get("ticker", "")] = sig

    for pr in position_review:
        ticker = pr.get("ticker", "")
        sig = rules_decisions.get(ticker)
        if sig:
            sig_action = sig.get("action", "").lower()
            sig_reason = sig.get("reason", "")
            claude_action = (pr.get("action", "") or "Hold").lower()
            claude_bullets = pr.get("bullets", [])

            if sig_action == "exit":
                pr["action"] = "Exit"
                if claude_action != "exit":
                    # DISAGREE — show both: rules engine reason + Claude context
                    combined_bullets = [sig_reason[:250]]
                    if claude_bullets:
                        combined_bullets.append("Claude analysis: " + claude_bullets[0][:200])
                    pr["bullets"] = combined_bullets
                    pr["what_to_do"] = sig_reason[:250]
                    pr["catalyst"] = "No forward catalyst identified"
                    pr["why"] = sig_reason[:250]
                else:
                    # AGREE on exit — use Claude's explanation (it's fresher)
                    pr["what_to_do"] = claude_bullets[0][:250] if claude_bullets else sig_reason[:250]
                    pr["why"] = claude_bullets[0][:250] if claude_bullets else sig_reason[:250]
            elif sig_action == "watch":
                pr["action"] = "Watch"
                if claude_action not in ("watch", "trim"):
                    combined_bullets = [sig_reason[:250]]
                    if claude_bullets:
                        combined_bullets.append("Claude analysis: " + claude_bullets[0][:200])
                    pr["bullets"] = combined_bullets
                    pr["what_to_do"] = sig_reason[:250]
                else:
                    pr["what_to_do"] = claude_bullets[0][:250] if claude_bullets else sig_reason[:250]
            elif sig_action == "hold":
                # Both agree on hold — keep Claude's fresh, news-driven text entirely
                # Do NOT override — Claude's text references today's news
                pr["action"] = "Hold"
                # Only touch what_to_do if Claude left it empty
                if not pr.get("what_to_do") and claude_bullets:
                    pr["what_to_do"] = claude_bullets[0][:250]

    # Ensure EVERY stock position appears in position_review
    # If Claude didn't mention a position, add it using rules engine data
    CRYPTO_SKIP_PR = {"BTC", "ETH", "XRP", "ZEC", "SOL", "BNB", "DOGE"}
    reviewed_tickers = {pr.get("ticker") for pr in position_review}
    for p in (positions or []):
        tk = p.get("ticker", "")
        if tk in CRYPTO_SKIP_PR or tk == "SPY":
            continue
        if tk not in reviewed_tickers:
            # This position was NOT in Claude's review — add it from rules engine
            sig = rules_decisions.get(tk, {})
            sig_action = sig.get("action", "hold").capitalize() if sig else "Hold"
            sig_reason = sig.get("reason", "Position under active monitoring.") if sig else "No specific update today — position under active monitoring."
            entry_price = p.get("entry_price", 0) or p.get("entry", 0) or 0
            current_price = p.get("current_price", 0) or 0
            pct = round((current_price - entry_price) / entry_price * 100, 1) if entry_price > 0 else 0
            position_review.append({
                "ticker": tk,
                "action": sig_action,
                "bullets": [sig_reason[:250]],
                "what_to_do": sig_reason[:250],
                "catalyst": sig.get("catalyst", ""),
                "why": sig_reason[:250],
                "entry_price": entry_price,
                "term": p.get("term", ""),
                "industry": p.get("industry", ""),
                "summary": p.get("summary", ""),
            })

    # Store rules_decisions so we can use it below
    _rules_decisions = rules_decisions

    # Industry opportunities — uses the actual Layer 2 scanner output directly
    # (recommended_security, recommended_type, recommended_conviction, stock_leaders)
    # rather than recreating vehicle-selection logic that the scanner already did.
    top_industries = industry_results.get("top_industries", []) if industry_results else []
    industry_opportunities = []
    sections = briefing.get("sections", {}) if briefing else {}
    rules_engine_text = sections.get("Rules Engine Signals", "")
    industry_analysis_text = sections.get("Industry Analysis (Layer 1 — Context Only)", "")

    for ind in top_industries[:4]:
        ind_news = ind.get("relevant_news", [])
        industry_name = ind["industry"]
        conviction = ind.get("conviction_score", ind.get("etf_conv", 0))

        # Pull Layer 2 recommendation directly — this IS the decision, not a recreation of it
        rec_security = ind.get("recommended_security", ind.get("etf", ""))
        rec_type = ind.get("recommended_type", "etf")
        rec_conviction = ind.get("recommended_conviction", conviction)
        stock_leaders = ind.get("stock_leaders", [])

        # Build bullets from actual data + news — momentum alone is never
        # sufficient reasoning; a catalyst/news basis is required.
        bullets = []
        excess = ind.get("excess_63d", 0)
        bullets.append(f"{ind['etf']} is outperforming SPY by {excess:+.1f} percentage points over the last 63 trading days.")

        has_real_catalyst = False
        if ind_news:
            for n in ind_news[:2]:
                headline = n.get("headline", "")
                summary = n.get("summary", "")
                if headline:
                    bullets.append(f"{headline}" + (f" — {summary[:300]}" if summary else ""))
                    has_real_catalyst = True

        if ind.get("ripple_benefits"):
            bullets.append(f"Ripple tailwinds flowing in from related sectors: {', '.join(ind['ripple_benefits'][:3])}.")
            has_real_catalyst = True

        event_score = ind.get("event_score", 0)
        if event_score and event_score > 0.5:
            has_real_catalyst = True

        if not has_real_catalyst:
            bullets.append("\u26a0\ufe0f No confirmed catalyst or news driver identified — this is a momentum-only signal. Momentum alone is not sufficient reason to invest; treat as a watch item until a specific catalyst emerges.")

        # Vehicle reasoning now comes directly from what the Layer 2 scanner decided
        if rec_type == "stock":
            stock_list_str = ", ".join([f"{s['ticker']} ({s['conviction']}/100)" for s in stock_leaders[:3]])
            vehicle = f"{rec_security} (individual stock) — scored {rec_conviction}/100, outscoring the {ind['etf']} ETF itself ({conviction}/100). Other leaders scanned in this industry: {stock_list_str if stock_list_str else 'none above threshold'}."
        else:
            vehicle = f"{ind['etf']} ETF — no individual stock in this industry scored meaningfully higher than the ETF itself ({conviction}/100). Broad sector exposure is the better risk-adjusted vehicle right now."

        # Build per-stock reasoning so each chip explains WHY it ranks where it does
        stock_reasoning = []
        for s in stock_leaders[:4]:
            tk = s.get("ticker", "")
            conv = s.get("conviction", 0)
            exc63 = s.get("excess_63d", 0)
            exc21 = s.get("excess_21d", 0)
            breakout = s.get("is_breakout", False)
            is_rec = (tk == rec_security)
            if breakout:
                reason = f"{tk} is showing a sharp 21-day breakout (+{exc21:.1f}pp vs SPY) — momentum just turned strong even though the 63-day trend hasn't fully confirmed yet ({exc63:+.1f}pp)."
            elif exc63 > 0 and exc21 > 0:
                reason = f"{tk} is outperforming SPY on both timeframes — +{exc63:.1f}pp over 63 days and +{exc21:.1f}pp over 21 days — sustained, not a one-week spike."
            elif exc63 > 0:
                reason = f"{tk} has a positive 63-day trend (+{exc63:.1f}pp vs SPY) but has cooled off recently ({exc21:+.1f}pp over 21 days)."
            else:
                reason = f"{tk} is currently lagging SPY ({exc63:+.1f}pp over 63 days) — included here for context, not currently the leader."
            stock_reasoning.append({
                "ticker": tk,
                "conviction": conv,
                "is_recommended": is_rec,
                "reason": reason,
            })

        # ETF-side reasoning when the ETF itself is the recommendation
        etf_reasoning = None
        if rec_type == "etf":
            etf_reasoning = f"{ind['etf']} scored {conviction}/100 on its own 63-day momentum vs SPY ({excess:+.1f}pp). The strongest individual stock scanned inside this industry only reached {stock_leaders[0]['conviction'] if stock_leaders else 0}/100 — not enough edge over the ETF to justify single-stock concentration risk right now."

        # Capital allocation guidance — how much of YOUR actual cash this would use
        active_sleeve_value = sum(
            (p.get("current_price", 0) or 0) * (p.get("qty", 0) or 0)
            for p in positions
            if p.get("ticker") not in ("SPY", "BTC", "ETH", "XRP", "ZEC")
        ) + (cash or 0)
        if rec_conviction >= 88:
            size_pct = 0.25
        elif rec_conviction >= 80:
            size_pct = 0.20
        elif rec_conviction >= 75:
            size_pct = 0.15
        else:
            size_pct = 0.0  # below entry threshold — informational only, not an actionable size

        if size_pct > 0 and active_sleeve_value > 0:
            dollar_size = round(active_sleeve_value * size_pct, 0)
            cash_available = cash or 0
            if cash_available >= dollar_size:
                allocation_guidance = f"At {rec_conviction}/100 conviction this would size at {size_pct:.0%} of your active sleeve (~${dollar_size:,.0f}). You currently have ${cash_available:,.0f} in cash — enough to fund this without touching existing positions."
            else:
                shortfall = dollar_size - cash_available
                allocation_guidance = f"At {rec_conviction}/100 conviction this would size at {size_pct:.0%} of your active sleeve (~${dollar_size:,.0f}). You have ${cash_available:,.0f} in cash, about ${shortfall:,.0f} short — this would require trimming an existing lower-conviction position or using less than full size."
        else:
            allocation_guidance = f"Conviction {rec_conviction}/100 is below the 75 entry threshold — this is informational context only, not a sized recommendation yet. No capital should be allocated here until conviction rises."

        industry_opportunities.append({
            "industry": industry_name,
            "allocation_guidance": allocation_guidance,
            "etf": ind["etf"],
            "conviction": conviction,
            "recommended_security": rec_security,
            "recommended_type": rec_type,
            "recommended_conviction": rec_conviction,
            "stock_leaders": stock_leaders,
            "stock_reasoning": stock_reasoning,
            "etf_reasoning": etf_reasoning,
            "term": _classify_term(ind),
            "bullets": bullets,
            "vehicle": vehicle,
            "stocks": [s["ticker"] for s in stock_leaders[:4]],
            "why_now": _get_why_now(ind),
        })

    # Afternoon-specific sections
    what_changed = []
    notable_moves = []
    afternoon_positions = []
    afternoon_candidates = []

    if run_type == "afternoon":
        aft_sections = briefing.get("sections", {}) if briefing else {}
        raw_text = briefing.get("raw_text", "") if briefing else ""

        # If section parsing found nothing, try re-parsing from raw text
        if not any(aft_sections.values()) and raw_text:
            import re
            found = {}
            parts = re.split(r"^## ", raw_text, flags=re.MULTILINE)
            for part in parts[1:]:
                lines = part.split(chr(10))
                sec_name = lines[0].strip()
                sec_content = chr(10).join(lines[1:]).strip()
                found[sec_name] = sec_content
            if found:
                aft_sections = found
                log(f"Re-parsed afternoon sections from raw: {list(found.keys())}")

        # What Changed
        aft_text = (
            aft_sections.get("What Changed Since Morning") or
            aft_sections.get("What Changed") or ""
        )
        what_changed = _extract_bullets(aft_text)
        if not what_changed and raw_text:
            # Last resort: look for any lines after "What Changed" in raw text
            match = re.search(r"What Changed.*?\n(.*?)(?=##|$)", raw_text, re.DOTALL | re.IGNORECASE)
            if match:
                what_changed = _extract_bullets(match.group(1))

        # Notable Price Moves
        notable_text = (
            aft_sections.get("Notable Price Moves") or
            aft_sections.get("Notable Moves") or ""
        )
        notable_moves = _extract_bullets(notable_text)
        if not notable_moves:
            notable_moves = ["⚠️ Notable price moves unavailable — Claude output could not be parsed. Check GitHub Actions logs for this run."]

        # Portfolio Actions Before Close
        portfolio_actions_text = (
            aft_sections.get("Portfolio Actions Before Close") or
            aft_sections.get("Portfolio Review") or
            aft_sections.get("Portfolio Actions") or ""
        )
        afternoon_positions = _parse_afternoon_positions(portfolio_actions_text, positions)

        # If no positions parsed, show error message
        if not afternoon_positions:
            afternoon_positions = []
            for p in positions:
                entry = p.get("entry", 0) or p.get("entry_price", 0) or 0
                current = p.get("current_price", 0) or 0
                qty = p.get("qty", 0) or 0
                pct = round((current - entry) / entry * 100, 2) if entry > 0 else 0
                afternoon_positions.append({
                    "ticker": p.get("ticker", ""),
                    "action": "Hold",
                    "entry_price": entry,
                    "current_price": current,
                    "qty": qty,
                    "pct_change": pct,
                    "bullets": [f"Entry: ${entry:.2f} | Current: ${current:.2f} | P&L: {pct:+.1f}%", "⚠️ Portfolio actions could not be parsed — check GitHub Actions logs for this run."],
                })

        # New or Strengthened Candidates
        candidates_text = (
            aft_sections.get("New or Strengthened Candidates") or
            aft_sections.get("New Opportunities") or ""
        )
        afternoon_candidates = _parse_afternoon_candidates(candidates_text, industry_opportunities)

        # Close watch appended to what_changed
        close_watch = aft_sections.get("Market Close Watch", "")
        if close_watch and close_watch.strip():
            what_changed.append(f"<b>Close watch:</b> {close_watch.strip()}")

        # If still nothing in what_changed, show a default
        if not what_changed:
            what_changed = ["⚠️ What Changed section unavailable — Claude output could not be parsed. Check GitHub Actions logs for this run."]

        # Read existing dashboard data to preserve morning-only fields during afternoon runs
    _morning_catalysts = []
    _morning_position_review = []
    _morning_news = []
    try:
        import os as _os2
        _existing_path = _os2.path.join(_os2.path.dirname(__file__), "..", "..", "dashboard_data.js")
        if _os2.path.exists(_existing_path):
            with open(_existing_path) as _ef:
                _existing_raw = _ef.read()
            import json as _json2
            _existing = _json2.loads(_existing_raw.replace("window.BRIEFING_DATA = ", "").rstrip(";"))
            _morning_catalysts = _existing.get("catalyst_opportunities", [])
            _morning_position_review = _existing.get("position_review", [])
            _morning_news = _existing.get("news", [])
    except Exception:
        pass

    # IMPORTANT: preserve morning briefing data — do not clear it
        # Morning position_review and industry_opportunities stay in their keys
        # so the morning briefing tab remains populated after afternoon run

    # Positions for portfolio tab — field names match positions.json exactly
    portfolio_positions = []
    for p in positions:
        entry = p.get("entry", 0) or p.get("entry_price", 0) or 0
        current = p.get("current_price", 0) or 0
        qty = p.get("qty", 0) or p.get("position_size", 0) or 0
        balance = round(current * qty, 2) if current and qty else 0
        # Use pre-calculated values from pipeline when entry is available
        # Fall back to pipeline-calculated values if entry is missing (e.g. crypto via yfinance)
        if entry > 0 and current > 0:
            pct_change = round((current - entry) / entry * 100, 2)
            dollar_change = round((current - entry) * qty, 2)
        else:
            # Trust pre-calculated values from pipeline
            pct_change = p.get("pct_change", 0) or 0
            dollar_change = p.get("dollar_change", 0) or 0

        portfolio_positions.append({
            "ticker": p.get("ticker", ""),
            "type": p.get("type", "Stock"),
            "term": p.get("term", p.get("holding_type", "Medium-term")),
            "qty": qty,
            "entry_price": entry,
            "current_price": current,
            "balance": balance,
            "pct_change": pct_change,
            "dollar_change": dollar_change,
            "summary": p.get("summary", p.get("thesis", "")),
            "catalyst": p.get("catalyst", ""),
            "why": p.get("why", ""),
            "what_to_do": p.get("what_to_do", ""),
            "industry": p.get("industry", p.get("ticker", "")),
            "cost_basis": p.get("cost_basis", 0),
        })

    # Override portfolio positions — same smart logic as position review
    _rd = _rules_decisions if "_rules_decisions" in dir() else {}
    # Find matching position_review entry for Claude's fresh text
    _pr_lookup = {pr.get("ticker"): pr for pr in position_review}
    for pp in portfolio_positions:
        ticker = pp.get("ticker", "")
        sig = _rd.get(ticker)
        pr_match = _pr_lookup.get(ticker, {})
        if sig:
            sig_action = sig.get("action", "").lower()
            sig_reason = sig.get("reason", "")
            if sig_action == "exit":
                pp["what_to_do"] = pr_match.get("what_to_do") or sig_reason[:250]
                pp["catalyst"] = pr_match.get("catalyst") or "No forward catalyst"
                pp["why"] = pr_match.get("why") or sig_reason[:250]
            elif sig_action == "watch":
                pp["what_to_do"] = pr_match.get("what_to_do") or sig_reason[:250]
            elif sig_action == "hold":
                # Use Claude's fresh text for holds
                pp["what_to_do"] = pr_match.get("what_to_do") or pp.get("what_to_do", "")
                pp["why"] = pr_match.get("why") or pp.get("why", "")
                pp["catalyst"] = pr_match.get("catalyst") or pp.get("catalyst", "")

    # Performance history — placeholder until real history is tracked
    perf_dates = []
    perf_portfolio = []
    perf_spy = []
    if performance_history:
        for row in performance_history:
            perf_dates.append(row.get("date", ""))
            perf_portfolio.append(row.get("portfolio_pct", 0))
            perf_spy.append(row.get("spy_pct", 0))

    data = {
        "last_updated": now,
        "finnhub_key": os.environ.get("FINNHUB_KEY", ""),
        "run_type": run_type,
        "regime": regime_label,
        "regime_confidence": "High",
        "market_open": _is_market_open(),
        "vix": vix,
        "vix_avg": vix_avg,
        "vix_trend": vix_trend,
        "vix_regime": vix_regime,
        "market_bullets": market_bullets,
        "positions": portfolio_positions,
        "cash": cash,
        "cost_basis": cost_basis,
        "vs_spy_pp": None,
        "performance_dates": perf_dates,
        "performance_portfolio": perf_portfolio,
        "performance_spy": perf_spy,
        "news": news_cards if news_cards else _morning_news,
        "forward_catalysts": [
            {
                "date": c.get("date", ""),
                "event": c.get("event", ""),
                "action": c.get("action", "Hold"),
                "entry_opportunity": c.get("entry_opportunity", "N/A"),
                "exit_opportunity": c.get("exit_opportunity", "N/A"),
                "affected_holdings": c.get("affected_holdings", []),
                "trim_percentage": c.get("trim_percentage", "N/A"),
            }
            for c in forward_catalysts
        ],
        "position_review": position_review if position_review else _morning_position_review,
        "industry_opportunities": [],  # Removed — catalyst scanner replaces this
        "what_changed": what_changed,
        "notable_moves": notable_moves,
        "afternoon_positions": afternoon_positions,
        "afternoon_candidates": afternoon_candidates,
        "intraday": intraday or {},
        "catalyst_opportunities": catalyst_opportunities if catalyst_opportunities else _morning_catalysts,
        "rules_engine": {
            "regime_score": (rules_output or {}).get("regime_score", 0),
            "regime": (rules_output or {}).get("regime", "Yellow"),
            "exit_signals": (rules_output or {}).get("exit_signals", []),
            "entry_signals": (rules_output or {}).get("entry_signals", []),
            "crypto_check": (rules_output or {}).get("crypto_check", {}),
            "kill_criteria": (rules_output or {}).get("kill_criteria", {}),
        },
    }

    js_content = "window.BRIEFING_DATA = " + json.dumps(data, indent=2, default=str) + ";"

    with open(DASHBOARD_DATA_FILE, "w") as f:
        f.write(js_content)

    log(f"Dashboard data written: {DASHBOARD_DATA_FILE} ({len(js_content)} chars)")


def _is_market_open() -> bool:
    eastern = pytz.timezone("America/New_York")
    now = datetime.now(eastern)
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=9, minute=30, second=0)
    market_close = now.replace(hour=16, minute=0, second=0)
    return market_open <= now <= market_close


def _parse_afternoon_positions(text: str, positions: list) -> list:
    """Parse Claude afternoon position review into structured list."""
    if not text:
        return []
    results = []
    pos_lookup = {p.get("ticker"): p for p in positions}
    current_ticker = None
    current_action = "Hold"
    current_bullets = []

    for line in text.split(chr(10)):
        line = line.strip()
        if not line:
            if current_ticker:
                raw = pos_lookup.get(current_ticker, {})
                entry = raw.get("entry", 0) or raw.get("entry_price", 0) or 0
                current = raw.get("current_price", 0) or 0
                qty = raw.get("qty", 0) or 0
                pct = round((current - entry) / entry * 100, 2) if entry > 0 else 0
                results.append({
                    "ticker": current_ticker,
                    "action": current_action,
                    "entry_price": entry,
                    "current_price": current,
                    "qty": qty,
                    "pct_change": pct,
                    "bullets": current_bullets[:4],
                })
                current_ticker = None
                current_bullets = []
            continue

        # Detect ticker line: "TICKER — ACTION" — strip markdown bold first
        clean_line = line.replace("**", "").replace("__", "")
        upper = clean_line.upper()
        has_sep = chr(8212) in clean_line or " — " in clean_line or " - " in clean_line
        detected = False
        if has_sep:
            parts = clean_line.replace(chr(8212), "—").split("—")
            if parts:
                candidate_raw = parts[0].strip().split()[0].upper() if parts[0].strip() else ""
                candidate = "".join(c for c in candidate_raw if c.isalnum())
                action_text = parts[1].strip().upper() if len(parts) > 1 else ""
                first_words = " ".join(action_text.split()[:3])
                matched_action = "Hold"
                if first_words.startswith("EXIT") or first_words.startswith("CLOSE") or first_words.startswith("SELL"):
                    matched_action = "Exit"
                elif first_words.startswith("TRIM") or first_words.startswith("REDUCE"):
                    matched_action = "Trim"
                elif first_words.startswith("WATCH") or first_words.startswith("MONITOR"):
                    matched_action = "Watch"
                elif "BUY MORE" in first_words or first_words.startswith("BUY"):
                    matched_action = "Buy More"
                elif first_words.startswith("HOLD"):
                    matched_action = "Hold"
                action = matched_action
                if candidate in pos_lookup or (len(candidate) <= 5 and candidate.isalpha()):
                        if current_ticker:
                            raw = pos_lookup.get(current_ticker, {})
                            entry = raw.get("entry", 0) or raw.get("entry_price", 0) or 0
                            current_p = raw.get("current_price", 0) or 0
                            qty = raw.get("qty", 0) or 0
                            pct = round((current_p - entry) / entry * 100, 2) if entry > 0 else 0
                            results.append({
                                "ticker": current_ticker,
                                "action": current_action,
                                "entry_price": entry,
                                "current_price": current_p,
                                "qty": qty,
                                "pct_change": pct,
                                "bullets": current_bullets[:4],
                            })
                        current_ticker = candidate
                        current_action = action.title()
                        current_bullets = []
                        break
        if not has_sep or not detected:
            # Bullet line
            if current_ticker and len(clean_line) > 10:
                cleaned = clean_line.lstrip("•-* ").strip()
                if cleaned:
                    current_bullets.append(cleaned)

    # Flush last ticker
    if current_ticker:
        raw = pos_lookup.get(current_ticker, {})
        entry = raw.get("entry", 0) or raw.get("entry_price", 0) or 0
        current_p = raw.get("current_price", 0) or 0
        qty = raw.get("qty", 0) or 0
        pct = round((current_p - entry) / entry * 100, 2) if entry > 0 else 0
        results.append({
            "ticker": current_ticker,
            "action": current_action,
            "entry_price": entry,
            "current_price": current_p,
            "qty": qty,
            "pct_change": pct,
            "bullets": current_bullets[:4],
        })

    # Fill in any positions Claude didn't mention as clean holds
    mentioned = {r["ticker"] for r in results}
    for p in positions:
        ticker = p.get("ticker", "")
        if ticker and ticker not in mentioned:
            entry = p.get("entry", 0) or p.get("entry_price", 0) or 0
            current_p = p.get("current_price", 0) or 0
            qty = p.get("qty", 0) or 0
            pct = round((current_p - entry) / entry * 100, 2) if entry > 0 else 0
            results.append({
                "ticker": ticker,
                "action": "Hold",
                "entry_price": entry,
                "current_price": current_p,
                "qty": qty,
                "pct_change": pct,
                "bullets": ["No new developments today — thesis intact, hold into tomorrow."],
            })

    return results


def _parse_afternoon_candidates(text: str, fallback_opportunities: list) -> list:
    """Parse Claude afternoon candidates section. Falls back to morning opportunities if empty."""
    if not text or len(text.strip()) < 30:
        return fallback_opportunities

    candidates = []
    current = None

    for line in text.split(chr(10)):
        line = line.strip()
        if not line:
            if current:
                candidates.append(current)
                current = None
            continue

        # Detect industry header line
        if " — " in line or chr(8212) in line:
            parts = line.replace(chr(8212), "—").split("—")
            if len(parts) >= 2 and "conviction" in line.lower() or any(w in line for w in ["NEW", "STRENGTHENED", "/100"]):
                if current:
                    candidates.append(current)
                conviction = 0
                import re
                m = re.search(r"(\d+)/100", line)
                if m:
                    conviction = int(m.group(1))
                status = "NEW" if "NEW" in line.upper() else "STRENGTHENED" if "STRENGTHENED" in line.upper() else "CONFIRMED"
                current = {
                    "industry": parts[0].strip(),
                    "conviction": conviction,
                    "status": status,
                    "bullets": [],
                    "vehicle": "",
                    "stocks": [],
                    "etf": "",
                    "term": "Medium-term",
                }
                continue

        if current:
            cleaned = line.lstrip("•-* ").strip()
            if cleaned and len(cleaned) > 10:
                current["bullets"].append(cleaned)

    if current:
        candidates.append(current)

    return candidates if candidates else fallback_opportunities


def _extract_bullets(text: str) -> list:
    if not text:
        return []
    bullets = []
    for line in text.split("\n"):
        line = line.strip().lstrip("•-*").strip()
        if line and len(line) > 15:
            bullets.append(line)
    return bullets[:5]


def _parse_position_review(text: str, positions: list) -> list:
    """Parse Claude morning position review — reads actual Claude output, enriched with price data."""
    pos_lookup = {p.get("ticker", ""): p for p in positions}
    reviews = []

    if text:
        # Parse Claude output: each position block starts with TICKER — ACTION
        current_ticker = None
        current_action = "Hold"
        current_bullets = []

        for line in text.split(chr(10)):
            stripped = line.strip()
            if not stripped:
                if current_ticker:
                    _flush_morning_position(current_ticker, current_action, current_bullets, pos_lookup, reviews)
                    current_ticker = None
                    current_bullets = []
                continue

            # Detect ticker header: TICKER — ACTION or **TICKER** — ACTION
            clean = stripped.lstrip("*#").strip()
            parts = clean.replace(chr(8212), "—").split("—")
            if len(parts) >= 2:
                candidate = parts[0].strip().lstrip("*").rstrip("*").strip().split()[0].upper()
                action_part = parts[1].strip().upper()
                if candidate in pos_lookup and any(a in action_part for a in ["HOLD","WATCH","TRIM","REDUCE","EXIT","BUY"]):
                    if current_ticker:
                        _flush_morning_position(current_ticker, current_action, current_bullets, pos_lookup, reviews)
                    current_ticker = candidate
                    current_action = next((a for a in ["EXIT","REDUCE","TRIM","WATCH","BUY MORE","HOLD"] if a in action_part), "Hold").title()
                    current_bullets = []
                    continue

            if current_ticker:
                cleaned = stripped.lstrip("•-* ").strip()
                if cleaned and len(cleaned) > 10:
                    current_bullets.append(cleaned)

        if current_ticker:
            _flush_morning_position(current_ticker, current_action, current_bullets, pos_lookup, reviews)

    # Fill any positions Claude did not mention
    mentioned = {r["ticker"] for r in reviews}
    for p in positions:
        ticker = p.get("ticker", "")
        if ticker and ticker not in mentioned:
            entry = p.get("entry", 0) or p.get("entry_price", 0) or 0
            current = p.get("current_price", 0) or 0
            qty = p.get("qty", 0) or 0
            pct = round((current - entry) / entry * 100, 2) if entry > 0 else 0
            what_to_do = p.get("what_to_do", "")

            # Resolve action from what_to_do text
            resolved_action = "Hold"
            if what_to_do:
                wtd_upper = what_to_do.upper()
                if wtd_upper.startswith("CLOSE") or "CLOSE —" in wtd_upper:
                    resolved_action = "Close"
                elif wtd_upper.startswith("WATCH") or "WATCH —" in wtd_upper:
                    resolved_action = "Watch"
                elif wtd_upper.startswith("TRIM") or "TRIM —" in wtd_upper:
                    resolved_action = "Trim"
                elif wtd_upper.startswith("EXIT"):
                    resolved_action = "Exit"
                elif "HOLD AND MONITOR" in wtd_upper or "MONITOR" in wtd_upper:
                    resolved_action = "Watch"

            # Build bullets from what_to_do
            real_bullets = [f"Entry: ${entry:.2f} | Current: ${current:.2f} | P&L: {pct:+.1f}%"]
            if what_to_do:
                for sentence in what_to_do.replace("\n", " ").split("."):
                    s = sentence.strip().lstrip("- •*").strip()
                    if len(s) > 20:
                        real_bullets.append(s + ".")

            reviews.append({
                "ticker": ticker,
                "action": resolved_action,
                "entry_price": entry,
                "current_price": current,
                "pct_change": pct,
                "bullets": real_bullets[:5],
                "reasoning": what_to_do or "Hold — thesis intact.",
                "summary": p.get("summary", ""),
                "catalyst": p.get("catalyst", ""),
                "why": p.get("why", ""),
                "what_to_do": what_to_do,
                "industry": p.get("industry", ""),
                "term": p.get("term", ""),
            })

    return reviews


def _flush_morning_position(ticker, action, bullets, pos_lookup, reviews):
    p = pos_lookup.get(ticker, {})
    entry = p.get("entry", 0) or p.get("entry_price", 0) or 0
    current = p.get("current_price", 0) or 0
    qty = p.get("qty", 0) or 0
    pct = round((current - entry) / entry * 100, 2) if entry > 0 else 0
    header = f"Entry: ${entry:.2f} | Current: ${current:.2f} | P&L: {pct:+.1f}%"

    # Get the stored what_to_do from positions.json as the authoritative reasoning
    what_to_do = p.get("what_to_do", "")

    # Extract real action from what_to_do text if parser didn't find it
    resolved_action = action
    if what_to_do:
        wtd_upper = what_to_do.upper()
        if wtd_upper.startswith("CLOSE") or "CLOSE —" in wtd_upper or "EXIT —" in wtd_upper:
            resolved_action = "Close"
        elif wtd_upper.startswith("WATCH") or "WATCH —" in wtd_upper:
            resolved_action = "Watch"
        elif wtd_upper.startswith("TRIM") or "TRIM —" in wtd_upper:
            resolved_action = "Trim"
        elif wtd_upper.startswith("EXIT"):
            resolved_action = "Exit"
        elif "HOLD AND MONITOR" in wtd_upper or "HOLD AND WATCH" in wtd_upper or "MONITOR" in wtd_upper:
            resolved_action = "Watch"

    # Build real bullets from what_to_do text
    real_bullets = [header]
    if what_to_do:
        for sentence in what_to_do.replace("\n", " ").split("."):
            s = sentence.strip().lstrip("- •*").strip()
            if len(s) > 20:
                real_bullets.append(s + ".")
    if not real_bullets[1:] and bullets:
        real_bullets.extend(bullets)

    reviews.append({
        "ticker": ticker,
        "action": resolved_action,
        "entry_price": entry,
        "current_price": current,
        "pct_change": pct,
        "bullets": real_bullets[:5],
        "reasoning": what_to_do or (bullets[0] if bullets else ""),
        "summary": p.get("summary", ""),
        "catalyst": p.get("catalyst", ""),
        "why": p.get("why", ""),
        "what_to_do": what_to_do,
        "industry": p.get("industry", ""),
        "term": p.get("term", ""),
    })


def _classify_term(ind: dict) -> str:
    conviction = ind.get("conviction_score", 0)
    excess = ind.get("excess_63d", 0)
    if excess > 15 and conviction >= 70:
        return "Medium-term"
    elif conviction >= 45:
        return "Medium-term"
    return "Short-term"


def _get_why_now(ind: dict) -> str:
    parts = []
    excess = ind.get("excess_63d", 0)
    conviction = ind.get("conviction_score", 0)
    event_score = int(ind.get("event_score", 0.5) * 100)
    macro = ind.get("macro_alignment", "Neutral")

    if excess > 20:
        parts.append(f"This industry has outrun SPY by {excess:.1f}pp over 63 days — that is not noise, it is sustained institutional buying.")
    elif excess > 10:
        parts.append(f"Consistent {excess:.1f}pp outperformance vs SPY over 63 days signals real money rotating into this sector.")

    if event_score >= 70:
        parts.append(f"Event catalyst score of {event_score}/100 indicates multiple confirmed near-term catalysts that could drive further upside.")
    elif event_score >= 50:
        parts.append(f"Event score of {event_score}/100 — moderate near-term catalyst activity supporting the thesis.")

    if ind.get("ripple_benefits"):
        parts.append(f"Positive spillover effects from: {', '.join(ind['ripple_benefits'][:3])} are amplifying sector momentum.")

    if macro == "Green":
        parts.append("Current macro regime (low VIX, risk-on) is directly favorable for this type of sector exposure.")
    elif macro == "Yellow":
        parts.append("Macro is neutral — sector strength here is coming from fundamentals and catalysts, not just a rising tide.")

    if conviction >= 75:
        parts.append(f"Conviction score of {conviction}/100 — this is a high-confidence setup where multiple independent signals are aligned.")
    elif conviction >= 60:
        parts.append(f"Conviction score of {conviction}/100 — solid setup with most signals pointing the same direction.")

    return " ".join(parts) if parts else "Quantitative momentum and event signals are aligned for this industry."
