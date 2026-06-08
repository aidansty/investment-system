import os
import re
import requests
from utils.logger import log
from utils.rate_limiter import finnhub_limiter

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")

# Sampling window — not "top news by importance"
# Downstream Claude synthesis should treat this as incomplete context
MAX_HEADLINES = 20


def _normalize_for_dedup(headline: str) -> str:
    """
    Normalize headline text for deduplication comparison only.
    Lowercase + remove punctuation + collapse whitespace.
    Not used in output — only for duplicate detection.
    """
    text = headline.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def fetch_market_news() -> list:
    """
    Fetch recent general market news from Finnhub.
    Pure ingestion layer — no sentiment, classification, or ranking.
    All intelligence stays in downstream Claude synthesis.

    Returns list of structured dicts, sorted by datetime if available.
    Falls back to raw API order if timestamps are missing or inconsistent
    (logged as warning when this occurs).

    Each item:
        {
            "headline": str,
            "source":   str,
            "datetime": str | None,  # ISO format when available
            "id":       str | None
        }
    """
    try:
        finnhub_limiter.wait()
        url = (
            f"https://finnhub.io/api/v1/news"
            f"?category=general&token={FINNHUB_KEY}"
        )
        r = requests.get(url, timeout=10)

        if r.status_code != 200:
            log(f"News fetch failed: HTTP {r.status_code}")
            return []

        data = r.json()
        if not data or not isinstance(data, list):
            log("News fetch returned empty or invalid response")
            return []

        # Parse structured articles
        articles = []
        for item in data:
            headline = item.get("headline", "").strip()
            if not headline:
                continue

            # Finnhub returns Unix timestamp in "datetime" field
            raw_ts = item.get("datetime")
            iso_dt = None
            if raw_ts:
                try:
                    from datetime import datetime, timezone
                    iso_dt = datetime.fromtimestamp(
                        int(raw_ts), tz=timezone.utc
                    ).isoformat()
                except (ValueError, TypeError):
                    pass

            articles.append({
                "headline": headline,
                "source": item.get("source", "").strip(),
                "datetime": iso_dt,
                "id": str(item.get("id", "")) or None
            })

        # Sort by datetime descending if timestamps available
        has_timestamps = sum(1 for a in articles if a["datetime"])
        if has_timestamps >= len(articles) * 0.8:
            articles.sort(key=lambda x: x["datetime"] or "", reverse=True)
        else:
            log("WARNING: News ordering unverified — "
                f"only {has_timestamps}/{len(articles)} articles have timestamps")

        # Deduplicate by normalized headline
        seen = set()
        deduped = []
        for article in articles:
            key = _normalize_for_dedup(article["headline"])
            if key not in seen:
                seen.add(key)
                deduped.append(article)

        dupes_removed = len(articles) - len(deduped)
        if dupes_removed > 0:
            log(f"News deduplication: removed {dupes_removed} duplicate headlines")

        # Apply sampling window
        result = deduped[:MAX_HEADLINES]
        log(f"News fetched: {len(result)} headlines "
            f"(from {len(data)} raw, {dupes_removed} dupes removed)")

        return result

    except Exception as e:
        log(f"News fetch error: {e}")
        return []
