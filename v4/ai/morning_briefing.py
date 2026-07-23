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
    recent_earnings_results: dict = None,
    catalyst_opportunities: list = None,
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

    # ── Recent Earnings Results (ACTUAL reported numbers, not estimates) ────────
    rer = recent_earnings_results or {}
    earnings_results_block = ""
    if rer:
        earnings_results_block = "\n=== RECENT EARNINGS RESULTS (last 14 days, ACTUAL reported) ===\n"
        earnings_results_block += "Use these ACTUAL results. NEVER tell the user to go check earnings themselves.\n"
        for ticker, r in rer.items():
            report_date = r.get("report_date", "")
            verdict = r.get("verdict", "")
            eps_actual = r.get("eps_actual")
            eps_estimate = r.get("eps_estimate")
            eps_surprise = r.get("eps_surprise_pct")
            rev_surprise = r.get("revenue_surprise_pct")
            earnings_results_block += "\n" + ticker + " reported " + str(report_date) + ": " + str(verdict) + "\n"
            earnings_results_block += "  EPS: actual " + str(eps_actual) + " vs estimate " + str(eps_estimate) + " (" + str(eps_surprise) + "% surprise)\n"
            if rev_surprise is not None:
                earnings_results_block += "  Revenue surprise: " + str(rev_surprise) + "%\n"
        earnings_results_block += "=== END RECENT EARNINGS RESULTS ===\n"

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

    # Industry detail loop removed — catalyst scanner handles this

    # Remaining layer 2 industries summary
    remaining = [i for i in layer2 if i not in top_industries]
    if remaining:
        industries_block += "\nOther qualifying industries (not top 4):\n"
        for ind in remaining[:6]:
            industries_block += f"- {ind['industry']} ({ind['etf']}): conviction {ind['conviction_score']}/100, excess return {ind['excess_63d']:+.1f}pp\n"

    # Build per-ticker recent news context so Claude references specific headlines per position
    news_list = news if isinstance(news, list) else []
    ticker_news_map = {}
    for n_item in news_list:
        affected = n_item.get("affected_tickers", [])
        if isinstance(affected, list):
            for t in affected:
                if t not in ticker_news_map:
                    ticker_news_map[t] = []
                if len(ticker_news_map[t]) < 3:
                    ticker_news_map[t].append(n_item.get("headline", ""))
        headline_upper = n_item.get("headline", "").upper()
        for p in positions:
            ptk = p.get("ticker", "")
            if ptk and len(ptk) >= 2 and ptk in headline_upper:
                if ptk not in ticker_news_map:
                    ticker_news_map[ptk] = []
                if len(ticker_news_map[ptk]) < 3:
                    ticker_news_map[ptk].append(n_item.get("headline", ""))

    # Open positions block — now includes per-ticker news context
    # Only send STOCK positions to Claude — skip crypto and SPY to save tokens
    CRYPTO_SKIP_BRIEF = {"BTC", "ETH", "XRP", "ZEC", "SOL"}
    stock_positions = [p for p in positions if p.get("ticker", "") not in CRYPTO_SKIP_BRIEF and p.get("ticker", "") != "SPY"]
    positions_block = f"Stock positions to review ({len(stock_positions)} — crypto and SPY excluded):\n"
    for p in stock_positions:
        entry = p.get("entry_price", 0)
        current = p.get("current_price", 0)
        pnl = ((current - entry) / entry * 100) if entry > 0 else 0
        stop = p.get("stop_price", 0)
        dist_stop = ((current - stop) / current * 100) if current > 0 and stop > 0 else 0
        tk = p["ticker"]
        tk_news = ticker_news_map.get(tk, [])
        news_context = ""
        if tk_news:
            news_context = "Recent news for this ticker:\n" + "\n".join(f"  - {h}" for h in tk_news[:3])
        else:
            news_context = "No specific news found for this ticker today."
        positions_block += f"""
TICKER: {tk}
Entry: ${entry:.2f} | Current: ${current:.2f} | P&L: {pnl:+.1f}%
Stop: ${stop:.2f} ({dist_stop:.1f}% away)
Holding type: {p.get('holding_type', 'Not specified')}
Thesis: {p.get('thesis', 'Not recorded')}
{news_context}
"""

    earnings_block = chr(10).join(
        f"  {t}: {i.get('date','')} {'(after close)' if i.get('hour')=='amc' else '(before open)' if i.get('hour')=='bmo' else ''}"
        for t,i in (earnings_calendar or {}).items()
    ) or "No confirmed earnings dates in next 90 days."


    cat_opps = catalyst_opportunities or []
    if cat_opps:
        catalyst_block = ""
        for c in cat_opps:
            catalyst_block += "\n" + c["ticker"] + " (" + c.get("industry","Unknown") + ")\n"
            catalyst_block += "  Earnings date: " + c["earnings_date"] + " (" + str(c["days_until"]) + " days away)\n"
            catalyst_block += "  21-day momentum vs SPY: +" + str(c["excess_21d"]) + "pp\n"
            catalyst_block += "  Current price: $" + str(c["price"]) + "\n"
            if c.get("eps_estimate"):
                catalyst_block += "  EPS estimate: " + str(c["eps_estimate"]) + "\n"
            if c.get("news_headlines"):
                catalyst_block += "  Recent news: " + c["news_headlines"][0][:100] + "\n"
    else:
        catalyst_block = "No stocks currently have both strong 21-day momentum and upcoming earnings within 30 days."

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

{rules_block}
{earnings_results_block}

=== CATALYST SCANNER (highest-priority new opportunities) ===
These stocks have BOTH strong 21-day momentum AND confirmed earnings dates within 30 days.
For each one, explain why the momentum + upcoming earnings makes this a high-probability setup.
{catalyst_block}
=== END CATALYST SCANNER ===
"""


def build_morning_output_instructions() -> str:
    return """
