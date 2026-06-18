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
        entry = p.get("entry_price", 0)
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

Generate a concise afternoon portfolio update.

## Portfolio Review
For each position write:
TICKER — HOLD / WATCH / REDUCE / EXIT
One sentence: what happened today and why this recommendation.
Base on: news, price vs stop/target, thesis integrity.

## New Opportunities
If new high-conviction industries emerged since morning:
List them with one sentence explanation of what changed.
If nothing new: write "No new opportunities since morning briefing."

## Market Close Watch
One sentence: the single most important thing to monitor before close.
If nothing urgent: write "No urgent action required before close."
"""

    log("Calling Claude for afternoon update...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system="You are a portfolio intelligence system generating an afternoon update. Be direct and specific. Every sentence must lead to a clear action.",
        messages=[{"role": "user", "content": prompt}]
    )

    raw_text = message.content[0].text
    sections = _parse_sections(raw_text)

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
