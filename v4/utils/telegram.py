import os
import requests
from v4.utils.logger import log

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

def send_telegram(message: str, parse_mode: str = "HTML") -> bool:
    """
    Send a message to Telegram.
    Returns True if successful, False if failed.
    Message is automatically truncated to 4096 chars (Telegram limit).
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("Telegram credentials not set — skipping notification")
        return False

    # Telegram max message length
    message = message[:4096]

    try:
        response = requests.post(
            TELEGRAM_API_URL,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": parse_mode,
            },
            timeout=10
        )
        if response.status_code == 200:
            log("Telegram message sent successfully")
            return True
        else:
            log(f"Telegram send failed: {response.status_code} — {response.text}")
            return False
    except Exception as e:
        log(f"Telegram error: {e}")
        return False


def send_morning_summary(regime: str, top_industries: list, position_alerts: list, vix_regime: str) -> bool:
    """
    Send concise morning summary to Telegram.
    Designed to be readable in under 60 seconds on a phone.
    """
    lines = []
    lines.append(f"<b>📊 Morning Briefing</b>")
    lines.append(f"Market: <b>{regime}</b> | VIX: <b>{vix_regime}</b>")
    lines.append("")

    if top_industries:
        lines.append("<b>🏭 Top Industries</b>")
        for ind in top_industries[:4]:
            score = ind.get("conviction_score", 0)
            name = ind.get("industry", "")
            etf = ind.get("etf", "")
            lines.append(f"• {name} ({etf}) — Conviction: {score}/100")
        lines.append("")

    if position_alerts:
        lines.append("<b>⚠️ Position Alerts</b>")
        for alert in position_alerts:
            lines.append(f"• {alert}")
        lines.append("")
    else:
        lines.append("✅ All positions stable")
        lines.append("")

    lines.append("Open dashboard for full briefing →")

    return send_telegram("\n".join(lines))


def send_afternoon_summary(position_updates: list, new_opportunities: list) -> bool:
    """
    Send concise afternoon portfolio update to Telegram.
    """
    lines = []
    lines.append("<b>📈 Afternoon Update</b>")
    lines.append("")

    if position_updates:
        lines.append("<b>Portfolio</b>")
        for update in position_updates:
            ticker = update.get("ticker", "")
            action = update.get("action", "HOLD")
            reason = update.get("reason", "")
            emoji = "🔴" if action in ("EXIT", "REDUCE") else "🟡" if action == "WATCH" else "🟢"
            lines.append(f"{emoji} {ticker} — {action}: {reason}")
        lines.append("")

    if new_opportunities:
        lines.append("<b>New Opportunities</b>")
        for opp in new_opportunities[:2]:
            lines.append(f"• {opp}")
    else:
        lines.append("No new opportunities identified")

    return send_telegram("\n".join(lines))
