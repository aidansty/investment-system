import os
from datetime import date
from notion_client import Client
from utils.logger import log

DAILY_BRIEFINGS_DB = "0cbd97d0802842e09065e60e112362e1"
OPEN_POSITIONS_DB = "4685bb9d2ea6414991d22e91a26b46be"
TRADE_CANDIDATES_DB = "b013410dfaa94be79c8eec6b408ba380"
COMPLETED_TRADES_DB = "292f8151ad7048ab8ae5d71f07e50ae5"


def get_notion_client() -> Client:
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        raise ValueError("NOTION_TOKEN environment variable not set")
    return Client(auth=token)


def _text_block(content: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": content[:2000]}}]
        }
    }


def _heading(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        }
    }


def _callout(text: str, emoji: str = "💡") -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": text[:2000]}}],
            "icon": {"type": "emoji", "emoji": emoji}
        }
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def write_daily_briefing(briefing: dict, regime: dict, scan_results: dict, today: date) -> str | None:
    try:
        notion = get_notion_client()
        date_str = today.isoformat()
        stats = scan_results.get("scan_stats", {})
        sections = briefing.get("sections", {})

        label = regime["label"]
        confidence = regime["confidence"]
        bullish = regime["bullish_points"]
        bearish = regime["bearish_points"]
        emoji = "🟢" if label == "Bullish" else "🔴" if label == "Bearish" else "🟡"

        blocks = []
        summary = emoji + " " + label + " — " + confidence + " Confidence | " + str(bullish) + "/5 bullish | " + str(bearish) + "/5 bearish"
        blocks.append(_callout(summary, emoji))
        blocks.append(_divider())

        section_map = [
            ("Market Regime", "📊 Market Regime"),
            ("Market News Summary", "📰 Market News"),
            ("Today's Key Events", "📅 Today's Key Events"),
            ("Open Position Review", "💼 Open Position Review"),
            ("Strong Candidates", "🎯 Strong Candidates"),
            ("Developing Candidates", "👀 Developing Candidates"),
            ("Risk Assessment", "⚠️ Risk Assessment"),
        ]

        for key, heading in section_map:
            content = sections.get(key)
            if content:
                blocks.append(_heading(heading))
                blocks.append(_text_block(content))
                blocks.append(_divider())

        footer = (
            "Scan: " + str(stats.get("universe_size", 0)) + " universe"
            + " → " + str(stats.get("rs_qualified", 0)) + " RS"
            + " → " + str(stats.get("trend_qualified", 0)) + " trend"
            + " → " + str(stats.get("strong_count", 0)) + " strong | "
            + str(stats.get("developing_count", 0)) + " developing"
        )
        blocks.append(_text_block(footer))

        page = notion.pages.create(
            parent={"database_id": DAILY_BRIEFINGS_DB},
            properties={
                "Date": {"title": [{"type": "text", "text": {"content": date_str}}]},
                "Regime": {"select": {"name": label}},
                "Confidence": {"select": {"name": confidence}},
                "Candidates Found": {"number": stats.get("strong_count", 0)},
                "Actions Required": {"checkbox": False},
                "Degraded Data": {"checkbox": regime.get("degraded", False)},
                "Bullish Points": {"number": bullish},
                "Bearish Points": {"number": bearish},
            },
            children=blocks
        )

        page_url = page.get("url", "")
        log("Daily briefing written: " + page_url)
        return page_url

    except Exception as e:
        log("Notion briefing write error: " + str(e))
        return None


