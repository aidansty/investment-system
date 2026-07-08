import os
import re
import time
import requests
import feedparser
import anthropic
from datetime import datetime, timedelta
import pytz
from v4.utils.logger import log
from v4.config.settings import INDUSTRY_ETF_MAP

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Yahoo Finance and CNBC RSS feeds — free, public, real-time
YAHOO_FINANCE_RSS = "https://finance.yahoo.com/news/rssindex"
CNBC_TOP_NEWS_RSS = "https://www.cnbc.com/id/100003114/device/rss/rss.html"
CNBC_MARKETS_RSS = "https://www.cnbc.com/id/20910258/device/rss/rss.html"
CNBC_ECONOMY_RSS = "https://www.cnbc.com/id/20910258/device/rss/rss.html"


def fetch_rss_news(hours_back: int = 20) -> list:
    """
    Fetch recent news from Yahoo Finance and CNBC RSS feeds.
    Window: after market close yesterday through premarket today.
    """
    eastern = pytz.timezone("America/New_York")
    cutoff = datetime.now(eastern) - timedelta(hours=hours_back)

    feeds = [
        ("Yahoo Finance", YAHOO_FINANCE_RSS),
        ("CNBC Top News", CNBC_TOP_NEWS_RSS),
        ("CNBC Markets", CNBC_MARKETS_RSS),
    ]

    all_items = []

    for source_name, feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:30]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                summary = entry.get("summary", "") or entry.get("description", "")
                link = entry.get("link", "")

                # Parse publish date
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=pytz.UTC).astimezone(eastern)

                # Skip if older than cutoff (unless no date available)
                if pub_date and pub_date < cutoff:
                    continue

                all_items.append({
                    "headline": title,
                    "source": source_name,
                    "datetime": pub_date.isoformat() if pub_date else "",
                    "url": link,
                    "summary": _clean_html(summary)[:300],
                })

        except Exception as e:
            log(f"RSS fetch error for {source_name}: {e}")
            continue

    log(f"RSS news fetched: {len(all_items)} items from Yahoo Finance + CNBC")
    return all_items


def _clean_html(text: str) -> str:
    """Strip HTML tags from RSS summary text."""
    clean = re.sub(r"<[^>]+>", "", text)
    return clean.strip()


def filter_relevant_news(news_items: list) -> list:
    """
    Relevance filtering is now handled inside deduplicate_and_summarize()
    in a single merged Claude call — cutting one full redundant API round-trip.
    This function passes items through unchanged.
    """
    return news_items


def deduplicate_and_summarize(news_items: list) -> list:
    """
    Group articles covering the same story into one summary.
    10 Iran articles become 1 entry with a 2-3 sentence summary
    covering key points across all of them.
    """
    if not news_items:
        return []

    if len(news_items) <= 3:
        return news_items

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    headlines_block = "\n".join([
        f"{i+1}. {item['headline']} — {item.get('summary', '')[:200]}"
        for i, item in enumerate(news_items)
    ])

    # Build positions context dynamically
    try:
        import json as _json, os as _os
        _pos_path = _os.path.join(_os.path.dirname(__file__), "..", "config", "positions.json")
        with open(_pos_path) as _f:
            positions_str = ", ".join([p["ticker"] for p in _json.load(_f).get("positions", [])])
    except Exception:
        positions_str = "SPY, NVDA, SPCX, AMD, MU, INTC, CRWV, NOK, SCO, HUM, BTC, ETH, ZEC, XRP"

    prompt = f"""You are analyzing financial news for an investor with these holdings: {positions_str}

Here are {len(news_items)} headlines to analyze:

{headlines_block}

Group headlines covering the SAME story together. For each unique story, return a JSON object.

STRICT RELEVANCE RULES — only include news that meets AT LEAST ONE of these criteria:
1. Directly affects one or more of the investor's holdings (listed above)
2. Affects an entire sector/industry that the investor is exposed to (semiconductors, AI infrastructure, crypto, managed care, oil, aerospace, networking)
3. Is a major macro event that moves the whole market (Fed decisions, CPI/jobs data, geopolitical events affecting oil or supply chains)
4. Represents a specific new investment opportunity in an industry the investor watches

REJECT these types of stories entirely — do not include them:
- Analyst reports about companies NOT in the holdings list (e.g. DuPont, Becton Dickinson, random S&P 500 stocks)
- Earnings from unrelated companies
- General market recaps with no specific portfolio relevance
- News about industries with zero connection to the portfolio

If after filtering fewer than 3 stories are relevant, include the 3 most market-relevant macro stories.

Return ONLY a valid JSON array. No markdown, no explanation, just the JSON:
[
  {{
    "headline": "Clear descriptive title (max 80 chars)",
    "summary": "2-3 sentences explaining exactly what happened and why it matters",
    "portfolio_impact": "1-2 sentences on how this specifically affects the investor — is it bullish or bearish for their holdings, or is this a new opportunity they should consider?",
    "bullets": [
      "What happened: one clear sentence",
      "Why it matters: one clear sentence on market or sector impact",
      "Portfolio relevance: name the SPECIFIC holding(s) from the list above this affects and explain exactly how (bullish/bearish, thesis strengthened/weakened). If no current holding is affected, name the specific NEW investment opportunity this points to. NEVER write a generic sentence — always name specific tickers."
    ],
    "affected_tickers": ["list of tickers from holdings affected, or new tickers representing opportunities"],
    "sentiment": "bullish or bearish or neutral",
    "source_count": 1,
    "category": "fed/economic/industry/company/geopolitical/crypto"
  }}
]"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        import json
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            grouped = json.loads(match.group())
            log(f"Deduplication: {len(news_items)} articles → {len(grouped)} grouped stories")
            return grouped
        else:
            log("Deduplication: could not parse response")
            return news_items

    except Exception as e:
        log(f"Deduplication error: {e}")
        return news_items


def fetch_critical_market_events() -> list:
    """
    Web search for critical events RSS feeds may miss —
    Fed meetings, major economic data, significant IPOs,
    geopolitical events with market impact.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    eastern = pytz.timezone("America/New_York")
    today_str = datetime.now(eastern).strftime("%B %d, %Y")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": f"""Search Yahoo Finance and CNBC for the most important financial market news today, {today_str}.

