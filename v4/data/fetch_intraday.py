"""
Fetch intraday (today's) price candles for stock positions via Finnhub.
Called server-side during the morning pipeline — writes data into dashboard_data.js
so the browser can render charts without hitting Finnhub directly (which is blocked
on the free tier from the browser).
"""

import os
import time
import requests
from datetime import datetime, timezone, timedelta
from v4.utils.logger import log

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
RATE_LIMIT_DELAY = 0.5

def fetch_intraday_candles(positions: list) -> dict:
    if not FINNHUB_KEY:
        log("FINNHUB_KEY not set — skipping intraday fetch")
        return {}

    now_utc = datetime.now(timezone.utc)
    et_offset = timedelta(hours=-4)
    market_open_utc = now_utc.replace(hour=13, minute=30, second=0, microsecond=0)
    market_close_utc = now_utc.replace(hour=20, minute=0, second=0, microsecond=0)

    if now_utc.weekday() >= 5:
        log("Weekend — intraday fetch skipped")
        return {}

    t_from = int(market_open_utc.timestamp())
    t_to = int(min(now_utc, market_close_utc).timestamp())

    if now_utc < market_open_utc:
        # Before market open — fetch yesterday's full session
        prev = now_utc - timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= timedelta(days=1)
        prev_open = prev.replace(hour=13, minute=30, second=0, microsecond=0)
        prev_close = prev.replace(hour=20, minute=0, second=0, microsecond=0)
        t_from = int(prev_open.timestamp())
        t_to = int(prev_close.timestamp())
        log(f"Pre-market: fetching {prev.strftime('%Y-%m-%d')} session candles")

    crypto_tickers = {"BTC", "ETH", "XRP", "ZEC", "BNB", "SOL", "DOGE"}
    stock_positions = [
        p for p in positions
        if p.get("ticker") not in crypto_tickers
        and p.get("type", "").lower() != "crypto"
    ]

    log(f"Fetching intraday candles for {len(stock_positions)} positions...")
    results = {}

    for pos in stock_positions:
        ticker = pos.get("ticker")
        if not ticker:
            continue
        try:
            url = (
                f"https://finnhub.io/api/v1/stock/candle"
                f"?symbol={ticker}&resolution=5&from={t_from}&to={t_to}"
                f"&token={FINNHUB_KEY}"
            )
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                log(f"  {ticker}: HTTP {r.status_code}")
                continue
            data = r.json()
            if data.get("s") != "ok":
                log(f"  {ticker}: no data (status={data.get('s')})")
                continue
            closes = data.get("c", [])
            timestamps = data.get("t", [])
            if not closes or not timestamps:
                continue
            labels = []
            for ts in timestamps:
                dt_et = datetime.fromtimestamp(ts, tz=timezone.utc) + et_offset
                labels.append(dt_et.strftime("%-I:%M"))
            results[ticker] = {"closes": [round(c, 2) for c in closes], "labels": labels}
            log(f"  {ticker}: {len(closes)} candles OK")
        except Exception as e:
            log(f"  {ticker}: error — {e}")
        time.sleep(RATE_LIMIT_DELAY)

    log(f"Intraday fetch complete: {len(results)}/{len(stock_positions)} tickers")
    return results
