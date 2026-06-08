from data.fetch_news import fetch_market_news

print("=== Testing News Fetch ===\n")
headlines = fetch_market_news()

print(f"Headlines fetched: {len(headlines)}\n")
for i, h in enumerate(headlines, 1):
    print(f"{i:2}. {h}")
