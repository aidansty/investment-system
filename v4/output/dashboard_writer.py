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
    # Last resort: if still empty, build a basic explanation from macro data directly
    if not market_bullets and macro:
        vix_val = macro.get("vix", 0)
        vix_regime = macro.get("vix_regime", "Yellow")
        vix_trend = macro.get("vix_trend", "Flat")
        market_bullets = [
            f"VIX at {vix_val} is currently in the {vix_regime.lower()} range, trending {vix_trend.lower()}.",
            f"Regime classification: {vix_regime} — {'favorable for new entries' if vix_regime == 'Green' else 'selective entries only, catalyst required' if vix_regime == 'Yellow' else 'defensive posture, no new entries'}.",
        ]

    # News
    recent_news = news_package.get("recent_news", [])
    forward_catalysts = news_package.get("forward_catalysts", [])

    news_cards = []
    for n in recent_news[:8]:
        bullets = []
        summary = n.get("summary", "")
        if summary:
            for sentence in summary.replace(". ", ".|").split("|"):
                s = sentence.strip()
                if s and len(s) > 20:
                    bullets.append(s)
        # Add portfolio impact as a bullet if present
        impact = n.get("portfolio_impact", "") or n.get("impact", "")
        if impact and impact not in bullets:
            bullets.append(impact)
        # Add affected tickers
        affected = n.get("affected_tickers", []) or n.get("tickers", [])
        if affected:
            bullets.append(f"Affects: {', '.join(affected)}")
        news_cards.append({
            "headline": n.get("headline", ""),
            "url": n.get("url", ""),
            "source": n.get("source", ""),
            "bullets": bullets[:5],
            "affected_tickers": affected,
            "sentiment": n.get("sentiment", ""),
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

    # Industry opportunities
    top_industries = industry_results.get("top_industries", []) if industry_results else []
    industry_opportunities = []
    # Get industry section from Claude briefing for richer reasoning
    sections = briefing.get("sections", {}) if briefing else {}
    ind_briefing_text = (
        sections.get("Industry Opportunities") or
        sections.get("Top Industry Opportunities") or
        sections.get("Industry Candidates") or ""
    )

    for ind in top_industries[:3]:
        ind_news = ind.get("relevant_news", [])
        industry_name = ind["industry"]

        # Build rich bullets from actual data + news
        bullets = []
        excess = ind.get("excess_63d", 0)
        bullets.append(f"{ind['etf']} is outperforming SPY by {excess:+.1f} percentage points over the last 63 trading days — sustained momentum that goes beyond a one-day move.")

        if ind_news:
            for n in ind_news[:2]:
                headline = n.get("headline", "")
                summary = n.get("summary", "")
                if headline:
                    bullets.append(f"{headline}" + (f" — {summary[:300]}" if summary else ""))

        if ind.get("ripple_benefits"):
            bullets.append(f"Ripple tailwinds flowing in from related sectors: {', '.join(ind['ripple_benefits'][:3])}.")

        macro = ind.get("macro_alignment", "Neutral")
        event_score = int(ind.get("event_score", 0.5) * 100)
        bullets.append(f"Macro environment is {macro} for this industry. Event catalyst score: {event_score}/100 — {'multiple confirmed catalysts' if event_score >= 60 else 'moderate catalyst activity'}.")

        # Vehicle: ETF vs stocks with specific reasoning
        conviction = ind.get("conviction_score", 0)
        top_stocks = ind.get("top_stocks", []) or ind.get("validated_stocks", []) or []
        if conviction >= 70 and top_stocks:
            vehicle = f"Individual stocks — at this conviction level, concentrated positions in sector leaders outperform the ETF. Focus on: {', '.join(top_stocks[:3])}."
        elif conviction >= 55:
            vehicle = f"{ind['etf']} ETF — conviction is building but not yet high enough to concentrate in individual names. The ETF captures the sector move with less single-stock risk."
        else:
            vehicle = f"{ind['etf']} ETF — early-stage opportunity. Use the ETF for broad exposure until a clear sector leader emerges."

        industry_opportunities.append({
            "industry": industry_name,
            "etf": ind["etf"],
            "conviction": conviction,
            "term": _classify_term(ind),
            "bullets": bullets,
            "vehicle": vehicle,
            "stocks": top_stocks[:4],
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
        "news": news_cards,
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
        "position_review": position_review,
        "industry_opportunities": industry_opportunities,
        "what_changed": what_changed,
        "notable_moves": notable_moves,
        "afternoon_positions": afternoon_positions,
        "afternoon_candidates": afternoon_candidates,
        "intraday": intraday or {},
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

        # Detect ticker line: "TICKER — ACTION"
        upper = line.upper()
        for action in ["EXIT", "REDUCE", "TRIM", "WATCH", "HOLD", "BUY MORE"]:
            if action in upper and chr(8212) in line or " — " in line or " - " in line:
                parts = line.replace(chr(8212), "—").split("—")
                if parts:
                    candidate = parts[0].strip().split()[0].upper()
                    if candidate in pos_lookup or len(candidate) <= 5:
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
        else:
            # Bullet line
            if current_ticker and len(line) > 10:
                cleaned = line.lstrip("•-* ").strip()
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
