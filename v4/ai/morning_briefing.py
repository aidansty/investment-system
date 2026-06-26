import os
import anthropic
from v4.utils.logger import log
from v4.utils.file_reader import read_one_pager, read_memory_log
from v4.config.settings import (
    CONVICTION_HIGH, CONVICTION_MEDIUM, MAX_INDUSTRIES_BRIEFING
)


def build_morning_context(
    macro: dict,
    industry_results: dict,
    news: list,
    forward_catalysts: list,
    positions: list,
    today: str,
    earnings_calendar: dict = None,
) -> str:
    """
    Assembles the complete context block for the morning briefing.
    Claude receives only structured, verified data.
    """

    # One-Pager and Memory Log
    one_pager = read_one_pager()
    memory = read_memory_log(last_n_days=7)

    # Macro block
    vix = macro.get("vix", 20.0)
    vix_regime = macro.get("vix_regime", "Yellow")
    vix_trend = macro.get("vix_trend", "Flat")
    econ_events = macro.get("economic_events", [])

    macro_block = f"""VIX: {vix} | Regime: {vix_regime} | Trend: {vix_trend}
Economic events today: {len(econ_events)}"""
    if econ_events:
        for e in econ_events[:3]:
            macro_block += f"\n- {e['name']} ({e['impact']} impact)"

    # News block — already deduplicated and summarized stories
    news_block = ""
    for i, item in enumerate(news, 1):
        headline = item.get("headline", "")
        summary = item.get("summary", "")
        category = item.get("category", "")
        news_block += f"{i}. {headline}\n"
        if summary:
            news_block += f"   {summary}\n"
        if category:
            news_block += f"   Category: {category}\n"

    # Forward catalysts block — events with specific future dates
    catalysts_block = ""
    for cat in forward_catalysts:
        event = cat.get("event", "")
        date_str = cat.get("date", "")
        why = cat.get("why_it_matters", "")
        action = cat.get("action_type", "")
        holdings = cat.get("affected_holdings", [])
        holdings_str = ", ".join(holdings) if holdings else "None — new opportunity"
        catalysts_block += f"[{date_str}] {event}\n"
        catalysts_block += f"   Why it matters: {why}\n"
        catalysts_block += f"   Action type: {action} | Affects: {holdings_str}\n\n"

    # Industry results block
    top_industries = industry_results.get("top_industries", [])
    layer2 = industry_results.get("layer2", [])
    high_conviction = industry_results.get("high_conviction", [])

    industries_block = f"Total industries scanned: 25\n"
    industries_block += f"Layer 1 (outperforming SPY): {len(industry_results.get('layer1', []))}\n"
    industries_block += f"Layer 2 (deep analysis): {len(layer2)}\n"
    industries_block += f"High conviction (70+): {len(high_conviction)}\n\n"

    for ind in top_industries[:MAX_INDUSTRIES_BRIEFING]:
        industries_block += f"""
INDUSTRY: {ind['industry']}
ETF: {ind['etf']} | Current Price: ${ind['current_price']}
Conviction Score: {ind['conviction_score']}/100
63-day return: {ind['etf_63d_return']}% vs SPY {ind['spy_63d_return']}% (outperformance: {ind['excess_63d']:+.1f}pp)
21-day return: {ind['etf_21d_return']}% (recent trend)
Macro alignment: {ind.get('macro_alignment', 'Neutral')}
Relevant news count: {ind.get('news_count', 0)}
Ripple benefits: {', '.join(ind.get('ripple_benefits', [])) or 'None detected'}
Ripple harms: {', '.join(ind.get('ripple_harms', [])) or 'None detected'}
Relevant headlines:"""
        for news_item in ind.get("relevant_news", [])[:2]:
            industries_block += f"\n  - {news_item['headline']}"
        industries_block += "\n"

    # Remaining layer 2 industries summary
    remaining = [i for i in layer2 if i not in top_industries]
    if remaining:
        industries_block += "\nOther qualifying industries (not top 4):\n"
        for ind in remaining[:6]:
            industries_block += f"- {ind['industry']} ({ind['etf']}): conviction {ind['conviction_score']}/100, excess return {ind['excess_63d']:+.1f}pp\n"

    # Open positions block
    positions_block = f"Open positions: {len(positions)}\n"
    for p in positions:
        entry = p.get("entry_price", 0)
        current = p.get("current_price", 0)
        pnl = ((current - entry) / entry * 100) if entry > 0 else 0
        stop = p.get("stop_price", 0)
        dist_stop = ((current - stop) / current * 100) if current > 0 and stop > 0 else 0
        positions_block += f"""
TICKER: {p['ticker']}
Entry: ${entry:.2f} | Current: ${current:.2f} | P&L: {pnl:+.1f}%
Stop: ${stop:.2f} ({dist_stop:.1f}% away)
Holding type: {p.get('holding_type', 'Not specified')}
Thesis: {p.get('thesis', 'Not recorded')}
"""

    earnings_block = chr(10).join(
        f"  {t}: {i.get('date','')} {'(after close)' if i.get('hour')=='amc' else '(before open)' if i.get('hour')=='bmo' else ''}"
        for t,i in (earnings_calendar or {}).items()
    ) or "No confirmed earnings dates in next 90 days."

    return f"""DATE: {today}

=== CONFIRMED EARNINGS DATES (Finnhub verified — use these, not estimates) ===
{earnings_block}


=== INVESTOR ONE-PAGER (Your North Star) ===
{one_pager}

=== RECENT MEMORY LOG (Last 7 days) ===
{memory if memory else "No recent entries."}

=== MACRO CONDITIONS ===
{macro_block}

=== TODAY'S NEWS ({len(news)} headlines) ===
{news_block if news_block else "No news available."}

=== INDUSTRY INTELLIGENCE SCAN RESULTS ===
{industries_block}

=== OPEN POSITIONS ===
{positions_block if positions else "No open positions."}
"""