Focus on:
1. Federal Reserve decisions, statements, or meetings today
2. Major economic data releases today (CPI, jobs, GDP, PCE, retail sales)
3. Major IPOs trading today or pricing today
4. Geopolitical events affecting markets today
5. Any major corporate events (M&A, bankruptcy, regulatory action)

Only include events that would appear on the Yahoo Finance or CNBC front page right now.

Return ONLY a JSON array, nothing else:
[
  {{"headline": "...", "source": "web search", "datetime": "{today_str}", "summary": "2-3 sentences", "category": "fed/economic/ipo/geopolitical/corporate"}}
]"""
            }]
        )

        for block in response.content:
            if hasattr(block, "text"):
                text = block.text.strip()
                match = re.search(r"\[.*\]", text, re.DOTALL)
                if match:
                    import json
                    events = json.loads(match.group())
                    log(f"Web search found {len(events)} critical market events")
                    return events

        return []

    except Exception as e:
        log(f"Critical events web search error: {e}")
        return []


def fetch_forward_catalysts(current_holdings: list = None) -> list:
    """
    Web search for forward-looking catalysts in the next 1-3 weeks.
    Upcoming earnings, Fed meetings, FDA decisions, IPO lockups,
    economic data release dates — anything with a known future date
    that affects our industries or holdings.

    Every catalyst gets a single-word action decision:
    - Buy: new position, not currently held, catalyst suggests entry
    - Buy More: currently held, catalyst suggests further upside
    - Sell: currently held, catalyst suggests downside, full exit warranted
    - Trim: currently held, some downside risk but not severe — includes trim percentage
    - Hold: uncertain direction, wait for clarity on a specific date/event
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    eastern = pytz.timezone("America/New_York")
    today_str = datetime.now(eastern).strftime("%B %d, %Y")

    industries_list = ", ".join(list(INDUSTRY_ETF_MAP.keys())[:15])
    holdings = current_holdings or ["SPY","NVDA","SPCX","AMD","MU","INTC","PLTR","CRWV","NOK","SCO","HUM","BTC","ETH","ZEC","XRP"]
    holdings_str = ", ".join(holdings)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": f"""Today is {today_str}. Search for upcoming market-moving events scheduled in the next 1 to 3 weeks.

Focus on events affecting: {industries_list}, and these specific current holdings: {holdings_str}.

Look for:
1. Upcoming earnings report dates for major companies in these industries
2. Scheduled Fed/FOMC meeting dates
3. Scheduled economic data releases (CPI, jobs report, GDP)
4. FDA decision dates for pharma/biotech
5. IPO lockup expiration dates
6. Major product launch or conference dates