=== OUTPUT INSTRUCTIONS ===

You are a human investment analyst writing your daily morning briefing. You think like a person — you read the news, immediately think about how it affects your client's portfolio, and produce ONE CONNECTED analysis where every section builds on the previous one.

YOUR THOUGHT PROCESS (follow this exactly):
1. Read ALL the news and data above
2. Identify which pieces of news ACTUALLY MATTER — filter out noise (minor analyst notes, generic commentary, routine updates). Only surface information that has a realistic chance of moving a stock price 5%+.
3. For each piece of real news, think: "Does this affect any of my client's holdings? How? Is this positive or negative? What should they do?"
4. Write the briefing so the information FLOWS from section to section

OUTPUT FORMAT — follow exactly:

## Market Snapshot Explanation
Write EXACTLY 4-5 bullet points starting with a dash (-):
- Bullet 1: What the VIX level means right now
- Bullet 2: What the VIX trend signals about changing sentiment
- Bullet 3: What the regime label means for whether new positions should be entered today
- Bullet 4: Connect today's macro conditions to THIS portfolio specifically
- Bullet 5 (optional): Any economic event today and what it could change

## Actionable Intelligence
ONLY include news that passes this test: "Could this realistically move a stock price 5%+ or directly affect one of my client's holdings?"

For each qualifying piece of news:
**[Headline]**
- What happened (1 sentence — the facts)
- Which of your holdings this affects and HOW — explain the CAUSAL LINK. If it affects multiple holdings, explain each one separately. Example: "This affects MU because increased AI spending drives memory chip demand. This affects AMD because they compete for the same data center GPU contracts."
- What to do about it — specific action recommendation tied to THIS news

Do NOT include: earnings calendar dates (those go in Coming Up), minor analyst notes, generic market recaps, or anything that is just noise.

## Coming Up — Events Affecting You
List dated events in the next 14 days that affect your client's holdings or could create opportunities:
- [DATE] EVENT — Why this matters to YOUR portfolio (1 sentence)

Include: your holdings' earnings dates, major economic releases, FDA decisions, competitor earnings that affect your holdings. Do NOT repeat news from Actionable Intelligence.

## Position Review
THIS IS THE MOST IMPORTANT SECTION. It is a SYNTHESIS of everything above.

For EVERY stock position (no crypto, no SPY), write:

TICKER — HOLD / WATCH / EXIT / TRIM
- Entry: $X | Current: $Y | P&L: +/-Z%
- **Today's news impact:** Reference SPECIFIC news from the Actionable Intelligence section above that affects this ticker. If news item #2 mentioned a Morgan Stanley downgrade of RPD, say "Morgan Stanley downgraded RPD today (see above) — this weakens our earnings run-up thesis because..." If NO news today affects this ticker, say "No material news today for this ticker."
- **Catalyst status:** Is the original catalyst still intact? How many days until the catalyst date? Has anything changed about it? Is the thesis getting stronger or weaker?
- **What to do and WHY:** Give the specific action and explain the reasoning. "Hold because the Q2 earnings catalyst on August 4th is still 13 days away, momentum remains positive at +11pp vs SPY, and today's AI rebound news supports the thesis." Or "Exit because the Morgan Stanley downgrade fundamentally changes the risk profile — the catalyst thesis that justified entry is now in question."

CRITICAL DATE RULE: Today is {today}. Do NOT reference events older than 7 days as current. Every position review must be DIFFERENT from yesterday's — reference today's specific news, prices, and upcoming dates.

SIGNIFICANCE FILTER: Only change an action (from Hold to Exit/Watch/Trim) if the event is significant enough to move the stock 5%+. Minor events get one sentence of context: "Note: [minor event]. Not significant enough to change the current action."

## Capital Deployment Guidance
One paragraph: should new capital be deployed today or held in cash? Reference the regime score and whether any catalyst scanner candidates scored above 70 conviction.

RULES:
- Never use percentage loss alone to recommend action
- Never say "hold and monitor" — say WATCH and name exactly what to monitor
- Use CONFIRMED EARNINGS DATES from the data — never estimate
- Never recommend options, short selling, or margin
- SPY is a permanent anchor — never recommend closing it
- If you reference news in the position review, it MUST exist in the Actionable Intelligence section — do not invent news
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
    recent_earnings_results: dict = None,
    catalyst_opportunities: list = None,
) -> dict:
    """
    Generate the complete morning briefing using Claude.
    Claude is the EXPLANATION layer — rules engine decisions are passed in.
    Returns dict with raw_text, sections, and token usage.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    context = build_morning_context(macro, industry_results, news, forward_catalysts, positions, today, earnings_calendar=earnings_calendar or {}, rules_output=rules_output or {}, recent_earnings_results=recent_earnings_results or {}, catalyst_opportunities=catalyst_opportunities or [])
    instructions = build_morning_output_instructions()
    full_prompt = context + instructions

    log("Calling Claude for morning briefing...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        system="""You are a human investment analyst writing a daily morning briefing for your client. You think like a person — when you read news, you immediately connect it to your client's portfolio. Your analysis flows naturally: news leads to impact assessment leads to action recommendation.

You are direct, specific, and never generic. Every sentence references real data, real news from today, or real upcoming dates. You never write filler or boilerplate. If there is nothing new to say about a position, you say exactly that in one sentence rather than repeating yesterday's analysis.

Your client trusts you because your position reviews reference the SPECIFIC news you flagged in Actionable Intelligence. The sections are connected — one thought process, structured into sections.""",
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
        lines.append("<b>🏭 Catalyst Scanner Opportunities</b>")
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
