from data.fetch_prices import fetch_all_prices, load_price_cache, fetch_current_prices

test_tickers = ["AAPL","MSFT","NVDA","GOOGL","META","AMZN","TSLA","JPM","V","SPY"]

print("=== Testing fetch_all_prices ===")
prices = fetch_all_prices(test_tickers)

if prices:
    print(f"\nResults:")
    for ticker, data in prices.items():
        print(f"  {ticker}: {len(data)} days | latest: ${data[-1]:.2f}")

    print("\n=== Testing load_price_cache ===")
    cached = load_price_cache()
    print(f"Cache contains: {len(cached)} tickers")

    print("\n=== Testing fetch_current_prices ===")
    current = fetch_current_prices(["AAPL","NVDA","SPY"])
    for ticker, price in current.items():
        print(f"  {ticker}: ${price:.2f}")

    print("\nAll tests passed.")
else:
    print("FAILED")