For each catalyst, assign exactly ONE action word based on this decision logic:

- "Buy": this is a NEW industry, ETF, or stock not in current holdings ({holdings_str}), and the catalyst suggests a good entry opportunity.
- "Buy More": this affects a CURRENT holding and the catalyst suggests further price increase is likely.
- "Sell": this affects a CURRENT holding and the catalyst suggests meaningful price decrease is likely — full exit warranted.
- "Trim": this affects a CURRENT holding and the catalyst suggests SOME downside risk, but not severe enough to fully exit. Include trim_percentage (a number 10-50) based on your confidence in the negative signal — low confidence/mild risk = 10-20%, high confidence/significant risk = 30-50%.
- "Hold": the catalyst could move price in either direction and there is genuine uncertainty. Specify what future date, event, or news development would resolve the uncertainty.

Then populate exactly ONE of these two fields based on the action:
- entry_opportunity: ONLY if action is "Buy" or "Buy More" — describe the specific event, date, news, or price level signaling when to actually enter or add to the position.
- exit_opportunity: ONLY if action is "Sell" or "Trim" — describe the specific event, date, news, or price level signaling when to actually sell or trim the position.

Leave the unused field as null. For "Hold" actions, leave both entry_opportunity and exit_opportunity as null, and instead populate watch_for with the specific date/event/news that would resolve the uncertainty.

CRITICAL JSON FORMATTING RULES — FOLLOW EXACTLY:
- Output ONLY the raw JSON array. No markdown code fences. No commentary before or after. No explanation.
- Use double quotes for every string. Never single quotes, never smart/curly quotes.
- NEVER use the literal value null. Every field must be a string or array of strings.
- If a field does not apply, use the exact string "N/A" instead of null or omitting it.
- No trailing comma after the last field in an object or the last object in the array.
- Keep every text field under 200 characters, one plain sentence, no embedded quotes, no line breaks.
- ABSOLUTE RULE: never use a double-quote character anywhere inside a text field value. If you need to reference a word, name, or quoted term, write it WITHOUT quotation marks around it instead. Example: write "the breakthrough therapy designation" not "the "breakthrough therapy" designation".
- Do not use parentheses containing quotes, do not use nicknames in quotes, do not quote any term for emphasis.
- trim_percentage must always be a string like "25" or "N/A", never a bare number and never null.
- affected_holdings must always be an array — use [] if none, never null.

Return ONLY a JSON array. Every object must have EXACTLY these 10 fields, in this order, every time:
[
  {{
    "event": "short event name",
    "date": "YYYY-MM-DD",
    "industry_or_ticker": "name",
    "why_it_matters": "one plain sentence",
    "category": "earnings",
    "action": "Buy",
    "trim_percentage": "N/A",
    "entry_opportunity": "specific signal or N/A",
    "exit_opportunity": "specific signal or N/A",
    "affected_holdings": []
  }}
]

action must be exactly one of: Buy, Buy More, Sell, Trim, Hold
For Buy or Buy More: fill entry_opportunity, set exit_opportunity to "N/A"
For Sell or Trim: fill exit_opportunity, set entry_opportunity to "N/A". For Trim, trim_percentage must be a number string like "30".
For Hold: set both entry_opportunity and exit_opportunity to describe what to watch for to resolve the uncertainty

