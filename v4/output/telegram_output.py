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
) -> None:
    """
    Send two Telegram messages every morning.
    Message 1: Market overview + news + forward catalysts
    Message 2: Position review + alerts + action items
    """
    sections = briefing.get("sections", {}) if briefing else {}
    vix = macro.get("vix", 0)
    vix_regime = macro.get("vix_regime", "Yellow")
    vix_trend = macro.get("vix_trend", "Flat")
    vix_avg = macro.get("vix_5d_avg", 0)
    top_industries = industry_results.get("top_industries", []) if industry_results else []
    high_conviction = industry_results.get("high_conviction", []) if industry_results else []
    recent_news = news_package.get("recent_news", []) if news_package else []

    regime_emoji = "🟢" if vix_regime == "Green" else "🔴" if vix_regime == "Red" else "🟡"

    # ─── MESSAGE 1: Market Regime + News + Catalysts ───────────────────────

    msg1 = []
    msg1.append(f"<b>📊 Morning Briefing — {today}</b>")
    msg1.append("")

    # Regime with plain English reasoning
    msg1.append(f"<b>{regime_emoji} Market Regime</b>")
    market_overview = sections.get("Market Overview", "")
    if market_overview:
        sentences = [s.strip() for s in market_overview.replace("\n", " ").split(".") if len(s.strip()) > 20]
        regime_summary = ". ".join(sentences[:2]) + "." if sentences else market_overview[:300]
        msg1.append(regime_summary)
    else:
        trend_word = "falling" if vix_trend == "Falling" else "rising" if vix_trend in ("Rising", "Spiking") else "flat"
        msg1.append(f"VIX at {vix} ({vix_regime}), {trend_word} from {vix_avg} five-day average.")
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

            # Override with specific known situations
            if pnl <= -10 and dist_stop and dist_stop < 5:
                action = "WATCH"
                reason = f"Down {pnl_str} and within {dist_stop:.1f}% of stop ${stop:.2f}. Monitor closely."
            elif pnl <= -15:
                action = "REVIEW"
                reason = f"Down {pnl_str} — mandatory thesis review triggered. Has anything changed?"

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
        if dist_stop is not None and dist_stop < 3:
            items.append(f"⚠️ {ticker}: only {dist_stop:.1f}% above stop ${stop:.2f} — watch closely at open")

        # Large loss with no stop buffer
        if pnl <= -15:
            items.append(f"🔴 {ticker}: down {pnl:+.1f}% — mandatory review, has the thesis changed?")

    return items


