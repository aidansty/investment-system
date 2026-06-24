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
    market_overview = briefing.get("sections", {}).get("Market Overview", "") if briefing else ""
    market_bullets = _extract_bullets(market_overview)

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
                    bullets.append(f"{headline}" + (f" — {summary[:120]}" if summary else ""))

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
        aft_text = briefing.get("sections", {}).get("What Changed", "") if briefing else ""
        what_changed = _extract_bullets(aft_text)

        close_watch = briefing.get("sections", {}).get("Market Close Watch", "") if briefing else ""
        if close_watch:
            what_changed.append(f"<b>Close watch:</b> {close_watch.strip()}")

        afternoon_positions = position_review
        afternoon_candidates = industry_opportunities

        position_review = []
        industry_opportunities = []

    # Positions for portfolio tab — field names match positions.json exactly
    portfolio_positions = []
    for p in positions:
        entry = p.get("entry", 0) or p.get("entry_price", 0) or 0
        current = p.get("current_price", 0) or 0
        qty = p.get("qty", 0) or p.get("position_size", 0) or 0
        balance = round(current * qty, 2) if current and qty else 0
        pct_change = round((current - entry) / entry * 100, 2) if entry > 0 and current > 0 else 0
        dollar_change = round((current - entry) * qty, 2) if entry > 0 and qty else 0

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
    reviews = []
    for p in positions:
        ticker = p.get("ticker", "")
        if not ticker:
            continue
        entry = p.get("entry_price", 0) or 0
        current = p.get("current_price", 0) or 0
        stop = p.get("stop_price", 0) or 0
        pct = round((current - entry) / entry * 100, 2) if entry > 0 else 0
        dist_stop = round((current - stop) / current * 100, 2) if current > 0 and stop > 0 else None

        bullets = [
            f"Entry: ${entry:.2f} | Current: ${current:.2f} | P&L: {pct:+.1f}%",
        ]
        if dist_stop is not None:
            bullets.append(f"Stop at ${stop:.2f} ({dist_stop:.1f}% away from current price)")
        if pct <= -10:
            action = "Watch"
            reasoning = f"Down {pct:.1f}% — approaching mandatory review threshold. Thesis should be reassessed."
        elif pct <= -5:
            action = "Watch"
            reasoning = f"Down {pct:.1f}% from entry. Monitor closely but no action required yet."
        else:
            action = "Hold"
            reasoning = f"Position stable. No material changes to thesis today."

        reviews.append({
            "ticker": ticker,
            "action": action,
            "bullets": bullets,
            "reasoning": reasoning,
        })
    return reviews


def _classify_term(ind: dict) -> str:
    conviction = ind.get("conviction_score", 0)
    excess = ind.get("excess_63d", 0)
    if excess > 15 and conviction >= 70:
        return "Medium-term"
    elif conviction >= 45:
        return "Medium-term"
    return "Short-term"


def _get_why_now(ind: dict) -> str:
    reasons = []
    if ind.get("excess_63d", 0) > 10:
        reasons.append("sustained momentum outperformance")
    if ind.get("ripple_benefits"):
        reasons.append("macro ripple tailwinds")
    if ind.get("news_count", 0) >= 2:
        reasons.append("multiple confirming news catalysts")
    if ind.get("event_score", 0) >= 0.7:
        reasons.append("strong event catalyst score")
    if not reasons:
        return "Quantitative signals align with current macro conditions."
    return "Momentum and " + " plus ".join(reasons) + " are pointing the same direction simultaneously."
