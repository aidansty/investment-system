# All Claude prompt templates live here.
# Edit this file to improve briefing quality over time.
# Never hardcode prompts anywhere else in the codebase.
#
# COMPOSITE SCORE FORMULA (for developer reference):
# score = (rs_normalized * 0.40) + (earnings_score * 0.35) + (catalyst_score * 0.25)
#
# rs_normalized:   0.0-1.0, normalized excess return vs SPY within qualified pool
# earnings_score:  0.0=no beats, 0.3=1 beat, 0.6=2 beats, 0.8=3 beats, 1.0=4+ beats
# catalyst_score:  0.0=none, 0.5=catalyst 21-42 days away, 1.0=catalyst 5-20 days away
#
# Tier thresholds:
# Strong:     composite >= 0.65 AND earnings_score > 0
# Developing: composite >= 0.45 AND earnings_score > 0
# Watch:      composite < 0.45
#
# Weights are documented assumptions, not calibrated values.
# First calibration review: after 30 completed trades.

DAILY_BRIEFING_SYSTEM_PROMPT = """
You are a professional investment analyst generating a daily morning briefing
for a retail investor using a rules-based framework.

CORE RULES:
1. Every number, price, date, and data point you reference must come from the
   context block provided. You never invent data.
2. If information is unavailable in the provided context, state that it is
   unavailable. Do not infer, estimate, assume, or invent missing information.
   This applies to company descriptions, event dates, news implications,
   position reviews, and candidate analysis.
3. Do not reference company names, business descriptions, or sector details
   unless explicitly provided in the context. Use the ticker symbol only.
4. Provide clear interpretations of the data and identify actions consistent
   with the framework rules. Do not create new rules or override existing ones.
5. Do not present future price movements as certainties. Avoid language such
   as "will rise", "will fall", or "should rally". Instead describe setup
   quality, supporting evidence, key risks, and conditions that would
   invalidate the thesis.
6. If signals conflict -- for example a bullish regime with negative news and
   zero strong candidates, or a bearish regime with strong individual setups --
   explain the conflict explicitly. Do not force all evidence into a single
   bullish or bearish conclusion. Describe what is supportive and what is
   cautionary.
7. When summarizing news, prioritize headlines relevant to current positions,
   strong candidates, or market regime conditions. Do not spend significant
   space on headlines with no impact on portfolio decisions.
8. Only fully discuss the top 5 strong candidates by composite score.
   If more than 5 exist, summarize the remainder in one short paragraph.
9. Every sentence must either inform a decision or explain a risk.
   Remove anything that does neither.

WRITING STYLE:
- Plain English only. No financial jargon.
- Be specific. Reference actual tickers, actual prices, actual dates.
- Be concise. Short paragraphs and clear bullet points.
- Write for someone who is intelligent but not a finance professional.
"""