def build_and_send_afternoon_telegram(
    positions: list,
    update: dict,
    new_opportunities: list,
    notable_moves: list,
    today: str,
) -> None:
    """
    Send afternoon portfolio update via Telegram.
    Two messages: what changed + positions, then opportunities.
    """
    sections = update.get("sections", {}) if update else {}

    msg1 = []
    msg1.append(f"<b>📈 Afternoon Update — {today}</b>")
    msg1.append("")

    # What changed
    what_changed = (
        sections.get("What Changed Since Morning") or
        sections.get("What Changed") or
        sections.get("Portfolio Review") or ""
    )
    if what_changed:
        msg1.append("<b>What Changed Today</b>")
        sentences = [s.strip() for s in what_changed.replace("\n", " ").split(".") if len(s.strip()) > 15]
        for s in sentences[:3]:
            msg1.append(f"• {s}.")
        msg1.append("")

    # Notable moves
    if notable_moves:
        msg1.append("<b>Notable Price Moves</b>")
        for m in notable_moves[:4]:
            ticker = m.get("ticker", "")
            move = m.get("move", "")
            reason = m.get("reason", "")
            msg1.append(f"• <b>{ticker} {move}</b> — {reason[:100]}")
        msg1.append("")

    # Position updates — only show positions where something changed or action needed
    position_review = (
        sections.get("Portfolio Actions Before Close") or
        sections.get("Open Position Review") or
        sections.get("Portfolio Actions") or
        sections.get("Portfolio Review") or ""
    )
    if positions and position_review:
        flagged = []
        for p in positions:
            ticker = p.get("ticker", "")
            entry = p.get("entry", 0) or p.get("entry_price", 0) or 0
            current = p.get("current_price", 0) or 0
            pnl = round((current - entry) / entry * 100, 1) if entry > 0 else 0
            pnl_str = f"{pnl:+.1f}%"

            # Determine if Claude flagged this position with an action
            action = None
            reason = None
            for line in position_review.split(chr(10)):
                if ticker in line:
                    upper = line.upper()
                    if "EXIT" in upper or "SELL" in upper or "CLOSE" in upper:
                        action = "CLOSE"
                        reason = line.strip()[:120]
                    elif "BUY" in upper or "ADD" in upper:
                        action = "BUY MORE"
                        reason = line.strip()[:120]
                    elif "TRIM" in upper or "REDUCE" in upper:
                        action = "TRIM"
                        reason = line.strip()[:120]
                    elif "WATCH" in upper or "MONITOR" in upper:
                        action = "WATCH"
                        reason = line.strip()[:120]
                    break

            if action:
                emoji = {"CLOSE": "🔴", "TRIM": "🟠", "BUY MORE": "🟢", "WATCH": "🟡"}.get(action, "⚪")
                flagged.append(f"{emoji} <b>{ticker}</b> {pnl_str} — {action}")
                # Extract 2-3 sentences from the review block as bullets
                ticker_block = ""
                in_block = False
                for line in position_review.split(chr(10)):
                    if ticker in line:
                        in_block = True
                    if in_block and line.strip():
                        ticker_block += " " + line.strip()
                    if in_block and len(ticker_block) > 20 and line.strip() == "":
                        break
                sentences = [s.strip() for s in ticker_block.replace(chr(10)," ").split(".") if len(s.strip()) > 20]
                for s in sentences[:3]:
                    flagged.append(f"   • {s}.")

        if flagged:
            msg1.append("<b>Positions Needing Attention</b>")
            msg1.extend(flagged)
        else:
            msg1.append("<b>Positions</b>")
            msg1.append("• No position changes warranted — hold everything into close.")

    msg1.append("")
    msg1.append("→ Full update on dashboard")

    msg2 = []
    # Flatten new_opportunities — it may arrive as a list-of-lists from the pipeline
    opps_flat = []
    for item in (new_opportunities or []):
        if isinstance(item, list):
            opps_flat.extend(item)
        elif isinstance(item, dict):
            opps_flat.append(item)

    if opps_flat:
        msg2.append("<b>🏭 New or Strengthened Opportunities</b>")
        for opp in opps_flat[:3]:
            if not isinstance(opp, dict):
                continue
            name = opp.get("industry", "")
            etf = opp.get("etf", "")
            score = opp.get("conviction_score", opp.get("conviction", 0))
            excess = opp.get("excess_63d", 0)
            ripple = opp.get("ripple_benefits", [])
            rel_news = opp.get("relevant_news", [])
            msg2.append(f"• <b>{name} ({etf})</b> — Conviction {score}/100")
            if excess > 0:
                msg2.append(f"  · Outperforming SPY by {excess:.1f}% over 3 months.")
            if ripple:
                ripple_clean = [r.replace("_", " ") for r in ripple[:2]]
                msg2.append(f"  · Tailwinds from: {', '.join(ripple_clean)}.")
            if rel_news:
                headline = rel_news[0].get("headline", "")
                if headline:
                    msg2.append(f"  · {headline[:90]}")
        msg2.append("")

    close_watch = sections.get("Market Close Watch", "")
    if close_watch and "no urgent" not in close_watch.lower():
        msg2.append(f"<b>⏰ Before Close</b>")
        msg2.append(close_watch.strip()[:300])
        msg2.append("")

    msg2.append("→ Full analysis on dashboard")

    send_telegram("\n".join(msg1))
    if len(msg2) > 3:
        import time
        time.sleep(1)
        send_telegram("\n".join(msg2))

    log("Afternoon Telegram: messages sent")
