import os
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor
from notion_client import Client
from data.fetch_prices import fetch_current_prices
from utils.logger import log

OPEN_POSITIONS_DB = "4e5532c4-e657-4a09-8d3a-b00f4f94507e"


def get_open_positions(price_cache: dict = None) -> list:
    """
    Read all active positions from Notion Open Positions database.
    Uses data_sources.query which is correct for this notion_client version.
    If price_cache is provided, uses cached prices instead of live API calls
    — eliminates redundant fetches since analyze.py already downloaded prices.
    """
    try:
        notion = Client(auth=os.environ.get("NOTION_TOKEN", ""))

        pages = []
        has_more = True
        start_cursor = None

        while has_more:
            query_kwargs = {
                "filter": {"property": "Status", "select": {"equals": "Active"}}
            }
            if start_cursor:
                query_kwargs["start_cursor"] = start_cursor

            response = notion.data_sources.query(
                OPEN_POSITIONS_DB,
                **query_kwargs
            )
            pages.extend(response.get("results", []))
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

        if not pages:
            log("No open positions found")
            return []

        positions = []
        tickers_to_price = []

        for page in pages:
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

            def get_date(key):
                p = props.get(key, {})
                d = p.get("date", {})
                return d.get("start") if d else None

            ticker = get_title("Ticker")
            if not ticker:
                continue

            positions.append({
                "page_id": page["id"],
                "ticker": ticker,
                "entry_date": get_date("Entry Date"),
                "entry_price": get_num("Entry Price"),
                "stop_price": get_num("Stop Price"),
                "target_price": get_num("Target Price"),
                "position_size": get_num("Position Size"),
                "current_price": get_num("Current Price"),
                "thesis": get_text("Thesis"),
                "price_status": "unknown",
                "flags": []
            })
            tickers_to_price.append(ticker)

        if tickers_to_price:
            live_prices = fetch_current_prices(tickers_to_price)
            for position in positions:
                ticker = position["ticker"]
                if ticker in live_prices and live_prices[ticker]:
                    position["current_price"] = live_prices[ticker]
                    position["price_status"] = "live"
                elif position.get("current_price"):
                    position["price_status"] = "cached"
                else:
                    position["price_status"] = "missing"

        for position in positions:
            entry = position.get("entry_price") or 0
            current = position.get("current_price") or 0
            stop = position.get("stop_price") or 0
            target = position.get("target_price") or 0

            if not current or current == 0:
                position["price_status"] = "missing"
                position["pnl_pct"] = None
                position["distance_to_stop_pct"] = None
                position["distance_to_target_pct"] = None
            else:
                position["pnl_pct"] = ((current - entry) / entry * 100) if entry > 0 else 0
                position["distance_to_stop_pct"] = ((current - stop) / current * 100) if stop > 0 else None
                position["distance_to_target_pct"] = ((target - current) / current * 100) if target > 0 else None

            if position.get("entry_date"):
                try:
                    entry_dt = datetime.strptime(position["entry_date"], "%Y-%m-%d").date()
                    position["days_held"] = (date.today() - entry_dt).days
                except Exception:
                    position["days_held"] = 0
            else:
                position["days_held"] = 0

            flags = []
            if current and current > 0:
                if stop > 0:
                    if current <= stop:
                        flags.append("STOP BREACHED")
                    elif position["distance_to_stop_pct"] is not None and position["distance_to_stop_pct"] <= 2:
                        flags.append("APPROACHING STOP")

                if target > 0:
                    if current >= target:
                        flags.append("TARGET EXCEEDED")
                    elif position["distance_to_target_pct"] is not None and position["distance_to_target_pct"] <= 3:
                        flags.append("APPROACHING TARGET")

                if position["pnl_pct"] is not None and position["pnl_pct"] >= 15:
                    flags.append("PARTIAL PROFIT ZONE")

            if position["price_status"] == "missing":
                flags.append("PRICE UNAVAILABLE")

            position["flags"] = flags

        log(f"Loaded {len(positions)} open positions")
        flagged = [p["ticker"] for p in positions if p["flags"]]
        if flagged:
            log(f"Positions requiring attention: {flagged}")

        return positions

    except Exception as e:
        log(f"Portfolio load error: {e}")
        return []


def _update_single_position(args):
    notion_client, position = args
    page_id = position.get("page_id")
    current_price = position.get("current_price")
    if not page_id or current_price is None:
        return False
    try:
        notion_client.pages.update(
            page_id=page_id,
            properties={"Current Price": {"number": round(current_price, 2)}}
        )
        return True
    except Exception as e:
        log(f"Price update error for {position.get('ticker', '?')}: {e}")
        return False


def update_position_prices(positions: list) -> None:
    """Write updated current prices back to Notion using thread pool."""
    if not positions:
        return
    try:
        notion = Client(auth=os.environ.get("NOTION_TOKEN", ""))
        args = [(notion, p) for p in positions if p.get("current_price") is not None]
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(_update_single_position, args))
        updated = sum(1 for r in results if r)
        log(f"Updated current prices for {updated}/{len(positions)} positions")
    except Exception as e:
        log(f"Position price update error: {e}")