def write_trade_candidates(scan_results: dict, regime: dict, today: date) -> str | None:
    """
    Write one daily Trade Candidates page to Notion.
    Strong candidates get full readable writeups.
    Developing candidates get a single summary line each.
    Organized by date — one page per trading day.
    """
    if not scan_results:
        return None

    try:
        notion = get_notion_client()
        date_str = today.isoformat()
        strong = scan_results.get("strong", [])
        developing = scan_results.get("developing", [])

        blocks = []

        regime_label = regime["label"]
        emoji = "🟢" if regime_label == "Bullish" else "🔴" if regime_label == "Bearish" else "🟡"

        header = emoji + " " + regime_label + " regime | " + str(len(strong)) + " Strong | " + str(len(developing)) + " Developing"
        blocks.append(_callout(header, emoji))
        blocks.append(_divider())

        # Strong candidates — full writeup
        blocks.append(_heading("🎯 Strong Candidates — Review These Today"))

        if strong:
            for c in strong:
                if c.get("has_catalyst"):
                    catalyst_str = "Earnings in " + str(c["days_to_catalyst"]) + " trading days (" + str(c["catalyst_date"]) + ")"
                else:
                    catalyst_str = "No confirmed catalyst in window"

                lines = [
                    c["ticker"],
                    "Outperforming market by " + str(round(c["rs_score"], 1)) + "pp over 63 days (stock returned " + str(round(c["rs_return"], 1)) + "%)",
                    str(c["beat_streak"]) + " consecutive earnings beats (earnings score: " + str(round(c["earnings_score"], 1)) + "/1.0)",
                    "Catalyst: " + catalyst_str,
                    "Composite score: " + str(c["composite_score"]) + " | Missing signals: " + str(c.get("missing_signal", "None")),
                ]
                entry_text = "\n".join(lines)
                blocks.append(_text_block(entry_text))
                blocks.append(_divider())
        else:
            blocks.append(_text_block("No strong candidates today."))
            blocks.append(_divider())

        # Developing candidates — one line each
        blocks.append(_heading("👀 Developing — Watch List"))

        if developing:
            dev_lines = []
            for c in developing[:15]:
                if c.get("has_catalyst"):
                    cat = "catalyst in " + str(c["days_to_catalyst"]) + "d"
                else:
                    cat = "no catalyst"
                line = c["ticker"] + ": RS " + str(round(c["rs_score"], 1)) + "pp | " + str(c["beat_streak"]) + " beats | " + cat + " | Missing: " + str(c.get("missing_signal", "Below threshold"))
                dev_lines.append(line)
            if len(developing) > 15:
                dev_lines.append("...and " + str(len(developing) - 15) + " more developing candidates")
            blocks.append(_text_block("\n".join(dev_lines)))
        else:
            blocks.append(_text_block("No developing candidates today."))

        page = notion.pages.create(
            parent={"database_id": TRADE_CANDIDATES_DB},
            properties={
                "Date": {"title": [{"type": "text", "text": {"content": date_str}}]},
                "Regime": {"select": {"name": regime_label}},
                "Strong Count": {"number": len(strong)},
                "Developing Count": {"number": len(developing)},
            },
            children=blocks
        )

        page_url = page.get("url", "")
        log("Trade candidates written to Notion: " + page_url)
        return page_url

    except Exception as e:
        log("Trade candidates write error: " + str(e))
        return None


def get_open_positions() -> list:
    try:
        notion = get_notion_client()
        response = notion.data_sources.query(
            "4e5532c4-e657-4a09-8d3a-b00f4f94507e",
            filter={"property": "Status", "select": {"equals": "Active"}}
        )

        positions = []
        for page in response.get("results", []):
            props = page.get("properties", {})

            def get_num(key):
                p = props.get(key, {})
                return p.get("number")

            def get_text(key):
                p = props.get(key, {})
                rt = p.get("rich_text", [])
                return rt[0]["text"]["content"] if rt else ""

            def get_title(key):
                p = props.get(key, {})
                t = p.get("title", [])
                return t[0]["text"]["content"] if t else ""

            positions.append({
                "page_id": page["id"],
                "ticker": get_title("Ticker"),
                "entry_price": get_num("Entry Price"),
                "stop_price": get_num("Stop Price"),
                "target_price": get_num("Target Price"),
                "position_size": get_num("Position Size"),
                "current_price": get_num("Current Price"),
                "thesis": get_text("Thesis"),
            })

        log("Loaded " + str(len(positions)) + " open positions from Notion")
        return positions

    except Exception as e:
        log("Position load error: " + str(e))
        return []


def update_open_position_prices(positions: list) -> None:
    if not positions:
        return
    try:
        notion = get_notion_client()
        updated = 0
        for p in positions:
            page_id = p.get("page_id")
            price = p.get("current_price")
            if not page_id or price is None:
                continue
            notion.pages.update(
                page_id=page_id,
                properties={"Current Price": {"number": price}}
            )
            updated += 1
        log("Updated prices for " + str(updated) + " positions")
    except Exception as e:
        log("Position price update error: " + str(e))
