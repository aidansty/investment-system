import os
from v4.utils.logger import log
from v4.utils.telegram import send_telegram


def build_and_send_morning_telegram(
    macro: dict,
    industry_results: dict,
    news_package: dict,
    positions: list,
    briefing: dict,
    forward_catalysts: list,
    today: str,
    rules_output: dict = None,
) -> None:
    """
    Send two Telegram messages every morning.
    Message 1: Regime score + news + catalysts
    Message 2: Industries + rules engine signals + position actions
    """
    sections = briefing.get("sections", {}) if briefing else {}
    vix = macro.get("vix", 0)
    vix_regime = macro.get("vix_regime", "Yellow")
    vix_trend = macro.get("vix_trend", "Flat")
    vix_avg = macro.get("vix_5d_avg", 0)
    top_industries = industry_results.get("top_industries", []) if industry_results else []
    high_conviction = industry_results.get("high_conviction", []) if industry_results else []
    recent_news = news_package.get("recent_news", []) if news_package else []

    # Use composite regime score from rules engine
    re = rules_output or {}
    regime_score = re.get("regime_score", 0)
    regime = re.get("regime", vix_regime)
    regime_emoji = "🟢" if regime == "Green" else "🔴" if regime == "Red" else "🟡"
    kill_criteria = re.get("kill_criteria", {})
    entry_signals = re.get("entry_signals", [])
    exit_signals = re.get("exit_signals", [])

    # ─── MESSAGE 1: Market Regime + News + Catalysts ───────────────────────

    msg1 = []
    msg1.append(f"<b>📊 Morning Briefing — {today}</b>")
    msg1.append("")

    # Kill criteria alert first if triggered
    if kill_criteria.get("triggered"):
        msg1.append("🚨 <b>KILL CRITERIA TRIGGERED</b>")
        for alert in kill_criteria.get("alerts", []):
            msg1.append(f"  {alert.get('message', '')[:150]}")
        msg1.append("")

    # Composite regime score
    msg1.append(f"<b>{regime_emoji} Market Regime — {regime} ({regime_score}/100)</b>")
    market_overview = sections.get("Market Snapshot Explanation", sections.get("Market Overview", ""))
    if market_overview:
        sentences = [s.strip().lstrip("- ") for s in market_overview.split(chr(10)) if len(s.strip()) > 20]
        for s in sentences[:3]:
            msg1.append(f"  • {s}")
    else:
        trend_word = "falling" if vix_trend == "Falling" else "rising" if vix_trend in ("Rising", "Spiking") else "flat"
        msg1.append(f"  • VIX at {vix} ({vix_regime}), {trend_word} from {vix_avg} five-day average.")
    msg1.append("")

    # Key news labeled by how it affects you
    current_tickers = {p.get("ticker", "") for p in positions}
    if recent_news:
        msg1.append("<b>📰 Key News &amp; Events</b>")
        for n in recent_news[:5]:
            headline = n.get("headline", "")
            summary = n.get("summary", "")
            portfolio_impact = n.get("portfolio_impact", "")
            affected = n.get("affected_tickers", [])
            sentiment = n.get("sentiment", "").lower()
            if not headline:
                continue
            held = [t for t in affected if t in current_tickers]
            not_held = [t for t in affected if t not in current_tickers]
            if held:
                sentiment_word = "📈 Bullish" if sentiment == "bullish" else "📉 Bearish" if sentiment == "bearish" else "⚪ Neutral"
                label = f"{sentiment_word} for your {', '.join(held[:3])}"
            elif not_held:
                label = f"💡 Potential opportunity — {', '.join(not_held[:3])}"
            else:
                label = "🌐 Market-wide"
            msg1.append(f"<b>{headline[:75]}</b>")
            msg1.append(f"  {label}")
            if portfolio_impact:
                msg1.append(f"  {portfolio_impact[:150]}")
            elif summary:
                sentences = [s.strip() for s in summary.split(".") if len(s.strip()) > 15]
                if sentences:
                    msg1.append(f"  {sentences[0][:150]}.")
        msg1.append("")

    # Forward catalysts
    if forward_catalysts:
        msg1.append("<b>📅 Coming Up</b>")
        sorted_cats = sorted(forward_catalysts, key=lambda c: c.get("date", "9999"))
        for cat in sorted_cats[:4]:
            date = cat.get("date", "")
            event = cat.get("event", "")
            action = cat.get("action", "Hold")
            holdings = cat.get("affected_holdings", [])
            action_emoji = "🟢" if action in ("Buy", "Buy More") else "🔴" if action in ("Sell", "Trim") else "⚪"
            holdings_str = f" → {', '.join(holdings)}" if holdings else ""
            msg1.append(f"{action_emoji} [{date}] {event[:60]}{holdings_str}")
        msg1.append("")

    msg1.append("→ Full briefing on dashboard")

    # ─── MESSAGE 2: Industries + Positions + Action Items ───────────────────

    msg2 = []
    msg2.append(f"<b>💼 Portfolio Update — {today}</b>")
    msg2.append("")

    # Top industries with conviction
    if top_industries:
        msg2.append(f"<b>🏭 Top Industries ({len(high_conviction)} high conviction)</b>")
        for ind in top_industries[:4]:
            score = ind.get("conviction_score", 0)
            name = ind["industry"]
            etf = ind["etf"]
            excess = ind.get("excess_63d", 0)
            ripple = ind.get("ripple_benefits", [])
            news_count = ind.get("news_count", 0)
            rel_news = ind.get("relevant_news", [])
            msg2.append(f"<b>{name} ({etf})</b> — Conviction {score}/100")
            if excess > 0:
                msg2.append(f"  • Outperforming S&P 500 by {excess:.1f}% over the last 3 months.")
            if ripple:
                ripple_clean = [r.replace("_", " ") for r in ripple[:2]]
                msg2.append(f"  • Tailwinds from: {', '.join(ripple_clean)}.")
            if news_count >= 2:
                msg2.append(f"  • {news_count} news stories confirming this direction today.")
            if rel_news:
                headline = rel_news[0].get("headline", "")
                if headline:
                    msg2.append(f"  • {headline[:90]}")
        msg2.append("")

    if positions:
        msg2.append("<b>Position Review</b>")
        for p in positions:
            ticker = p.get("ticker", "")
            entry = p.get("entry", 0) or p.get("entry_price", 0) or 0
            current = p.get("current_price", 0) or 0
            stop = p.get("stop_price", 0) or 0
            pnl = round((current - entry) / entry * 100, 1) if entry > 0 else 0
            dist_stop = round((current - stop) / current * 100, 1) if current > 0 and stop > 0 else None
            pnl_str = f"{pnl:+.1f}%"
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"

            # Determine action and reason from briefing — try multiple section name variants
            pos_review = (
                sections.get("Open Position Review") or
                sections.get("Position Review") or
                sections.get("Portfolio Review") or ""
            )
            action = "HOLD"
            reason = "Thesis intact, no material changes today."

            if ticker in pos_review:
                # Extract the line for this ticker
                for line in pos_review.split("\n"):
                    if ticker in line:
                        if "EXIT" in line.upper():
                            action = "EXIT"
                        elif "REDUCE" in line.upper() or "TRIM" in line.upper():
                            action = "TRIM"
                        elif "WATCH" in line.upper():
                            action = "WATCH"
                        break

            # Only surface positions requiring attention — skip clean HOLDs
            if action == "HOLD":
                continue

            action_emoji = {"EXIT": "🔴", "TRIM": "🟠", "WATCH": "🟡", "REVIEW": "🟡"}.get(action, "🟢")
            msg2.append(f"{action_emoji} <b>{ticker}</b> {pnl_str} — {action}")
            ticker_block = ""
            in_block = False
            for line in pos_review.split(chr(10)):
                if ticker in line:
                    in_block = True
                if in_block and line.strip():
                    ticker_block += " " + line.strip()
                if in_block and len(ticker_block) > 20 and line.strip() == "":
                    break
            sentences = [s.strip() for s in ticker_block.replace(chr(10), " ").split(".") if len(s.strip()) > 20]
            bullets = sentences[:3] if sentences else [reason]
            for b in bullets:
                msg2.append(f"   • {b}.")

        msg2.append("")

    # Explicit action items
    action_items = _build_action_items(positions, forward_catalysts)
    if action_items:
        msg2.append("<b>⚡ Action Items Today</b>")
        for item in action_items:
            msg2.append(item)
        msg2.append("")

    # Rules engine entry signals
    if entry_signals:
        msg2.append("<b>🎯 Entry Signals (Rules Engine)</b>")
        for sig in entry_signals[:3]:
            size_pct = sig.get("size_pct", 0)
            entry_type = sig.get("entry_type", "full")
            size_label = f"{size_pct:.0%}" if size_pct else ""
            type_label = "REDUCED" if entry_type == "reduced" else "FULL"
            msg2.append(f"  📈 <b>{sig.get('ticker','')}</b> — {type_label} ENTRY {size_label}")
            msg2.append(f"     {sig.get('reason','')[:120]}")
        msg2.append("")

    # Rules engine exit signals
    exits_triggered = [s for s in exit_signals if s.get("action") == "exit"]
    if exits_triggered:
        msg2.append("<b>🚨 Exit Signals (Rules Engine)</b>")
        for sig in exits_triggered:
            urgency = sig.get("urgency", "")
            urgency_label = "IMMEDIATE" if urgency == "immediate" else "NEXT OPEN" if urgency == "next_open" else "TODAY"
            msg2.append(f"  🔴 <b>{sig.get('ticker','')}</b> — EXIT {urgency_label}")
            msg2.append(f"     {sig.get('reason','')[:120]}")
        msg2.append("")

    # Tax awareness flags
    tax_warnings = []
    for sig in exit_signals:
        tax = sig.get("tax_awareness", {})
        if tax.get("urgency") in ("high", "medium") and sig.get("action") != "exit":
            tax_warnings.append(f"  💰 <b>{sig.get('ticker','')}</b>: {tax.get('tax_recommendation','')[:100]}")
    if tax_warnings:
        msg2.append("<b>💰 Tax Awareness</b>")
        msg2.extend(tax_warnings[:3])
        msg2.append("")

    msg2.append("→ Full analysis on dashboard")

    # Send both messages
    send_telegram("\n".join(msg1))
    import time
    time.sleep(1)
    send_telegram("\n".join(msg2))

    log("Morning Telegram: 2 messages sent")