def build_morning_output_instructions() -> str:
    return """
=== OUTPUT INSTRUCTIONS ===

You are generating the morning investment briefing. Read the Investor One-Pager carefully.
Every recommendation must align with the philosophy, rules, and constraints it contains.

Think like an institutional research desk. Prioritize industries before individual stocks.
Think in second and third-order effects. Combine quantitative data with event intelligence.

OUTPUT FORMAT — follow exactly:

## Market Overview
One paragraph. What is the current market environment?
Reference VIX regime, macro conditions, and any major overnight developments.
Be specific — no generic commentary.

## Major Macro Developments
Only include developments that directly affect investable industries.
List 2-4 bullet points maximum. If nothing material: state that clearly.

## Industry Opportunities
For each of the top 2-4 high-conviction industries, write exactly this format:

### [INDUSTRY NAME] — Conviction: [SCORE]/100

**Why Now**
2-3 sentences. Why does this industry deserve attention today?
Reference specific data from the scan results above.

**What Changed**
1-2 sentences. What event or data point is driving this opportunity?
Must come directly from the news or scan data provided.

**Quantitative Support**
- ETF: [ticker] | 63-day return: [X]% | Outperformance vs SPY: [X]pp
- [One additional relevant data point]

**Investment Vehicle**
Recommend ETF or individual stocks. Explain why one is better than the other right now.
If recommending stocks, name 2-3 specific tickers from within the industry.
Keep this to 2-3 sentences maximum.

**Key Risks**
2 bullet points. What could invalidate this opportunity?

---

## Catalysts Ahead
List 3-5 of the most important upcoming catalysts from the data above.
For each: date, event, and one sentence on whether this is an entry opportunity,
a position management decision, or both. Prioritize catalysts affecting current
holdings or high-conviction industries. If a catalyst is an entry opportunity,
say so explicitly — e.g. "Consider entering before this date to capture the move."
If a catalyst requires managing an existing position, say so explicitly —
e.g. "TICKER earnings on [date] — based on [analyst expectations / guidance / sector momentum], the setup looks [strong/weak/mixed]. Recommend [hold through / trim before / exit before] because [specific reason]."
Never apply a blanket exit rule before earnings. Analyze the actual setup: guidance, estimate revisions, sector tailwinds, and how much gain is at risk. Only recommend exiting if the risk/reward is unfavorable given the specific data. If the setup is strong, say so and recommend holding.

## Market Overview
Write 3-5 bullet points explaining what the VIX level, trend, and macro regime actually mean for the portfolio today. Do not just restate the numbers — explain what they mean. Example: if VIX is 18 and falling, explain why that is good for risk assets and what it signals about market confidence. Explain the regime (Bullish/Bearish/Neutral) in plain English and why it matters for today specifically. Each bullet must start with a dash (-).

## Open Position Review
For EVERY position write exactly this format:

TICKER — HOLD / WATCH / TRIM / EXIT / CLOSE
- Bullet 1: Current P&L context and what drove it today (cite specific news or data)
- Bullet 2: Thesis status — is it intact, strengthening, or breaking? Why?
- Bullet 3: Specific action and exact reasoning (not generic — cite the actual catalyst, stop level, or event)
- Bullet 4 (optional): What to watch for next / upcoming catalyst or risk event

Rules:
- Use WATCH if the position needs monitoring due to approaching stop, upcoming earnings, or negative news
- Use CLOSE or EXIT if a hard stop has been breached or thesis has broken
- Use TRIM if position is oversized or risk/reward has shifted
- Use HOLD only if thesis is fully intact and no action is needed
- NEVER say "hold and monitor" — that is WATCH not HOLD
- PLTR hard stop is  — if price is below , action must be CLOSE
- MU earnings have already occurred — do not say "exit before earnings"
- Always use the CONFIRMED EARNINGS DATES provided above, never estimate
For each held position:
TICKER — HOLD / WATCH / REDUCE / EXIT
One sentence explaining the recommendation based on current data.
If no positions: state "No open positions."

## Risk Assessment & Cash Guidance
One paragraph. Should capital be deployed today or is caution warranted?
If no high-conviction opportunities exist, explicitly recommend holding cash.
Reference specific reasons from the data above.

IMPORTANT RULES:
- Never recommend options, short selling, or margin
- Never exceed 15% in a single position
- Never recommend a position simply because it is moving up
- If conviction score is below 45 for all industries, recommend holding cash
- Always explain WHY, not just WHAT
"""


