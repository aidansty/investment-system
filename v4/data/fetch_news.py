import os
import time
import requests
from datetime import datetime, timedelta
from v4.utils.logger import log
from v4.config.settings import NEWS_MAX_HEADLINES, NEWS_LOOKBACK_HOURS

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")


def fetch_market_news() -> list:
    """
    Fetch market news from multiple sources.
    Returns deduplicated list of news items sorted newest first.
    Each item: {headline, source, datetime, url, summary}
    """
    all_news = []

    # Source 1: Finnhub general market news
    finnhub_news = _fetch_finnhub_news()
    all_news.extend(finnhub_news)

    # Source 2: Alpha Vantage news sentiment
    if ALPHA_VANTAGE_KEY:
        av_news = _fetch_alpha_vantage_news()
        all_news.extend(av_news)

    # Deduplicate by headline similarity
    seen_headlines = set()
    deduped = []
    for item in all_news:
        headline = item.get("headline", "").lower()[:60]
        if headline not in seen_headlines:
            seen_headlines.add(headline)
            deduped.append(item)

    # Sort newest first
    deduped.sort(key=lambda x: x.get("datetime", ""), reverse=True)

    log(f"News fetched: {len(deduped)} headlines ({len(all_news)} raw, {len(all_news)-len(deduped)} dupes removed)")
    return deduped[:NEWS_MAX_HEADLINES]


def fetch_ticker_news(ticker: str, days: int = 1) -> list:
    """
    Fetch news for a specific ticker.
    Used in afternoon position review.
    """
    if not FINNHUB_KEY:
        return []

    try:
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        to_date = datetime.now().strftime("%Y-%m-%d")
        url = (
            f"https://finnhub.io/api/v1/company-news"
            f"?symbol={ticker}&from={from_date}&to={to_date}&token={FINNHUB_KEY}"
        )
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        results = []
        for item in data[:10]:
            headline = item.get("headline", "").strip()
            if headline:
                results.append({
                    "headline": headline,
                    "source": item.get("source", ""),
                    "datetime": str(item.get("datetime", "")),
                    "url": item.get("url", ""),
                    "summary": item.get("summary", ""),
                })
        return results
    except Exception as e:
        log(f"Ticker news error for {ticker}: {e}")
        return []


def _fetch_finnhub_news() -> list:
    if not FINNHUB_KEY:
        return []
    try:
        url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_KEY}"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            log(f"Finnhub news error: {r.status_code}")
            return []
        data = r.json()
        results = []
        cutoff = datetime.now() - timedelta(hours=NEWS_LOOKBACK_HOURS)
        for item in data:
            ts = item.get("datetime", 0)
            if ts and datetime.fromtimestamp(ts) < cutoff:
                continue
            headline = item.get("headline", "").strip()
            if headline:
                results.append({
                    "headline": headline,
                    "source": item.get("source", "Finnhub"),
                    "datetime": datetime.fromtimestamp(ts).isoformat() if ts else "",
                    "url": item.get("url", ""),
                    "summary": item.get("summary", ""),
                })
        return results
    except Exception as e:
        log(f"Finnhub news fetch error: {e}")
        return []


def _fetch_alpha_vantage_news() -> list:
    if not ALPHA_VANTAGE_KEY:
        return []
    try:
        url = (
            f"https://www.alphavantage.co/query"
            f"?function=NEWS_SENTIMENT&limit=50&apikey={ALPHA_VANTAGE_KEY}"
        )
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        feed = data.get("feed", [])
        results = []
        for item in feed[:30]:
            headline = item.get("title", "").strip()
            if headline:
                results.append({
                    "headline": headline,
                    "source": item.get("source", "Alpha Vantage"),
                    "datetime": item.get("time_published", ""),
                    "url": item.get("url", ""),
                    "summary": item.get("summary", ""),
                })
        return results
    except Exception as e:
        log(f"Alpha Vantage news error: {e}")
        return []
