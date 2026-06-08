import os
import anthropic
from utils.logger import log
from config.prompts import DAILY_BRIEFING_SYSTEM_PROMPT, build_daily_briefing_prompt


def generate_daily_briefing(regime, macro, news, candidates, positions, today):
    """
    Make a single Claude Sonnet call to generate the complete daily briefing.
    Assembles verified context from all upstream data sources.
    Claude receives only verified data — no external lookups permitted.

    Returns dict:
        {
            "raw_text": str,
            "sections": dict,
            "model": str,
            "input_tokens": int,
            "output_tokens": int
        }
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    user_prompt = build_daily_briefing_prompt(
        regime=regime,
        macro=macro,
        news=news,
        candidates=candidates,
        positions=positions,
        today=str(today)
    )

    log("Calling Claude Sonnet — context assembled")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        system=DAILY_BRIEFING_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    raw_output = message.content[0].text
    sections = _parse_sections(raw_output)

    log(f"Briefing generated — {message.usage.input_tokens} input tokens | "
        f"{message.usage.output_tokens} output tokens | "
        f"{len(sections)} sections parsed")

    return {
        "raw_text": raw_output,
        "sections": sections,
        "model": message.model,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }


def _parse_sections(raw_text):
    """
    Split Claude output into named sections by ## headers.
    Returns dict: {section_name: content_string}
    """
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
