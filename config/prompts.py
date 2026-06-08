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
6. If signals conflict — for example a bullish regime with negative news and
   zero strong candidates, or a bearish regime with strong individual setups —
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


def build_daily_briefing_prompt(
    regime: dict,
    macro: dict,
    news: list,
    candidates: dict,
    positions: list,
    today: str
) -> str:
    """
    Assembles the full verified context block and output instructions.
    Claude receives only this data — nothing external, nothing invented.

    Composite score formula (for context interpretation):
    score = (rs_normalized * 0.40) + (earnings_score * 0.35) + (catalyst_score * 0.25)
    Higher score = stronger combination of momentum, earnings consistency, and timing.
    """

    # Format news headlines
    news_block = ""
    for i, article in enumerate(news[:15], 1):
        dt = article.get("datetime", "")[:16] if article.get("datetime") else ""
        news_block += f"{i}. [{dt}] {article['headline']} ({article['source']})\n"

    # Format economic calendar
    economic_calendar = macro.get("economic_calendar", None)
    if economic_calendar is None:
        calendar_block = "Economic calendar data not provided."
    elif len(economic_calendar) == 0:
        calendar_block = "No major economic releases detected today."
    else:
        calendar_block = ""
        for event in economic_calendar:
            calendar_block += f"- {event['name']}: {event['status']} ({event['date']})\n"

    # Format strong candidates — top 5 only
    strong = candidates.get("strong", [])
    strong_top5 = strong[:5]
    strong_remainder = strong[5:]

    strong_block = ""
    for c in strong_top5:
        catalyst_str = (
            f"Earnings in {c['days_to_catalyst']} trading days ({c['catalyst_date']})"
            if c.get("has_catalyst") else "No upcoming catalyst in window"
        )
        strong_block += f"""
TICKER: {c['ticker']}
Outperformed SPY by: {c['rs_score']:+.1f} percentage points over 63 days
Stock 63-day return: {c['rs_return']:+.1f}%
Consecutive earnings beats: {c['beat_streak']} quarters in a row
Catalyst: {catalyst_str}
Composite score: {c['composite_score']:.3f}
"""

    if strong_remainder:
        tickers = ", ".join(c['ticker'] for c in strong_remainder)
        strong_block += f"\nAdditional strong candidates not shown: {tickers}\n"

    # Format developing candidates — include explicit failure reason
    developing_block = ""
    for c in candidates.get("developing", [])[:8]:
        catalyst_str = (f"earnings in {c['days_to_catalyst']}d"
                       if c.get("has_catalyst") else "no catalyst in window")
        missing = c.get("missing_signal", "Unknown")
        developing_block += (
            f"- {c['ticker']}: RS {c['rs_score']:+.1f}pp | "
            f"{c['beat_streak']} consecutive beats | {catalyst_str} | "
            f"Missing: {missing}\n"
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

        positions_block += f"""
TICKER: {p['ticker']}
Entry: ${entry:.2f} | Current: ${current:.2f} | P&L: {pnl:+.1f}%
Stop: ${stop:.2f} ({dist_stop:+.1f}% from current) | Target: ${target:.2f} ({dist_target:+.1f}% from current)
Original thesis: {p.get('thesis', 'Not recorded')}
"""

    # Format regime conditions
    conditions_block = ""
    for name, data in regime.get("conditions", {}).items():
        status = "BULLISH" if data["bullish"] else ("BEARISH" if data["bearish"] else "NEUTRAL")
        conditions_block += f"- {name}: {status} — {data['value']}\n"

    return f"""
DATE: {today}

MARKET REGIME:
Label: {regime['label']}
Confidence: {regime['confidence']}
Bullish signals: {regime['bullish_points']}/5
Bearish signals: {regime['bearish_points']}/5
Data degraded: {regime.get('degraded', False)}
Max positions allowed today: {regime['max_positions']}
Minimum cash to maintain: {regime['min_cash_pct']:.0%}
Stop loss width: {regime['stop_loss_pct']:.0%}

Condition breakdown:
{conditions_block}

ECONOMIC CALENDAR:
{calendar_block}

TODAY'S NEWS (verified headlines, last 24 hours):
{news_block if news_block else 'No news data available.'}

STRONG CANDIDATES ({len(strong)} found today — showing top 5):
{strong_block if strong_block else 'No strong candidates today.'}

DEVELOPING CANDIDATES ({len(candidates.get('developing', []))} found):
{developing_block if developing_block else 'None today.'}

OPEN POSITIONS ({len(positions)} held):
{positions_block if positions_block else 'No open positions.'}

---
REQUIRED OUTPUT — write each section exactly as shown.
Use paragraphs and bullet points. Never use tables or grids.

## Market Regime
2-3 sentences. What is the current market environment and what does it mean
for capital deployment today? Reference the specific signal values above.
If signals conflict, describe the conflict explicitly.

## Market News Summary
3-5 sentences. Focus only on news relevant to current positions, strong
candidates, or regime conditions. Explain how relevant headlines affect
positioning. If no headlines are relevant, state that clearly in one sentence.

## Today's Key Events
Report economic releases from the ECONOMIC CALENDAR section above.
If the calendar data was not provided, write:
"Economic calendar data not available for today."
If no releases are listed, write:
"No major economic releases detected today."
Do not invent or assume any events.

## Open Position Review
For each open position:
TICKER — HOLD / ADD / REDUCE / EXIT
One sentence explaining the action based on price relative to stop and target.
State whether the original thesis remains intact based on available data only.
If no positions: "No open positions to review."

## Strong Candidates
For each of the top 5 strong candidates:

**TICKER**
- Why it qualifies: describe each signal using only the data provided above
- Catalyst: what is it, when does it occur, why does it create a timing window
- Key risk: the single most important thing that could go wrong
- What ends the trade: one specific condition that would invalidate the setup

If additional strong candidates exist beyond the top 5, summarize them
in one short paragraph listing their tickers and noting they met all criteria.

## Developing Candidates
One bullet per candidate using the Missing field from the context:
- TICKER: explain in plain English what is missing and what would need to
  change for it to become a strong candidate

## Risk Assessment
2-3 sentences. Should new positions be opened today or is caution warranted?
Name any specific reason — from news, regime, or position data — to be more
careful than the regime label alone suggests. If everything aligns, say so.
"""
