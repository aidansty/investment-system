# All Claude prompt templates live here.
# Edit this file to improve briefing quality over time.
# Never hardcode prompts anywhere else in the codebase.

DAILY_BRIEFING_SYSTEM_PROMPT = """
You are generating a daily morning investment briefing. Your only job is to
synthesize the verified data in the context block into a clean, actionable output.

ABSOLUTE RULES — NEVER VIOLATE THESE:
1. Every number, price, date, and fact must come from the context block.
   You never invent, estimate, or infer data.
2. If a field says None or N/A, do not use it. Do not substitute a guess.
3. Do not reference company names or business descriptions.
   Use ticker symbols only. The user knows what the companies do.
4. Do not use jargon: no "momentum play", no "technical setup", no "breakout".
   Write plain English that a non-specialist can act on.
5. Do not add sections, headers, bullet points, or commentary beyond what
   the output format specifies. Six lines per candidate, no exceptions.
6. The WHY THIS TRADE must contain four things in order:
   (1) what the stock has been doing and why it is showing strength
   (2) what the upcoming catalyst is and why the timing makes sense now
   (3) what combination of factors makes this a genuine entry and not just
       a stock that has moved up
   (4) one sentence on what must remain true for the trade to work
   Do not add a fifth sentence. Do not add sub-points.
7. If catalyst_confirmed is False, do not present an earnings date as certain.
   Write "an unconfirmed earnings date" or "a probable catalyst around [date]".
8. The FLAGS line surfaces only things that change what the user does:
   insider selling, sector overlap, implied move warning, extended move,
   no confirmed catalyst. If nothing material: write exactly "No flags."
"""