Only include events with confirmed or highly likely specific dates. Maximum 8 events.
Include both catalysts affecting current holdings AND catalysts representing new entry opportunities in tracked industries we do not currently hold.
Before responding, verify your JSON is valid — every object has all 10 fields, no null values, no trailing commas."""
            }]
        )

        for block in response.content:
            if hasattr(block, "text"):
                text = block.text.strip()
                match = re.search(r"\[.*\]", text, re.DOTALL)
                if match:
                    import json
                    raw_json = match.group()
                    try:
                        catalysts = json.loads(raw_json)
                        log(f"Forward catalysts found: {len(catalysts)}")
                        return catalysts
                    except json.JSONDecodeError as je:
                        log(f"JSON parse error at char {je.pos}: {je.msg}")
                        # Show the problem area for diagnosis
                        start = max(0, je.pos - 80)
                        end = min(len(raw_json), je.pos + 80)
                        log(f"Context around error: ...{raw_json[start:end]}...")

                        repaired = _repair_json(raw_json)
                        try:
                            catalysts = json.loads(repaired)
                            log(f"Forward catalysts found after repair: {len(catalysts)}")
                            return catalysts
                        except Exception as je2:
                            log(f"JSON repair failed: {je2} — extracting partial events")
                            return _extract_partial_catalysts(raw_json)

        return []

    except Exception as e:
        log(f"Forward catalyst search error: {e}")
        return []


def _repair_json(raw_json: str) -> str:
    """
    Repair common JSON issues from LLM generation:
    - Trailing commas
    - Smart/curly quotes
    - Unescaped inner quotes within string values
    """
    text = raw_json

    # Normalize smart quotes to straight quotes
    text = text.replace(chr(8220), '"').replace(chr(8221), '"')
    text = text.replace(chr(8216), "'").replace(chr(8217), "'")

    # Remove trailing commas before ] or }
    text = re.sub(r",(\s*[\]\}])", r"\1", text)

    # Fix unescaped inner quotes: find "key": "value with "inner" quotes here"
    # and escape the inner quote pairs. Matches a field value that contains
    # an extra quote-word-quote pattern before the closing quote+comma/brace.
    def fix_field(match):
        key = match.group(1)
        value = match.group(2)
        # Escape any double quotes inside the value that aren't already escaped
        fixed_value = re.sub(r'(?<!\\\\)"', '\\\\"', value)
        return f'"{key}": "{fixed_value}"'

    # This pattern matches "key": "....possibly with inner unescaped quotes...." followed by , or }
    text = re.sub(
        r'"(\w+)":\s*"((?:[^"\\]|\\.)*?(?:"(?:[^"\\]|\\.)*?)*?)"(?=\s*[,}])',
        lambda m: f'"{m.group(1)}": "{m.group(2).replace(chr(34), "")}"',
        text
    )

    return text


def _extract_partial_catalysts(raw_text: str) -> list:
    """
    Fallback: extract individual catalyst objects even if the full
    array has a syntax error. Parses object-by-object.
    """
    import json
    events = []
    # Find individual {...} objects
    depth = 0
    start = None
    for i, ch in enumerate(raw_text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                obj_text = raw_text[start:i+1]
                try:
                    obj = json.loads(obj_text)
                    events.append(obj)
                except Exception:
                    pass
                start = None
    log(f"Partial extraction recovered {len(events)} catalysts")
    return events


def fetch_complete_news_package() -> dict:
    """
    Master function — builds the complete news package for the morning briefing.
    Returns: {recent_news, critical_events, forward_catalysts}
    """
    log("=== Building complete news package ===")

    # Step 1: RSS feeds (Yahoo Finance + CNBC)
    rss_news = fetch_rss_news(hours_back=20)

    # Step 2: REMOVED — critical events web search merged into forward_catalysts
    # to save 1 Claude + web search call (~$0.30-0.50 per run).
    # Forward catalysts already searches for the same type of events.
    combined = rss_news

    # Step 3: Filter for relevance
    relevant = filter_relevant_news(combined)

    # Step 4: Deduplicate and summarize
    deduped = deduplicate_and_summarize(relevant)

    # Step 5: Forward-looking catalysts (separate category)
    forward_catalysts = fetch_forward_catalysts()

    log(f"News package complete: {len(deduped)} recent stories | {len(forward_catalysts)} forward catalysts")

    return {
        "recent_news": deduped,
        "forward_catalysts": forward_catalysts,
    }


def fetch_ticker_news(ticker: str, days: int = 1) -> list:
    """
    Fetch news specific to one ticker for afternoon position review.
    Uses Yahoo Finance RSS filtered by ticker mention, plus targeted web search.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    eastern = pytz.timezone("America/New_York")
    today_str = datetime.now(eastern).strftime("%B %d, %Y")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": f"""Search Yahoo Finance and CNBC for news specifically about {ticker} stock from today, {today_str}, and yesterday after market close.

Return ONLY a JSON array, nothing else, no markdown fences, no trailing commas:
[
  {{"headline": "...", "source": "...", "datetime": "{today_str}", "summary": "1-2 sentences"}}
]

If no ticker-specific news exists, return an empty array: []"""
            }]
        )

        for block in response.content:
            if hasattr(block, "text"):
                text = block.text.strip()
                match = re.search(r"\[.*\]", text, re.DOTALL)
                if match:
                    import json
                    try:
                        items = json.loads(match.group())
                        return items
                    except Exception:
                        return _extract_partial_catalysts(match.group())

        return []

    except Exception as e:
        log(f"Ticker news error for {ticker}: {e}")
        return []