def build_daily_briefing_prompt(regime, macro, news, candidates, positions, today):
    """
    Assembles the full verified context block and output instructions.
    Claude receives only this data -- nothing external, nothing invented.

    Composite score formula (for context interpretation):
    score = (rs_normalized * 0.40) + (earnings_score * 0.35) + (catalyst_score * 0.25)
    Higher score = stronger combination of momentum, earnings consistency, and timing.
    """

    # Format news headlines
    news_block = ""
    for i, article in enumerate(news[:15], 1):
        dt = article.get("datetime", "")[:16] if article.get("datetime") else ""
        headline = article.get("headline", "")
        source = article.get("source", "")
        news_block += str(i) + ". [" + dt + "] " + headline + " (" + source + ")\n"

    # Format economic calendar
    economic_calendar = macro.get("economic_calendar", None)
    if economic_calendar is None:
        calendar_block = "Economic calendar data not provided."
    elif len(economic_calendar) == 0:
        calendar_block = "No major economic releases detected today."
    else:
        calendar_block = ""
        for event in economic_calendar:
            calendar_block += "- " + event["name"] + ": " + event["status"] + " (" + event["date"] + ")\n"

    # Format strong candidates -- top 5 only
    strong = candidates.get("strong", [])
    strong_top5 = strong[:5]
    strong_remainder = strong[5:]

    strong_block = ""
    for c in strong_top5:
        if c.get("has_catalyst"):
            catalyst_str = "Earnings in " + str(c["days_to_catalyst"]) + " trading days (" + str(c["catalyst_date"]) + ")"
        else:
            catalyst_str = "No upcoming catalyst in window"

        strong_block += "\nTICKER: " + c["ticker"] + "\n"
        strong_block += "Outperformed SPY by: " + str(round(c["rs_score"], 1)) + " percentage points over 63 days\n"
        strong_block += "Stock 63-day return: " + str(round(c["rs_return"], 1)) + "%\n"
        strong_block += "Consecutive earnings beats: " + str(c["beat_streak"]) + " quarters in a row\n"
        strong_block += "Catalyst: " + catalyst_str + "\n"
        strong_block += "Composite score: " + str(c["composite_score"]) + "\n"

    if strong_remainder:
        tickers = ", ".join(c["ticker"] for c in strong_remainder)
        strong_block += "\nAdditional strong candidates not shown: " + tickers + "\n"

    # Format developing candidates -- include explicit failure reason
    developing_block = ""
    for c in candidates.get("developing", [])[:8]:
        if c.get("has_catalyst"):
            catalyst_str = "earnings in " + str(c["days_to_catalyst"]) + "d"
        else:
            catalyst_str = "no catalyst in window"
        missing = c.get("missing_signal", "Unknown")
        developing_block += (
            "- " + c["ticker"] + ": RS " + str(round(c["rs_score"], 1)) + "pp | "
            + str(c["beat_streak"]) + " consecutive beats | " + catalyst_str
            + " | Missing: " + missing + "\n"
        )

    # Format open positions
    positions_block = ""
    for p in positions:
        if not p.get("ticker"):
            continue
        entry = p.get("entry_price") or 0
        current = p.get("current_price") or 0
        stop = p.get("stop_price") or 0
        target = p.get("target_price") or 0
        pnl = ((current - entry) / entry * 100) if entry > 0 else 0
        dist_stop = ((current - stop) / current * 100) if current > 0 else 0
        dist_target = ((target - current) / current * 100) if current > 0 else 0

        positions_block += "\nTICKER: " + p["ticker"] + "\n"
        positions_block += "Entry: $" + str(round(entry, 2)) + " | Current: $" + str(round(current, 2)) + " | P&L: " + str(round(pnl, 1)) + "%\n"
        positions_block += "Stop: $" + str(round(stop, 2)) + " (" + str(round(dist_stop, 1)) + "% from current) | Target: $" + str(round(target, 2)) + " (" + str(round(dist_target, 1)) + "% from current)\n"
        positions_block += "Original thesis: " + str(p.get("thesis", "Not recorded")) + "\n"

    # Format regime conditions
    conditions_block = ""
    for name, data in regime.get("conditions", {}).items():
        status = "BULLISH" if data["bullish"] else ("BEARISH" if data["bearish"] else "NEUTRAL")
        conditions_block += "- " + name + ": " + status + " -- " + str(data["value"]) + "\n"

    return (
        "\nDATE: " + str(today) + "\n\n"
        "MARKET REGIME:\n"
        "Label: " + regime["label"] + "\n"
        "Confidence: " + regime["confidence"] + "\n"
        "Bullish signals: " + str(regime["bullish_points"]) + "/5\n"
        "Bearish signals: " + str(regime["bearish_points"]) + "/5\n"
        "Data degraded: " + str(regime.get("degraded", False)) + "\n"
        "Max positions allowed today: " + str(regime["max_positions"]) + "\n"
        "Minimum cash to maintain: " + str(int(regime["min_cash_pct"] * 100)) + "%\n"
        "Stop loss width: " + str(int(regime["stop_loss_pct"] * 100)) + "%\n\n"
        "Condition breakdown:\n" + conditions_block + "\n"
        "ECONOMIC CALENDAR:\n" + calendar_block + "\n\n"
        "TODAY'S NEWS (verified headlines, last 24 hours):\n"
        + (news_block if news_block else "No news data available.") + "\n\n"
        "STRONG CANDIDATES (" + str(len(strong)) + " found today -- showing top 5):\n"
        + (strong_block if strong_block else "No strong candidates today.") + "\n\n"
        "DEVELOPING CANDIDATES (" + str(len(candidates.get("developing", []))) + " found):\n"
        + (developing_block if developing_block else "None today.") + "\n\n"
        "OPEN POSITIONS (" + str(len(positions)) + " held):\n"
        + (positions_block if positions_block else "No open positions.") + "\n\n"
        "---\n"
        "REQUIRED OUTPUT -- write each section exactly as shown.\n"
        "Use paragraphs and bullet points. Never use tables or grids.\n\n"
        "## Market Regime\n"
        "2-3 sentences. What is the current market environment and what does it mean\n"
        "for capital deployment today? Reference the specific signal values above.\n"
        "If signals conflict, describe the conflict explicitly.\n\n"
        "## Market News Summary\n"
        "3-5 sentences. Focus only on news relevant to current positions, strong\n"
        "candidates, or regime conditions. Explain how relevant headlines affect\n"
        "positioning. If no headlines are relevant, state that clearly in one sentence.\n\n"
        "## Today's Key Events\n"
        "Report economic releases from the ECONOMIC CALENDAR section above.\n"
        "If the calendar data was not provided, write:\n"
        "Economic calendar data not available for today.\n"
        "If no releases are listed, write:\n"
        "No major economic releases detected today.\n"
        "Do not invent or assume any events.\n\n"
        "## Open Position Review\n"
        "For each open position:\n"
        "TICKER -- HOLD / ADD / REDUCE / EXIT\n"
        "One sentence explaining the action based on price relative to stop and target.\n"
        "State whether the original thesis remains intact based on available data only.\n"
        "If no positions: No open positions to review.\n\n"
        "## Strong Candidates\n"
        "For each of the top 5 strong candidates:\n\n"
        "**TICKER**\n"
        "- Why it qualifies: describe each signal using only the data provided above\n"
        "- Catalyst: what is it, when does it occur, why does it create a timing window\n"
        "- Key risk: the single most important thing that could go wrong\n"
        "- What ends the trade: one specific condition that would invalidate the setup\n\n"
        "If additional strong candidates exist beyond the top 5, summarize them\n"
        "in one short paragraph listing their tickers and noting they met all criteria.\n\n"
        "## Developing Candidates\n"
        "One bullet per candidate using the Missing field from the context:\n"
        "- TICKER: explain in plain English what is missing and what would need to\n"
        "  change for it to become a strong candidate\n\n"
        "## Risk Assessment\n"
        "2-3 sentences. Should new positions be opened today or is caution warranted?\n"
        "Name any specific reason -- from news, regime, or position data -- to be more\n"
        "careful than the regime label alone suggests. If everything aligns, say so.\n"
    )
