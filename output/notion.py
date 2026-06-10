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
                "Date": {"title": [{"type": "text", "text": {"content": date_str + " — 9AM Morning Briefing"}}]},
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
                "Date": {"title": [{"type": "text", "text": {"content": date_str + " — 9AM Morning Briefing"}}]},
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


AFTER_HOURS_ALERTS_DB = "0cbd97d0802842e09065e60e112362e1"  # Reuse Daily Briefings DB


def write_after_hours_alert(alert: dict, positions: list, today) -> str | None:
    """
    Write after-hours alert as a Notion page in the Daily Briefings database.
    Only called when material developments are detected.
    Designed to be read on a phone — short and scannable.
    """
    try:
        notion = get_notion_client()
        date_str = str(today)
        sections = alert.get("sections", {})
        tickers = ", ".join(p["ticker"] for p in positions)

        blocks = []

        # Urgent callout at top
        summary = sections.get("Alert Summary", "Review required before market open.")
        blocks.append(_callout("⚠️ AFTER-HOURS ALERT — " + summary, "⚠️"))
        blocks.append(_divider())

        if sections.get("Position Impact"):
            blocks.append(_heading("Position Impact"))
            blocks.append(_text_block(sections["Position Impact"]))
            blocks.append(_divider())

        if sections.get("Key Risk Tomorrow"):
            blocks.append(_heading("Key Risk Tomorrow"))
            blocks.append(_callout(sections["Key Risk Tomorrow"], "🔴"))

        blocks.append(_divider())
        blocks.append(_text_block("Positions monitored: " + tickers))

        # Write to Daily Briefings DB tagged as after-hours
        page = notion.pages.create(
            parent={"database_id": DAILY_BRIEFINGS_DB},
            properties={
                "Date": {"title": [{"type": "text", "text": {"content": date_str + " — After-Hours Alert"}}]},
                "Actions Required": {"checkbox": True},
            },
            children=blocks
        )

        page_url = page.get("url", "")
        log("After-hours alert written to Notion: " + page_url)
        return page_url

    except Exception as e:
        log("After-hours alert write error: " + str(e))
        return None


def write_after_hours_alert(briefing: dict, positions: list, today) -> str | None:
    """
    Write after-hours alert as a Notion page in the Daily Briefings database.
    Only called when material developments are detected.
    Designed to be read on a phone — short and scannable.
    """
    try:
        notion = get_notion_client()
        date_str = str(today)
        sections = briefing.get("sections", {})
        tickers = ", ".join(p["ticker"] for p in positions) if positions else "No positions"

        blocks = []

        summary = sections.get("Key Risk Before Open", "Review before market open.")
        blocks.append(_callout("AFTER-HOURS ALERT | " + date_str + " | " + summary, "⚠️"))
        blocks.append(_divider())

        if sections.get("Position Review"):
            blocks.append(_heading("Position Review"))
            blocks.append(_text_block(sections["Position Review"]))
            blocks.append(_divider())

        if sections.get("New Opportunities"):
            blocks.append(_heading("New Opportunities"))
            blocks.append(_text_block(sections["New Opportunities"]))
            blocks.append(_divider())

        if sections.get("Key Risk Before Open"):
            blocks.append(_heading("Key Risk Before Open"))
            blocks.append(_callout(sections["Key Risk Before Open"], "🔴"))

        blocks.append(_divider())
        blocks.append(_text_block("Positions monitored: " + tickers))

        page = notion.pages.create(
            parent={"database_id": DAILY_BRIEFINGS_DB},
            properties={
                "Date": {"title": [{"type": "text", "text": {"content": date_str + " — 3PM Alert ⚠️"}}]},
                "Actions Required": {"checkbox": True},
                "Bullish Points": {"number": 0},
                "Bearish Points": {"number": 0},
            },
            children=blocks
        )

        page_url = page.get("url", "")
        log("After-hours alert written to Notion: " + page_url)
        return page_url

    except Exception as e:
        log("After-hours alert write error: " + str(e))
        return None


CANDIDATE_ANALYSIS_DB = "34c25f29-1aea-4416-bb9f-89421bf2dabc"
AFTER_HOURS_BRIEFING_DB = "e4c6418f08b54a14ae8748e1da7e437e"


