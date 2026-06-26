import os
import anthropic
from v4.utils.logger import log
from v4.utils.file_reader import read_one_pager, read_memory_log


def generate_afternoon_update(
    positions: list,
    industry_results: dict,
    news: list,
    morning_top_industries: list,
    today: str,
) -> dict:
    """
    Generate afternoon portfolio intelligence update.
    Focuses on position monitoring and new opportunities.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    one_pager = read_one_pager()
    memory = read_memory_log(last_n_days=3)

    # Build positions context
    positions_block = ""
    for p in positions:
        entry = p.get("entry_price", 0) or p.get("entry", 0)
        current = p.get("current_price", 0)
        stop = p.get("stop_price", 0)
        target = p.get("target_price", 0)
        pnl = ((current - entry) / entry * 100) if entry > 0 else 0
        dist_stop = ((current - stop) / current * 100) if current > 0 and stop > 0 else 0
        dist_target = ((target - current) / current * 100) if current > 0 and target > 0 else 0

        ticker_news = p.get("ticker_news", [])
        news_lines = "\n".join([f"  - {n['headline']}" for n in ticker_news[:3]]) or "  No ticker-specific news today"

        positions_block += f"""
TICKER: {p['ticker']} | Holding Type: {p.get('holding_type', 'Not specified')}
Entry: ${entry:.2f} | Current: ${current:.2f} | P&L: {pnl:+.1f}%
Stop: ${stop:.2f} ({dist_stop:.1f}% away) | Target: ${target:.2f} ({dist_target:.1f}% to target)
Original thesis: {p.get('thesis', 'Not recorded')}
Today's news for this ticker:
{news_lines}
"""

    # New opportunities vs morning
    afternoon_top = industry_results.get("top_industries", [])
    morning_names = {i.get("industry") for i in morning_top_industries}
    new_opportunities = [i for i in afternoon_top if i["industry"] not in morning_names]

    new_opps_block = ""
    for ind in new_opportunities[:3]:
        new_opps_block += f"- {ind['industry']} ({ind['etf']}): conviction {ind['conviction_score']}/100, +{ind['excess_63d']:.1f}pp vs SPY\n"

    news_block = "\n".join([
        f"- [{item.get('datetime', '')[:16]}] {item['headline']}"
        for item in news[:20]
    ])

    prompt = f"""DATE: {today} — Afternoon Portfolio Update (2:45 PM ET)

=== INVESTOR ONE-PAGER ===
{one_pager}

=== RECENT MEMORY ===
{memory if memory else "No recent entries."}

=== OPEN POSITIONS ===
{positions_block if positions_block else "No open positions."}

=== NEW OPPORTUNITIES (not in morning briefing) ===
{new_opps_block if new_opps_block else "No new opportunities emerged since morning."}

=== AFTERNOON NEWS ===
{news_block if news_block else "No significant news."}

=== OUTPUT INSTRUCTIONS ===

Generate a detailed afternoon portfolio update with the following sections. Be specific — every bullet must reference real news, data, or price action from today. Never use generic filler.

## What Changed Since Morning
3-5 bullet points covering the most important things that shifted since the morning briefing. Include: notable macro moves, sector developments, news that broke during the session, any price action that matters. If truly nothing changed, say so in one sentence.

## Notable Price Moves
REQUIRED — always include this section. List 3-5 notable price moves from today. These do NOT have to be your holdings — include broad market ETFs (SPY, QQQ, IWM), sector ETFs, or any individual stock with a significant move today. For each: ticker, approximate move percentage, and one sentence on why it matters to this portfolio. There are always notable movers every session — find them.

## Portfolio Actions Before Close
For EVERY open position, write:
TICKER — HOLD / WATCH / REDUCE / EXIT
Entry:  | Current:  | P&L: X%
Then 2-3 bullet points explaining:
- What happened today specifically that affects this position (cite actual news or price action — not just the P&L number)
- Whether the thesis is intact, strengthening, or breaking
- Exact action: hold into tomorrow, reduce X% before close, exit fully, or buy more
Do NOT skip any position. Do NOT use generic phrases like "position stable" or "no material changes" unless you can confirm nothing whatsoever occurred in this sector today.

## New or Strengthened Candidates
For each high-conviction industry (whether new or same as morning but with updated reasoning):
INDUSTRY — conviction X/100 — NEW or STRENGTHENED
Then 3-4 bullet points explaining:
- What specific catalyst, news, or data point TODAY makes this compelling
- Why the conviction score is what it is (cite the actual factors: momentum data, news catalysts, macro alignment, event scores)
- ETF or specific stock ticker — and the exact reasoning why that vehicle over the alternative
- Why act now vs waiting
If nothing changed from morning and conviction is unchanged, say so clearly and re-explain the original thesis with the specific stock/ETF recommendation.

## Market Close Watch
The single most important thing to monitor or act on before market close today.
"""

    log("Calling Claude for afternoon update...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system="You are a portfolio intelligence system generating an afternoon update. Be direct and specific. Every sentence must reference real data, news, or price action. Always use ## headers exactly as specified in the instructions.",
        messages=[{"role": "user", "content": prompt}]
    )

    raw_text = message.content[0].text
    sections = _parse_sections(raw_text)
    log(f"Afternoon sections found: {list(sections.keys())}")

    log(f"Afternoon update generated — {message.usage.output_tokens} output tokens")

    return {
        "raw_text": raw_text,
        "sections": sections,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }


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