def build_daily_briefing_prompt(regime, macro, news, candidates, positions, today):
    """
    Assembles verified context block for Claude.
    All new signal fields are passed explicitly.
    Claude receives conclusions, not raw scores.
    """

    # News block
    news_block = ""
    for i, article in enumerate(news[:15], 1):
        dt = article.get("datetime", "")[:16] if article.get("datetime") else ""
        headline = article.get("headline", "")
        source = article.get("source", "")
        news_block += str(i) + ". [" + dt + "] " + headline + " (" + source + ")\n"

    # Economic calendar
    economic_calendar = macro.get("economic_calendar", None)
    if economic_calendar is None:
        calendar_block = "Economic calendar data not provided."
    elif len(economic_calendar) == 0:
        calendar_block = "No major economic releases detected today."
    else:
        calendar_block = ""
        for event in economic_calendar:
            calendar_block += "- " + event["name"] + ": " + event["status"] + " (" + event["date"] + ")\n"

    # Strong candidates — pass ALL new signal fields explicitly
    strong = candidates.get("strong", [])
    strong_top5 = strong[:5]
    strong_remainder = strong[5:]

    strong_block = ""
    for c in strong_top5:
        ticker = c["ticker"]
        current_price = c.get("current_price", "N/A")

        # Catalyst description — respect confirmed status
        has_catalyst = c.get("has_catalyst", False)
        confirmed = c.get("catalyst_confirmed", False)
        days = c.get("days_to_catalyst")
        cat_date = c.get("catalyst_date", "N/A")

        if has_catalyst and confirmed:
            catalyst_str = "Confirmed earnings in " + str(days) + " trading days (" + str(cat_date) + ")"
        elif has_catalyst and not confirmed:
            catalyst_str = "Unconfirmed earnings approximately " + str(days) + " trading days out (" + str(cat_date) + " — date not yet confirmed by company)"
        else:
            catalyst_str = "No catalyst in 5-42 day window"

        # Freshness
        freshness = c.get("freshness", "Fresh")
        freshness_note = c.get("freshness_note", "")
        entry_line = freshness
        if freshness == "Extended":
            entry_line = "Extended — wait for pullback or reduce size"
        elif freshness == "Pulling Back":
            entry_line = "Pulling back — potential better entry forming"
        elif freshness == "Watch":
            entry_line = "Overextended — do not enter"

        # Stop and targets
        atr_stop = c.get("atr_stop_price", "N/A")
        tier1_target = c.get("tier1_target_price", "N/A")
        pre_exit_date = c.get("pre_earnings_exit_date", "N/A")
        position_size = c.get("final_position_size", "Full")

        # Implied move
        implied_move = c.get("implied_move_pct")
        implied_check = c.get("implied_move_check", "Not Checked")

        # Earnings reaction quality
        reaction = c.get("reaction_quality", "Neutral")

        # Flags
        flags_str = c.get("flags_str", "No flags")

        # Sector
        sector = c.get("sector", "Other")
        sub_industry = c.get("sub_industry", "Other")
        overlap = c.get("sector_overlap_with")

        # Beat streak
        streak = c.get("beat_streak", 0)

        strong_block += "\n---\n"
        strong_block += "TICKER: " + ticker + "\n"
        strong_block += "current_price: $" + str(current_price) + "\n"
        strong_block += "stock_63d_return: " + str(c.get("rs_return", "N/A")) + "%\n"
        strong_block += "spy_outperformance: " + str(round(c.get("raw_rs") or c.get("rs_score", 0), 1)) + "pp over 63 days\n"
        strong_block += "consecutive_beats: " + str(streak) + " quarters\n"
        strong_block += "earnings_reaction_history: " + reaction + "\n"
        strong_block += "catalyst: " + catalyst_str + "\n"
        strong_block += "freshness_status: " + freshness + " | " + freshness_note + "\n"
        strong_block += "entry_instruction: " + entry_line + "\n"
        strong_block += "position_size_instruction: " + position_size + " position\n"
        strong_block += "atr_stop_price: $" + str(atr_stop) + "\n"
        strong_block += "tier1_exit_price: $" + str(tier1_target) + "\n"
        strong_block += "pre_earnings_exit_date: " + str(pre_exit_date) + "\n"
        strong_block += "sector: " + sector + " / " + sub_industry + "\n"
        if overlap:
            strong_block += "sector_overlap_with: " + str(overlap) + "\n"
        if implied_move:
            strong_block += "implied_earnings_move: +/-" + str(implied_move) + "% | compatibility: " + implied_check + "\n"
        strong_block += "flags: " + flags_str + "\n"

    if strong_remainder:
        tickers = ", ".join(c["ticker"] for c in strong_remainder)
        strong_block += "\nAdditional strong candidates (met all criteria): " + tickers + "\n"

    # Developing candidates
    developing_block = ""
    for c in candidates.get("developing", [])[:8]:
        missing = c.get("missing_signal", "Below threshold")
        developing_block += "- " + c["ticker"] + ": " + missing + "\n"

    # Open positions
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

    # Regime conditions
    conditions_block = ""
    for name, data in regime.get("conditions", {}).items():
        status = "BULLISH" if data["bullish"] else ("BEARISH" if data["bearish"] else "NEUTRAL")
        conditions_block += "- " + name + ": " + status + " -- " + str(data["value"]) + "\n"

    # VIX regime from first strong candidate (all share same scan)
    vix_regime = "Green"
    if strong:
        vix_regime = strong[0].get("vix_regime", "Green")

    return (
        "\nDATE: " + str(today) + "\n\n"
        "MARKET REGIME:\n"
        "Label: " + regime["label"] + "\n"
        "Confidence: " + regime["confidence"] + "\n"
        "Bullish signals: " + str(regime["bullish_points"]) + "/5\n"
        "Bearish signals: " + str(regime["bearish_points"]) + "/5\n"
        "VIX Regime: " + vix_regime + "\n"
        "Max positions allowed today: " + str(regime["max_positions"]) + "\n"
        "Minimum cash to maintain: " + str(int(regime["min_cash_pct"] * 100)) + "%\n\n"
        "Condition breakdown:\n" + conditions_block + "\n"
        "ECONOMIC CALENDAR:\n" + calendar_block + "\n\n"
        "TODAY'S NEWS (last 24 hours):\n"
        + (news_block if news_block else "No news data available.") + "\n\n"
        "STRONG CANDIDATES (" + str(len(strong)) + " found — showing top 5):\n"
        + (strong_block if strong_block else "No strong candidates today.") + "\n\n"
        "DEVELOPING CANDIDATES (" + str(len(candidates.get("developing", []))) + " found):\n"
        + (developing_block if developing_block else "None today.") + "\n\n"
        "OPEN POSITIONS (" + str(len(positions)) + " held):\n"
        + (positions_block if positions_block else "No open positions.") + "\n\n"
        "---\n"
        "OUTPUT FORMAT — FOLLOW EXACTLY, NO DEVIATIONS:\n\n"
        "## Market Regime\n"
        "Write this header line first, exactly:\n"
        "[Regime] — [Confidence] Confidence | VIX [GREEN/YELLOW/RED] | [N] Strong | [N] Developing\n\n"
        "Then one sentence only on what this means for deploying capital today.\n\n"
        "## Market News Summary\n"
        "2-3 sentences. Only news relevant to held positions or strong candidates.\n"
        "If nothing relevant: one sentence saying so.\n\n"
        "## Today's Key Events\n"
        "Report from ECONOMIC CALENDAR only. If none: 'No major economic releases today.'\n\n"
        "## Open Position Review\n"
        "For each position: TICKER — HOLD/WATCH/REDUCE/EXIT. One sentence reason.\n"
        "If none: 'No open positions.'\n\n"
        "## Strong Candidates\n"
        "For each strong candidate, write EXACTLY these six lines. Nothing else.\n"
        "No bullet points. No sub-headers. No extra commentary.\n\n"
        "TICKER\n\n"
        "WHY THIS TRADE\n"
        "Write exactly 3-4 sentences covering in order:\n"
        "(1) What the stock has been doing and why it is showing strength — use stock_63d_return and spy_outperformance\n"
        "(2) What the catalyst is and why the timing makes sense — use catalyst field, respect confirmed vs unconfirmed\n"
        "(3) What combination of factors makes this a genuine entry — use consecutive_beats, earnings_reaction_history, freshness_status\n"
        "(4) One sentence on what must remain true for this trade to work\n"
        "No jargon. No score references. Write so another analyst could verify the signal independently.\n\n"
        "ENTRY: [use entry_instruction field exactly]\n\n"
        "POSITION SIZE: [use position_size_instruction field exactly]\n\n"
        "STOP: $[use atr_stop_price field]\n\n"
        "EXIT PLAN: Take half off at $[tier1_exit_price] — exit remainder by [pre_earnings_exit_date] before earnings\n"
        "Use this format whenever pre_earnings_exit_date is not None, regardless of confirmed status.\n"
        "Only use the trailing stop format if pre_earnings_exit_date is None.\n\n"
        "FLAGS: [use flags field. Add implied move warning if implied_earnings_move is present and check is Warning or Mismatch. "
        "Add 'No confirmed earnings date' if catalyst_confirmed is False. "
        "If nothing material: write exactly 'No flags.']\n\n"
        "---\n\n"
        "## Developing Candidates\n"
        "One bullet per candidate. One sentence explaining what is missing in plain English.\n\n"
        "## Risk Assessment\n"
        "One sentence only. Is this a good day to open new positions or exercise caution?\n"
        "Name one specific reason from the data. No generic market commentary.\n"
    )