def write_candidate_analysis(candidates: list, today) -> None:
    """
    Write full audit trail for every Strong and Developing candidate.
    All raw calculations, every flag value, every signal score.
    This is the data source for the 30-trade review.
    """
    if not candidates:
        return

    try:
        notion = get_notion_client()
        written = 0
        date_str = str(today)

        for c in candidates:
            ticker = c.get("ticker", "")
            if not ticker:
                continue

            props = {
                "Ticker": {"title": [{"type": "text", "text": {"content": ticker}}]},
                "Tier": {"select": {"name": c.get("tier", "Watch")}},
                "Composite Score": {"number": c.get("composite_score")},
                "RS Score Raw": {"number": c.get("raw_rs") or c.get("rs_score")},
                "RS Normalized": {"number": c.get("rs_normalized")},
                "Ticker 63d Return": {"number": c.get("rs_return")},
                "SPY 63d Return": {"number": c.get("spy_return")},
                "Beat Streak": {"number": c.get("beat_streak")},
                "Earnings Score": {"number": c.get("earnings_score")},
                "Catalyst Score": {"number": c.get("catalyst_score")},
                "Has Catalyst": {"checkbox": bool(c.get("has_catalyst", False))},
                "Days To Catalyst": {"number": c.get("days_to_catalyst")},
                "Catalyst Confirmed": {"checkbox": bool(c.get("catalyst_confirmed", False))},
                "ATR 14 Day Pct": {"number": c.get("atr_14d_pct")},
                "ATR Stop Pct": {"number": c.get("atr_stop_pct")},
                "ATR Stop Price": {"number": c.get("atr_stop_price")},
                "Profit Target T1": {"number": c.get("tier1_target_price")},
                "VIX At Scan": {"number": c.get("vix_at_scan")},
                "Insider Net 90d": {"number": c.get("insider_net_90d")},
                "Implied Move Pct": {"number": c.get("implied_move_pct")},
                "Sector": {"rich_text": [{"type": "text", "text": {"content": c.get("sector", "")}}]},
                "Sub Industry": {"rich_text": [{"type": "text", "text": {"content": c.get("sub_industry", "")}}]},
                "Missing Signal": {"rich_text": [{"type": "text", "text": {"content": c.get("missing_signal", "")}}]},
                "Flags Applied": {"rich_text": [{"type": "text", "text": {"content": c.get("flags_str", "")}}]},
            }

            # Optional fields with enum values
            if c.get("freshness"):
                props["Freshness"] = {"select": {"name": c["freshness"]}}
            if c.get("reaction_quality"):
                props["Reaction Quality"] = {"select": {"name": c["reaction_quality"]}}
            if c.get("conviction_tier"):
                props["Conviction Tier"] = {"select": {"name": c["conviction_tier"]}}
            if c.get("vix_regime"):
                props["VIX Regime"] = {"select": {"name": c["vix_regime"]}}
            if c.get("implied_move_check"):
                props["Implied Move Check"] = {"select": {"name": c["implied_move_check"]}}
            if c.get("insider_flag"):
                props["Insider Flag"] = {"select": {"name": c["insider_flag"]}}
            if c.get("base_position_size"):
                props["Base Position Size"] = {"select": {"name": c["base_position_size"]}}
            if c.get("final_position_size"):
                props["Final Position Size"] = {"select": {"name": c["final_position_size"]}}

            # Date fields
            if c.get("catalyst_date"):
                props["Catalyst Date"] = {"date": {"start": c["catalyst_date"]}}
            if c.get("pre_earnings_exit_date"):
                props["Pre Earnings Exit Date"] = {"date": {"start": c["pre_earnings_exit_date"]}}
            if c.get("sector_overlap_with"):
                props["Sector Overlap With"] = {"rich_text": [{"type": "text", "text": {"content": c["sector_overlap_with"]}}]}

            props["Scan Date"] = {"date": {"start": date_str}}
            if c.get("five_day_return") is not None:
                props["5 Day Return"] = {"number": c["five_day_return"]}
            if c.get("ten_day_return") is not None:
                props["10 Day Return"] = {"number": c["ten_day_return"]}
            if c.get("avg_post_earnings_return") is not None:
                props["Avg Post Earnings Return"] = {"number": c["avg_post_earnings_return"]}

            notion.pages.create(
                parent={"database_id": "fc07a1e8f3544a679066ef7e8a572bdd"},
                properties=props
            )
            written += 1

        log(f"Candidate analysis written: {written} records to audit trail")

    except Exception as e:
        log(f"Candidate analysis write error: {e}")
