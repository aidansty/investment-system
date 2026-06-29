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
    rules_output: dict = None,
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

    # ── Rules Engine Signals ──────────────────────────────────────────────────
    re_out = rules_output or {}
    regime_score = re_out.get("regime_score", 0)
    regime = re_out.get("regime", "Yellow")
    entry_signals = re_out.get("entry_signals", [])
    exit_signals = re_out.get("exit_signals", [])
    kill_criteria = re_out.get("kill_criteria", {})

    rules_block = "\n=== RULES ENGINE OUTPUT ===\n"
    rules_block += f"REGIME: {regime} ({regime_score}/100)\n"
    if kill_criteria.get("triggered"):
        rules_block += "KILL CRITERIA TRIGGERED — defensive mode active\n"
    rules_block += f"\nENTRY SIGNALS ({len(entry_signals)} found):\n"
    if entry_signals:
        for sig in entry_signals:
            rules_block += f"  ENTER {sig.get('ticker','')} conviction={sig.get('conviction',0)}/100 size={sig.get('size_pct',0):.0%}\n"
            rules_block += f"  {sig.get('reason','')[:150]}\n"
    else:
        rules_block += "  No qualifying entries today (conviction >= 75 + catalyst required)\n"
    rules_block += f"\nPOSITION SIGNALS ({len(exit_signals)} evaluated):\n"
    for sig in exit_signals:
        action = sig.get("action", "hold").upper()
        if action != "HOLD":
            rules_block += f"  {action} {sig.get('ticker','')} — {sig.get('reason','')[:120]}\n"
            tax = sig.get("tax_awareness", {})
            if tax.get("urgency") in ("high", "medium"):
                rules_block += f"  TAX: {tax.get('tax_recommendation','')}\n"
    rules_block += "=== END RULES ENGINE OUTPUT ===\n"

    context += rules_block

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

## Rules Engine Signals
The rules engine has already evaluated all entry and exit decisions quantitatively.
Your job is to explain the reasoning behind each signal in plain English.

For each ENTRY signal the rules engine generated:
ENTRY: [TICKER] — [CONVICTION]/100 — [POSITION SIZE]% of active sleeve
- Why this ticker: what specific momentum, fundamental, or catalyst data supports it
- Why now specifically: what changed recently that makes this the right entry point
- What to watch: the specific data point or event that would invalidate this entry
- Tax note: new position will be short-term gain until held 12+ months

For each EXIT or WATCH signal:
EXIT/WATCH: [TICKER]
- What specifically broke or is weakening in the thesis
- The measurable data supporting this decision
- What would reverse this signal

If no entry signals: state clearly "Rules engine found no qualifying entry opportunities today. Hold cash and wait for conviction score above 75 with confirmed catalyst."

## Industry Analysis (Layer 1 — Context Only)
This section provides context for the rules engine signals above.
For each top 2-3 qualifying industry (conviction 75+):

### [INDUSTRY NAME] — Conviction: [SCORE]/100
- What is driving momentum in this industry right now
- Which individual stocks within this industry are leading vs lagging
- Specific catalyst or data point that could strengthen or break this thesis
- Key risk: one specific thing that could end this industry's outperformance

## Catalysts Ahead
List 3-5 of the most important upcoming catalysts from the data above.
For each: date, event, and one sentence on whether this is an entry opportunity,
a position management decision, or both. Prioritize catalysts affecting current
holdings or high-conviction industries. If a catalyst is an entry opportunity,
say so explicitly — e.g. "Consider entering before this date to capture the move."
If a catalyst requires managing an existing position, say so explicitly —
e.g. "TICKER earnings on [date] — based on [analyst expectations / guidance / sector momentum], the setup looks [strong/weak/mixed]. Recommend [hold through / trim before / exit before] because [specific reason]."
Never apply a blanket exit rule before earnings. Analyze the actual setup: guidance, estimate revisions, sector tailwinds, and how much gain is at risk. Only recommend exiting if the risk/reward is unfavorable given the specific data. If the setup is strong, say so and recommend holding.

## Market Snapshot Explanation
Write 3-5 bullet points explaining what the VIX level, trend, and macro regime actually mean for the portfolio today. Do not just restate the numbers — explain what they mean in plain English. Example: if VIX is 18 and falling, explain why that is good for risk assets and what it signals about market confidence. Explain the regime (Bullish/Bearish/Neutral) and why it matters for today specifically. Each bullet must start with a dash (-).

## Open Position Review
You are the explanation layer. The rules engine decides. You explain WHY using real data, news, and events.

For EVERY position write exactly:

TICKER — HOLD / WATCH / TRIM / EXIT / CLOSE
- Bullet 1: What specific data, news, or event is most relevant TODAY (cite actual numbers)
- Bullet 2: Thesis status in measurable terms — revenue growth %, earnings revision direction, relative strength
- Bullet 3: Exact reasoning for the recommended action — cite the specific factor
- Bullet 4: What to monitor next — specific data point, date, or event

THESIS BREAK — flag as EXIT immediately if ANY confirmed:
- Revenue growth reversal two consecutive negative quarters
- Earnings estimates cut more than 10% from consensus
- FCF turned negative when previously positive
- Regulatory rejection directly affecting core business
- Major contract loss with material revenue impact
- Management guidance cut significantly below expectations

RULES:
- NEVER use percentage loss alone to recommend action
- NEVER say "hold and monitor" — say WATCH and name exactly what to monitor
- EXIT only when thesis has fundamentally broken in measurable terms — 10 consecutive days below conviction 40
- Short-term dips in conviction (1-9 days below 40) are WATCH not EXIT — the thesis may recover
- Use CONFIRMED EARNINGS DATES above — never estimate
- Conviction-based sizing: 88+=25% of active sleeve, 80+=20%, 75+=15%
- Maximum 4 active positions at any time — if recommending a new entry, identify which current position it displaces if at max

## Capital Deployment Guidance
One paragraph covering two things:
1. Active sleeve (non-SPY, non-crypto stock holdings): should new capital be deployed today or held in cash? Reference the rules engine signals and regime score.
2. SPY anchor: no action needed unless trimming is warranted by a specific overweight condition.

IMPORTANT RULES:
- Never recommend options, short selling, or margin
- Maximum 4 active positions — if at max, a new entry requires identifying which position to exit first
- Never recommend a position below conviction 75 — wait for the right setup
- If no industry scores above 75 conviction, cash is the correct allocation — state this clearly
- Conviction-based sizing only: 88+=25%, 80+=20%, 75+=15% of active sleeve
- Always explain WHY with specific data, not generic market commentary
- SPY is a permanent anchor — never recommend closing it
"""


def generate_morning_briefing(
    macro: dict,
    industry_results: dict,
    news: list,
    forward_catalysts: list,
    positions: list,
    today: str,
    earnings_calendar: dict = None,
    rules_output: dict = None,
) -> dict:
    """
    Generate the complete morning briefing using Claude.
    Claude is the EXPLANATION layer — rules engine decisions are passed in.
    Returns dict with raw_text, sections, and token usage.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    context = build_morning_context(macro, industry_results, news, forward_catalysts, positions, today, earnings_calendar=earnings_calendar or {}, rules_output=rules_output or {})
    instructions = build_morning_output_instructions()
    full_prompt = context + instructions

    log("Calling Claude for morning briefing...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
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