def generate_morning_briefing(
    macro: dict,
    industry_results: dict,
    news: list,
    forward_catalysts: list,
    positions: list,
    today: str,
    earnings_calendar: dict = None,
) -> dict:
    """
    Generate the complete morning briefing using Claude.
    Returns dict with raw_text, sections, and token usage.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    context = build_morning_context(macro, industry_results, news, forward_catalysts, positions, today, earnings_calendar=earnings_calendar or {})
    instructions = build_morning_output_instructions()
    full_prompt = context + instructions

    log("Calling Claude for morning briefing...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system="""You are a no-fluff, data-driven investment strategist generating a daily
morning briefing. You think like an institutional research desk.
You prioritize industries before stocks. You think in second and third-order effects.
You never recommend investments without data support.
You always read and respect the Investor One-Pager rules.""",
        messages=[{"role": "user", "content": full_prompt}]
    )

    raw_text = message.content[0].text
    sections = _parse_sections(raw_text)

    log(f"Morning briefing generated — {message.usage.input_tokens} in | {message.usage.output_tokens} out tokens")
    log(f"Sections parsed: {list(sections.keys())}")

    return {
        "raw_text": raw_text,
        "sections": sections,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
        "model": message.model,
    }


def build_telegram_morning_summary(briefing: dict, industry_results: dict, macro: dict, positions: list) -> str:
    """
    Build concise Telegram morning summary.
    Readable in under 60 seconds on a phone.
    """
    vix = macro.get("vix", 0)
    vix_regime = macro.get("vix_regime", "Yellow")
    regime_emoji = "🟢" if vix_regime == "Green" else "🔴" if vix_regime == "Red" else "🟡"

    top = industry_results.get("top_industries", [])
    high = industry_results.get("high_conviction", [])

    lines = []
    lines.append(f"<b>📊 Morning Briefing</b>")
    lines.append(f"{regime_emoji} VIX {vix} ({vix_regime}) | {len(high)} high-conviction industries")
    lines.append("")

    if top:
        lines.append("<b>🏭 Top Industries</b>")
        for ind in top[:4]:
            score = ind.get("conviction_score", 0)
            name = ind["industry"]
            etf = ind["etf"]
            excess = ind.get("excess_63d", 0)
            emoji = "🔥" if score >= 70 else "👀"
            lines.append(f"{emoji} {name} ({etf}) +{excess:.1f}pp | {score}/100")
        lines.append("")

    # Position alerts
    alerts = []
    for p in positions:
        entry = p.get("entry_price", 0)
        current = p.get("current_price", 0)
        stop = p.get("stop_price", 0)
        pnl = ((current - entry) / entry * 100) if entry > 0 else 0
        dist_stop = ((current - stop) / current * 100) if current > 0 and stop > 0 else 0

        if dist_stop < 3 and stop > 0:
            alerts.append(f"⚠️ {p['ticker']} approaching stop ({dist_stop:.1f}% away)")
        elif pnl < -10:
            alerts.append(f"🔴 {p['ticker']} down {pnl:.1f}% — review required")

    if alerts:
        lines.append("<b>⚠️ Position Alerts</b>")
        for alert in alerts:
            lines.append(alert)
    else:
        lines.append("✅ All positions stable")

    lines.append("")
    lines.append("Open Notion for full briefing →")

    return "\n".join(lines)


def _parse_sections(raw_text: str) -> dict:
    sections = {}
    current_section = None
    current_lines = []

    for line in raw_text.split("\n"):
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections
