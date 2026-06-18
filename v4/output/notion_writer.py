import os
from datetime import date
from notion_client import Client
from v4.utils.logger import log

# Notion database IDs — reusing existing workspace
MORNING_BRIEFING_DB = "0cbd97d0802842e09065e60e112362e1"
AFTER_HOURS_BRIEFING_DB = "e4c6418f08b54a14ae8748e1da7e437e"
OPEN_POSITIONS_DB = "4e5532c4-e657-4a09-8d3a-b00f4f94507e"


def get_notion_client() -> Client:
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        raise ValueError("NOTION_TOKEN not set")
    return Client(auth=token)


def _text_block(content: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": content[:1900]}}]
        }
    }


def _heading2(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        }
    }


def _heading3(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        }
    }


def _callout(text: str, emoji: str = "📊") -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": text[:1900]}}],
            "icon": {"type": "emoji", "emoji": emoji}
        }
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _text_blocks(content: str) -> list:
    blocks = []
    while content:
        chunk = content[:1900]
        blocks.append(_text_block(chunk))
        content = content[1900:]
    return blocks


def write_morning_briefing(
    briefing: dict,
    industry_results: dict,
    macro: dict,
    positions: list,
    today,
) -> str | None:
    """Write morning briefing to Notion."""
    try:
        notion = get_notion_client()
        date_str = str(today)
        sections = briefing.get("sections", {})
        vix_regime = macro.get("vix_regime", "Yellow")
        top_industries = industry_results.get("top_industries", [])
        high_conviction = industry_results.get("high_conviction", [])

        regime_emoji = "🟢" if vix_regime == "Green" else "🔴" if vix_regime == "Red" else "🟡"

        blocks = []

        # Header
        header = (
            f"{regime_emoji} VIX {macro.get('vix', 0)} ({vix_regime}) | "
            f"{len(high_conviction)} High-Conviction Industries | "
            f"{len(positions)} Positions"
        )
        blocks.append(_callout(header, regime_emoji))
        blocks.append(_divider())

        # Market Overview
        if sections.get("Market Overview"):
            blocks.append(_heading2("📈 Market Overview"))
            blocks.extend(_text_blocks(sections["Market Overview"]))
            blocks.append(_divider())

        # Major Macro Developments
        if sections.get("Major Macro Developments"):
            blocks.append(_heading2("🌍 Major Macro Developments"))
            blocks.extend(_text_blocks(sections["Major Macro Developments"]))
            blocks.append(_divider())

        # Industry Opportunities
        if sections.get("Industry Opportunities"):
            blocks.append(_heading2("🏭 Industry Opportunities"))
            blocks.extend(_text_blocks(sections["Industry Opportunities"]))
            blocks.append(_divider())

        # Open Position Review
        if sections.get("Open Position Review"):
            blocks.append(_heading2("💼 Open Position Review"))
            blocks.extend(_text_blocks(sections["Open Position Review"]))
            blocks.append(_divider())

        # Risk Assessment
        if sections.get("Risk Assessment & Cash Guidance"):
            blocks.append(_heading2("⚠️ Risk Assessment & Cash Guidance"))
            blocks.extend(_text_blocks(sections["Risk Assessment & Cash Guidance"]))
            blocks.append(_divider())

        # Industry scan summary
        summary = f"Industries scanned: 25 | Layer 1: {len(industry_results.get('layer1', []))} | High conviction: {len(high_conviction)}"
        blocks.append(_text_block(summary))

        page = notion.pages.create(
            parent={"database_id": MORNING_BRIEFING_DB},
            properties={
                "Date": {"title": [{"type": "text", "text": {"content": date_str + " — 9AM Morning Briefing"}}]},
                "Actions Required": {"checkbox": len(high_conviction) > 0},
                "Bullish Points": {"number": len(high_conviction)},
                "Bearish Points": {"number": 0},
            },
            children=blocks
        )

        url = page.get("url", "")
        log(f"Morning briefing written to Notion: {url}")
        return url

    except Exception as e:
        log(f"Notion morning briefing write error: {e}")
        return None


def write_afternoon_update(
    update: dict,
    positions: list,
    today,
) -> str | None:
    """Write afternoon update to After Hours Briefing database."""
    try:
        notion = get_notion_client()
        date_str = str(today)
        sections = update.get("sections", {})

        blocks = []

        # Header
        blocks.append(_callout(f"📈 Afternoon Update — {date_str}", "📈"))
        blocks.append(_divider())

        if sections.get("Portfolio Review"):
            blocks.append(_heading2("💼 Portfolio Review"))
            blocks.extend(_text_blocks(sections["Portfolio Review"]))
            blocks.append(_divider())

        if sections.get("New Opportunities"):
            blocks.append(_heading2("🏭 New Opportunities"))
            blocks.extend(_text_blocks(sections["New Opportunities"]))
            blocks.append(_divider())

        if sections.get("Market Close Watch"):
            blocks.append(_heading2("⏰ Market Close Watch"))
            blocks.extend(_text_blocks(sections["Market Close Watch"]))

        has_alerts = any(
            action in sections.get("Portfolio Review", "").upper()
            for action in ["EXIT", "REDUCE", "WATCH"]
        )

        page = notion.pages.create(
            parent={"database_id": AFTER_HOURS_BRIEFING_DB},
            properties={
                "Date": {"title": [{"type": "text", "text": {"content": date_str}}]},
                "Actions Required": {"checkbox": has_alerts},
                "Positions Monitored": {"number": len(positions)},
                "Material Changes": {"checkbox": has_alerts},
            },
            children=blocks
        )

        url = page.get("url", "")
        log(f"Afternoon update written to Notion: {url}")
        return url

    except Exception as e:
        log(f"Notion afternoon update write error: {e}")
        return None


def get_open_positions() -> list:
    """Read open positions from Notion."""
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
                return props.get(key, {}).get("number")

            def get_text(key):
                rt = props.get(key, {}).get("rich_text", [])
                return rt[0]["text"]["content"] if rt else ""

            def get_title(key):
                t = props.get(key, {}).get("title", [])
                return t[0]["text"]["content"] if t else ""

            def get_select(key):
                s = props.get(key, {}).get("select")
                return s["name"] if s else ""

            def get_date(key):
                d = props.get(key, {}).get("date", {})
                return d.get("start") if d else None

            positions.append({
                "page_id": page["id"],
                "ticker": get_title("Ticker"),
                "entry_price": get_num("Entry Price"),
                "stop_price": get_num("Stop Price"),
                "target_price": get_num("Target Price"),
                "current_price": get_num("Current Price"),
                "position_size": get_num("Position Size"),
                "holding_type": get_select("Holding Type") if "Holding Type" in props else "Not specified",
                "thesis": get_text("Thesis"),
                "entry_date": get_date("Entry Date"),
            })

        log(f"Loaded {len(positions)} open positions")
        return [p for p in positions if p["ticker"]]

    except Exception as e:
        log(f"Position load error: {e}")
        return []


def update_position_prices(positions: list, price_cache: dict) -> None:
    """Update current prices in Notion for all open positions."""
    if not positions:
        return
    try:
        notion = get_notion_client()
        updated = 0
        for p in positions:
            ticker = p.get("ticker")
            page_id = p.get("page_id")
            price = price_cache.get(ticker)
            if not page_id or not price:
                continue
            notion.pages.update(
                page_id=page_id,
                properties={"Current Price": {"number": price}}
            )
            p["current_price"] = price
            updated += 1
        log(f"Updated prices for {updated}/{len(positions)} positions")
    except Exception as e:
        log(f"Position price update error: {e}")