def _build_action_items(positions: list, forward_catalysts: list) -> list:
    """
    Generate specific action items based on position state and upcoming catalysts.
    Only fires when there is a specific data-driven reason.
    """
    items = []

    for p in positions:
        ticker = p.get("ticker", "")
        entry = p.get("entry_price", 0) or 0
        current = p.get("current_price", 0) or 0
        stop = p.get("stop_price", 0) or 0
        pnl = round((current - entry) / entry * 100, 1) if entry > 0 else 0
        dist_stop = round((current - stop) / current * 100, 1) if current > 0 and stop > 0 else None

        # Check for upcoming earnings within 10 days
        upcoming_earnings = [
            c for c in forward_catalysts
            if ticker in c.get("affected_holdings", [])
            and c.get("category", "") == "earnings"
        ]
        if upcoming_earnings:
            cat = upcoming_earnings[0]
            items.append(f"⏰ {ticker}: earnings {cat.get('date', 'soon')} — review setup: check guidance, analyst expectations, and risk/reward before deciding hold/trim/exit")

        # Stop proximity warning
        # No hardcoded stop alerts — Claude's analysis drives all action recommendations

        # No hardcoded loss thresholds — Claude drives all recommendations

    return items


def build_and_send_afternoon_telegram(
    positions: list,
    update: dict,
    new_opportunities: list,
    notable_moves: list,
    today: str,
    rules_output: dict = None,
) -> None:
    """
    Afternoon Telegram — ONLY sends when something urgent affects a holding
    OR a significant positive opportunity emerges. Silent otherwise.
    """
    sections = update.get("sections", {}) if update else {}
    re_data = rules_output or {}
    exit_signals = re_data.get("exit_signals", [])
    kill_criteria = re_data.get("kill_criteria", {})

    urgent_items = []

    # 1. Kill criteria
    if kill_criteria.get("triggered"):
        alerts = kill_criteria.get("alerts", [])
        urgent_items.append("\U0001f6a8 <b>KILL CRITERIA TRIGGERED</b>\n" + "\n".join(f"  {a.get('message', '')[:150]}" for a in alerts))

    # 2. Exit signals (thesis breaks, catalyst failures, checkpoint reviews)
    for sig in exit_signals:
        if sig.get("action") == "exit":
            ticker = sig.get("ticker", "")
            reason = sig.get("reason", "")[:200]
            exit_type = sig.get("exit_type", "")
            emoji = "\U0001f6a8" if exit_type in ("fast", "catalyst_failed") else "\U0001f534"
            urgent_items.append(f"{emoji} <b>{ticker} — EXIT</b>\n  {reason}")

    # 3. Thesis-breaking news in What Changed
    what_changed = sections.get("What Changed Since Morning") or sections.get("What Changed") or ""
    if what_changed:
        thesis_keywords = ["thesis break", "thesis is break", "exit", "close position",
                           "breaking news", "crash", "plunge", "halt", "warning",
                           "downgrade", "miss", "cut guidance", "fraud", "investigate",
                           "bomb", "war", "sanction", "tariff", "ban"]
        if any(kw in what_changed.lower() for kw in thesis_keywords):
            sentences = [s.strip() for s in what_changed.replace("\n", " ").split(".") if len(s.strip()) > 15]
            if sentences:
                urgent_items.append("<b>What Changed Today</b>\n" + "\n".join(f"  \u2022 {s}." for s in sentences[:4]))

    # 4. Urgent watch signals
    for sig in exit_signals:
        if sig.get("action") == "watch" and sig.get("urgency") == "next_open":
            urgent_items.append(f"\u26a0\ufe0f <b>{sig.get('ticker', '')} — WATCH (urgent)</b>\n  {sig.get('reason', '')[:150]}")

    # 5. Positive opportunity alerts — significant bullish catalysts during the day
    if sections:
        candidates_text = sections.get("New or Strengthened Candidates") or sections.get("New Opportunities") or ""
        if candidates_text:
            opp_keywords = ["fda approv", "beat estimate", "beat expectations", "raised guidance",
                            "upgrade", "contract win", "contract award", "acquisition",
                            "index inclusion", "added to", "stock split", "buyback",
                            "record revenue", "record earnings", "blowout", "surge"]
            if any(kw in candidates_text.lower() for kw in opp_keywords):
                sentences = [s.strip() for s in candidates_text.replace("\n", " ").split(".") if len(s.strip()) > 15]
                if sentences:
                    urgent_items.append("\U0001f4b0 <b>New Opportunity Detected</b>\n" + "\n".join(f"  \u2022 {s}." for s in sentences[:4]))

    # 6. Entry signals from rules engine
    entry_signals = re_data.get("entry_signals", [])
    for sig in entry_signals:
        ticker = sig.get("ticker", "")
        conviction = sig.get("conviction", 0)
        reason = sig.get("reason", "")[:150]
        size_pct = sig.get("size_pct", 0)
        urgent_items.append(f"\U0001f4b0 <b>{ticker} — ENTRY SIGNAL ({conviction}/100)</b>\n  Size: {size_pct:.0%} of active sleeve\n  {reason}")

    # Only send if something genuinely important happened
    if not urgent_items:
        log("Afternoon Telegram: no urgent developments or opportunities — skipping send")
        return

    msg = [f"<b>\U0001f4ca Afternoon Alert — {today}</b>", ""]
    msg.extend(urgent_items)

    send_telegram("\n".join(msg))
    log(f"Afternoon Telegram: alert sent ({len(urgent_items)} items)")

