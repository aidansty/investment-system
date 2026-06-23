import os
from v4.utils.logger import log


def calculate_opportunity_cost(
    positions: list,
    top_industries: list,
    spy_entry_price: float = 659.44,
) -> list:
    """
    For each position, compare expected return vs redeploying into
    the highest-conviction current opportunity.
    Returns enriched positions with opportunity_cost_note added.
    """
    if not top_industries:
        return positions

    best_opportunity = top_industries[0] if top_industries else None

    enriched = []
    for p in positions:
        p = dict(p)
        ticker = p.get("ticker", "")
        entry = p.get("entry_price", 0) or 0
        current = p.get("current_price", 0) or 0
        pnl = round((current - entry) / entry * 100, 2) if entry > 0 else 0

        if best_opportunity and best_opportunity.get("industry") and ticker not in ["SPY", "BTC", "ETH", "XRP", "ZEC"]:
            best_name = best_opportunity.get("industry", "")
            best_etf = best_opportunity.get("etf", "")
            best_excess = best_opportunity.get("excess_63d", 0)
            best_conviction = best_opportunity.get("conviction_score", 0)

            if best_conviction >= 70 and pnl < 5 and pnl > -20:
                p["opportunity_cost_note"] = (
                    f"Capital here ({pnl:+.1f}% return) could alternatively be deployed into "
                    f"{best_name} ({best_etf}) which is outperforming SPY by {best_excess:.1f}pp "
                    f"with {best_conviction}/100 conviction — worth comparing expected returns."
                )
            else:
                p["opportunity_cost_note"] = None
        else:
            p["opportunity_cost_note"] = None

        enriched.append(p)

    return enriched


def build_opportunity_cost_context(positions: list, top_industries: list) -> str:
    """
    Build a context block for Claude summarizing opportunity cost comparisons.
    """
    enriched = calculate_opportunity_cost(positions, top_industries)
    notes = [(p["ticker"], p["opportunity_cost_note"]) for p in enriched if p.get("opportunity_cost_note")]

    if not notes:
        return ""

    block = "OPPORTUNITY COST COMPARISONS:\n"
    for ticker, note in notes:
        block += f"{ticker}: {note}\n"

    return block
