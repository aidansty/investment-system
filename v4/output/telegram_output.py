import os
from v4.utils.logger import log
from v4.utils.telegram import send_telegram


def build_morning_telegram(
    macro: dict,
    industry_results: dict,
    positions: list,
    briefing_sections: dict,
    forward_catalysts: list,
    today: str,
) -> str:
    """
    Morning Telegram message.
    Short, scannable, under 60 seconds to read.
    Full analysis available on web dashboard.
    """
    vix = macro.get("vix", 0)
    vix_regime = macro.get("vix_regime", "Yellow")
    vix_trend = macro.get("vix_trend", "Flat")
    regime_emoji = "🟢" if vix_regime == "Green" else "🔴" if vix_regime == "Red" else "🟡"
    trend_arrow = "↓" if vix_trend == "Falling" else "↑" if vix_trend in ("Rising", "Spiking") else "→"

    top = industry_results.get("top_industries", [])
    high = industry_results.get("high_conviction", [])

    lines = []
    lines.append(f"<b>📊 {today} — Morning Briefing</b>")
    lines.append(f"{regime_emoji} VIX {vix} {trend_arrow} ({vix_regime}) | {len(high)} high-conviction")
    lines.append("")

    # Critical market note — only if something major
    market_overview = briefing_sections.get("Market Overview", "")
    if market_overview:
        # Extract first sentence only
        first_sentence = market_overview.split(".")[0].strip()
        if first_sentence:
            lines.append(f"<i>{first_sentence}.</i>")
            lines.append("")

    # Top industries
    if top:
        lines.append("<b>Top Industries</b>")
        for ind in top[:4]:
            score = ind.get("conviction_score", 0)
            name = ind["industry"]
            etf = ind["etf"]
            excess = ind.get("excess_63d", 0)
            emoji = "🔥" if score >= 70 else "👀" if score >= 45 else "—"
            lines.append(f"{emoji} {name} ({etf}) | +{excess:.1f}pp | {score}/100")
    else:
        lines.append("⚪ No high-conviction industries today — consider holding cash")
    lines.append("")

    # Position alerts only — skip if all clear
    alerts = []
    for p in positions:
        ticker = p.get("ticker", "")
        entry = p.get("entry_price", 0) or 0
        current = p.get("current_price", 0) or 0
        stop = p.get("stop_price", 0) or 0
        pnl = ((current - entry) / entry * 100) if entry > 0 else 0
        dist_stop = ((current - stop) / current * 100) if current > 0 and stop > 0 else 0

        if dist_stop < 3 and stop > 0:
            alerts.append(f"⚠️ {ticker} near stop ({dist_stop:.1f}% away)")
        elif pnl <= -10:
            alerts.append(f"🔴 {ticker} down {pnl:.1f}% — review required")
        elif pnl >= 15:
            alerts.append(f"✅ {ticker} up {pnl:.1f}% — consider taking profits")

    if alerts:
        lines.append("<b>Position Alerts</b>")
        for alert in alerts:
            lines.append(alert)
    else:
        lines.append("✅ All positions stable")

    # Surface the single nearest catalyst affecting current holdings
    if forward_catalysts:
        holding_tickers = {p.get("ticker") for p in positions}
        relevant = [
            c for c in forward_catalysts
            if set(c.get("affected_holdings", [])) & holding_tickers
        ]
        if relevant:
            relevant.sort(key=lambda c: c.get("date", "9999"))
            nearest = relevant[0]
            lines.append("")
            lines.append(f"📅 Next: {nearest.get('date')} — {nearest.get('event')}")

    return "\n".join(lines)


def build_afternoon_telegram(
    positions: list,
    update_sections: dict,
    new_opportunities: list,
    today: str,
) -> str:
    """
    Afternoon Telegram message.
    Portfolio status and any action required before close.
    """
    lines = []
    lines.append(f"<b>📈 {today} — Afternoon Update</b>")
    lines.append("")

    # Position review
    portfolio_review = update_sections.get("Portfolio Review", "")
    if portfolio_review:
        lines.append("<b>Portfolio</b>")
        # Show each line of portfolio review
        for line in portfolio_review.strip().split("\n"):
            line = line.strip()
            if line:
                if "EXIT" in line:
                    lines.append(f"🔴 {line}")
                elif "REDUCE" in line:
                    lines.append(f"🟠 {line}")
                elif "WATCH" in line:
                    lines.append(f"🟡 {line}")
                elif "HOLD" in line:
                    lines.append(f"🟢 {line}")
                else:
                    lines.append(line)
        lines.append("")

    # New opportunities
    if new_opportunities:
        lines.append("<b>New Opportunities</b>")
        for opp in new_opportunities[:2]:
            lines.append(f"• {opp}")
        lines.append("")

    # Close watch
    close_watch = update_sections.get("Market Close Watch", "")
    if close_watch and "no urgent" not in close_watch.lower():
        lines.append(f"⏰ {close_watch.strip()}")

    return "\n".join(lines)
