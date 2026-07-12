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
    Morning Telegram — two concise, actionable messages.
    Message 1: Market regime (short) + actionable news + coming up
    Message 2: Catalyst scanner + position alerts + entry/exit signals
    """
    sections = briefing.get("sections", {}) if briefing else {}
    vix = macro.get("vix", 0)
    vix_regime = macro.get("vix_regime", "Yellow")
    vix_trend = macro.get("vix_trend", "Flat")
    recent_news = news_package.get("recent_news", []) if news_package else []

    re_data = rules_output or {}
    regime_score = re_data.get("regime_score", 0)
    regime = re_data.get("regime", vix_regime)
    regime_emoji = "\U0001f7e2" if regime == "Green" else "\U0001f534" if regime == "Red" else "\U0001f7e1"
    kill_criteria = re_data.get("kill_criteria", {})
    entry_signals = re_data.get("entry_signals", [])
    exit_signals = re_data.get("exit_signals", [])

    # ─── MESSAGE 1: Regime + News + Coming Up ─────────────────────────────

    msg1 = []
    msg1.append(f"<b>\U0001f4ca Morning Briefing — {today}</b>")
    msg1.append("")

    # Kill criteria alert
    if kill_criteria.get("triggered"):
        msg1.append("\U0001f6a8 <b>KILL CRITERIA TRIGGERED</b>")
        for alert in kill_criteria.get("alerts", []):
            msg1.append(f"  {alert.get('message', '')[:150]}")
        msg1.append("")

    # Market regime — SHORT (1 line + 1-2 sentences max)
    trend_meaning = {"Falling": "fear decreasing (bullish)", "Rising": "fear increasing (cautious)", "Spiking": "sharp fear spike (defensive)", "Flat": "stable sentiment"}.get(vix_trend, "")
    action_summary = {"Green": "Favorable for entering catalyst-driven positions at full size.", "Yellow": "Mixed conditions. Only enter with confirmed catalysts above 75 conviction.", "Red": "Defensive. No new entries until conditions stabilize."}.get(regime, "")
    msg1.append(f"<b>{regime_emoji} {regime} ({regime_score}/100)</b> — VIX {vix}, trend {vix_trend.lower()}")
    msg1.append(f"  {trend_meaning}. {action_summary}")
    msg1.append("")

    # Key news — ONLY real, significant news affecting holdings or creating opportunities
    # Filter out generic market commentary
    current_tickers = {p.get("ticker", "") for p in positions}
    crypto_skip = {"BTC", "ETH", "XRP", "ZEC", "SOL", "BNB"}
    stock_tickers = current_tickers - crypto_skip
    sig_keywords = ["EARNINGS", "FDA", "APPROV", "ACQUI", "MERGER", "CONTRACT", "LAUNCH",
                    "UPGRADE", "DOWNGRADE", "RECORD", "BEAT", "MISS", "GUIDANCE", "SPLIT",
                    "BUYBACK", "INDEX", "INCLUSION", "HALT", "CRASH", "SURGE"]
    noise_keywords = ["IF YOU INVESTED", "MEME COIN", "TRUMP", "WHAT WOULD", "PRICE TARGET",
                      "MAINTAINS RATING", "REITERATES", "INITIATES COVERAGE"]

    shown_news = []
    for n in recent_news[:10]:
        headline = n.get("headline", "")
        headline_upper = headline.upper()
        if any(nw in headline_upper for nw in noise_keywords):
            continue
        affected = n.get("affected_tickers", []) or []
        impact = n.get("portfolio_impact", "")
        summary = n.get("summary", "")
        sentiment = n.get("sentiment", "").lower()

        affects_holding = any(tk in stock_tickers for tk in affected) or any(tk in headline_upper for tk in stock_tickers if len(tk) >= 2)
        is_significant = any(sk in headline_upper for sk in sig_keywords)

        if affects_holding or (is_significant and affected):
            shown_news.append(n)
        if len(shown_news) >= 4:
            break

    if shown_news:
        msg1.append("<b>\U0001f4f0 Actionable Intelligence</b>")
        for n in shown_news:
            headline = n.get("headline", "")
            affected = n.get("affected_tickers", []) or []
            impact = n.get("portfolio_impact", "")
            summary = n.get("summary", "")
            held = [t for t in affected if t in stock_tickers]
            if held:
                label = f"Affects {', '.join(held[:3])}"
            elif affected:
                label = f"Opportunity: {', '.join(affected[:3])}"
            else:
                label = "Market-wide"
            msg1.append(f"\u2022 <b>{headline[:70]}</b>")
            msg1.append(f"  {label}")
            if impact:
                msg1.append(f"  {impact[:120]}")
            elif summary:
                first_sentence = summary.split(".")[0].strip()
                if len(first_sentence) > 15:
                    msg1.append(f"  {first_sentence[:120]}.")
        msg1.append("")

    # Coming up — keep as is, this works well
    if forward_catalysts:
        msg1.append("<b>\U0001f4c5 Coming Up</b>")
        sorted_cats = sorted(forward_catalysts, key=lambda c: c.get("date", "9999"))
        for cat in sorted_cats[:4]:
            date = cat.get("date", "")
            event = cat.get("event", "")
            holdings = cat.get("affected_holdings", [])
            holdings_str = f" \u2192 {', '.join(holdings)}" if holdings else ""
            msg1.append(f"  [{date}] {event[:60]}{holdings_str}")
        msg1.append("")

    msg1.append("\u2192 Full briefing on dashboard")
    send_telegram("\n".join(msg1))

    # ─── MESSAGE 2: Catalyst Scanner + Positions + Signals ─────────────────

    msg2 = []
    msg2.append(f"<b>\U0001f4bc Portfolio Update — {today}</b>")
    msg2.append("")

    # Catalyst scanner results (replaces top industries)
    catalyst_opps = re_data.get("catalyst_opportunities", [])
    if not catalyst_opps:
        # Try getting from briefing context
        catalyst_opps = briefing.get("catalyst_opportunities", []) if briefing else []
    if catalyst_opps:
        msg2.append(f"<b>\U0001f50e Catalyst Scanner ({len(catalyst_opps)} found)</b>")
        for c in catalyst_opps[:4]:
            cat_type = c.get("catalyst_type", "catalyst")
            days = c.get("days_until", 0)
            days_text = "today" if days == 0 else f"in {days} days"
            excess = c.get("excess_21d", 0)
            price = c.get("price", 0)
            msg2.append(f"  \U0001f4c8 <b>{c.get('ticker','')}</b> — {cat_type} {days_text}")
            msg2.append(f"    21d momentum: +{excess}pp vs SPY | Price: ${price}")
        if cat_type == 'post-catalyst-confirmed':
            msg2.append(f"    \u23f0 Execute after 9:45 AM — let opening volatility settle")
            if c.get("news_headlines"):
                msg2.append(f"    {c['news_headlines'][0][:80]}")
        msg2.append("")
    else:
        msg2.append("<b>\U0001f50e Catalyst Scanner</b>")
        msg2.append("  No qualifying catalyst opportunities found today.")
        msg2.append("")

    # Position alerts — only WATCH, EXIT, TRIM (skip clean HOLDs)
    # Use rules engine signals directly instead of parsing Claude text
    watch_exits = [s for s in exit_signals if s.get("action") in ("exit", "watch")]
    if watch_exits:
        msg2.append("<b>\U0001f4cb Position Alerts</b>")
        for sig in watch_exits:
            action = sig.get("action", "").upper()
            ticker = sig.get("ticker", "")
            reason = sig.get("reason", "")[:120]
            emoji = "\U0001f534" if action == "EXIT" else "\U0001f7e1"
            msg2.append(f"  {emoji} <b>{ticker}</b> — {action}")
            msg2.append(f"    {reason}")
        msg2.append("")

    # Action items — specific, not generic
    action_items = []
    for cat in (forward_catalysts or []):
        affected = cat.get("affected_holdings", [])
        held = [t for t in affected if t in stock_tickers]
        if held and cat.get("date"):
            event = cat.get("event", "")
            action = cat.get("action", "")
            for tk in held:
                pos = next((p for p in positions if p.get("ticker") == tk), None)
                if pos:
                    pnl = round(((pos.get("current_price", 0) or 0) - (pos.get("entry_price", 0) or pos.get("entry", 0) or 0)) / max((pos.get("entry_price", 0) or pos.get("entry", 0) or 1), 1) * 100, 1)
                    action_items.append(f"  \u23f0 <b>{tk}</b> ({pnl:+.1f}%): {event[:60]} on {cat.get('date','')}")
    if action_items:
        msg2.append("<b>\u26a1 Upcoming for Your Holdings</b>")
        for item in action_items[:4]:
            msg2.append(item)
        msg2.append("")

    # Entry signals — keep as is
    if entry_signals:
        msg2.append("<b>\U0001f3af Entry Signals</b>")
        for sig in entry_signals[:3]:
            size_pct = sig.get("size_pct", 0)
            entry_type = sig.get("entry_type", "full")
            type_label = "REDUCED" if entry_type == "reduced" else "FULL"
            msg2.append(f"  \U0001f4c8 <b>{sig.get('ticker','')}</b> — {type_label} ENTRY {size_pct:.0%}")
            msg2.append(f"    {sig.get('reason','')[:120]}")
        msg2.append("")

    # Exit signals — keep as is
    exits_triggered = [s for s in exit_signals if s.get("action") == "exit"]
    if exits_triggered:
        msg2.append("<b>\U0001f6a8 Exit Signals</b>")
        for sig in exits_triggered:
            msg2.append(f"  \U0001f534 <b>{sig.get('ticker','')}</b> — EXIT")
            msg2.append(f"    {sig.get('reason','')[:120]}")
        msg2.append("")

    msg2.append("\u2192 Full analysis on dashboard")
    send_telegram("\n".join(msg2))
    log(f"Morning Telegram: 2 messages sent")


# _build_action_items removed — action items built inline in morning telegram



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

