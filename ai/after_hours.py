import os
import anthropic
from utils.logger import log


AFTER_HOURS_SYSTEM_PROMPT = """
You are a risk monitoring assistant reviewing after-hours conditions for a retail
investor with active stock positions and potential new trade opportunities.

CORE RULES:
1. Only reference data provided in the context. Never invent news or prices.
2. If information is unavailable, state that clearly.
3. Be direct and specific. Every sentence must lead to a clear action.
4. Do not predict future price movements as certainties.
5. This alert will be read on a phone — keep it short and scannable.
6. Lead with the most urgent item first.
7. If nothing material is happening, say so in one sentence and stop.
"""


def build_after_hours_prompt(positions, candidate_changes, afternoon_scan, today):
    """Assemble focused context for after-hours risk and opportunity review."""

    # Format positions with ticker-specific news
    positions_block = ""
    for p in positions:
        entry = p.get("entry_price") or 0
        current = p.get("current_price") or 0
        stop = p.get("stop_price") or 0
        target = p.get("target_price") or 0
        pnl = ((current - entry) / entry * 100) if entry > 0 else 0
        dist_stop = ((current - stop) / current * 100) if current > 0 and stop > 0 else 0
        dist_target = ((target - current) / current * 100) if current > 0 and target > 0 else 0

        news_lines = ""
        for item in p.get("ticker_news", [])[:3]:
            news_lines += "  - " + item["headline"] + "\n"
        if not news_lines:
            news_lines = "  - No ticker-specific news today\n"

        positions_block += (
            f"TICKER: {p['ticker']}\n"
            f"P&L: {pnl:+.1f}% | Stop: {dist_stop:+.1f}% away | Target: {dist_target:+.1f}% away\n"
            f"Thesis: {p.get('thesis', 'Not recorded')}\n"
            f"Today's news:\n{news_lines}\n"
        )

    # Format candidate changes
    changes_block = ""
    if candidate_changes.get("no_morning_data"):
        changes_block = "No morning snapshot available for comparison.\n"
    else:
        new_strong = candidate_changes.get("new_strong", [])
        dropped = candidate_changes.get("dropped_strong", [])
        increases = candidate_changes.get("score_increases", [])
        new_cats = candidate_changes.get("new_catalysts", [])

        if new_strong:
            changes_block += "NEW STRONG CANDIDATES (not in morning scan):\n"
            for c in new_strong:
                cat = f"catalyst in {c['days_to_catalyst']}d" if c.get("has_catalyst") else "no catalyst"
                changes_block += f"  {c['ticker']}: score {c['composite_score']} | RS {c['rs_score']:+.1f}pp | {cat}\n"

        if dropped:
            changes_block += "DROPPED FROM STRONG (were strong this morning):\n"
            for c in dropped:
                changes_block += f"  {c['ticker']}: score {c['composite_score']} | {c.get('missing_signal', 'unknown')}\n"

        if increases:
            changes_block += "SCORE INCREASES (improved 0.10+ since morning):\n"
            for c in increases:
                changes_block += f"  {c['ticker']}: {c['score_delta']:+.3f} change | new score {c['composite_score']}\n"

        if new_cats:
            changes_block += "NEW CATALYSTS CONFIRMED TODAY:\n"
            for c in new_cats:
                changes_block += f"  {c['ticker']}: earnings in {c.get('days_to_catalyst', '?')} days ({c.get('catalyst_date', '?')})\n"

        if not changes_block:
            changes_block = "No material changes from morning scan.\n"

    return f"""
DATE: {today} — After-Hours Review (3:30 PM ET)

OPEN POSITIONS ({len(positions)} held):
{positions_block if positions_block else "No open positions."}

CANDIDATE CHANGES SINCE THIS MORNING:
{changes_block}

---
REQUIRED OUTPUT FORMAT:

## Position Review
For each held position write:
TICKER — HOLD / WATCH / REDUCE / EXIT
One sentence: what happened today and why this recommendation.
Skip positions with no material news and no stop/target alerts.
If all positions are fine: "All positions stable — no action required."

## New Opportunities
For each new or improved candidate worth acting on:
TICKER — BUY BEFORE CLOSE / WATCH FOR OPEN
One sentence: what changed and why it matters.
If nothing actionable: "No new opportunities identified."

## Key Risk Before Open
One sentence: the single most important thing to know before tomorrow's open.
If nothing material: "No material after-hours developments detected."
"""


def generate_after_hours_briefing(positions, candidate_changes, afternoon_scan, today):
    """
    Generate after-hours risk and opportunity briefing via Claude.
    Returns None if nothing material detected.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    user_prompt = build_after_hours_prompt(
        positions=positions,
        candidate_changes=candidate_changes,
        afternoon_scan=afternoon_scan,
        today=today
    )

    log("Calling Claude for after-hours briefing...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=AFTER_HOURS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )

    raw_output = message.content[0].text
    sections = _parse_sections(raw_output)

    log(f"After-hours briefing generated — {message.usage.input_tokens} in | "
        f"{message.usage.output_tokens} out tokens")

    # Check if anything material was detected
    key_risk = sections.get("Key Risk Before Open", "").lower()
    if "no material" in key_risk:
        all_hold = True
        position_review = sections.get("Position Review", "").lower()
        if "reduce" in position_review or "exit" in position_review or "watch" in position_review:
            all_hold = False
        new_opps = sections.get("New Opportunities", "").lower()
        if "buy before close" in new_opps or "watch for open" in new_opps:
            all_hold = False
        if all_hold:
            log("No material developments — suppressing alert")
            return None

    return {
        "raw_text": raw_output,
        "sections": sections,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }


def _parse_sections(raw_text):
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
