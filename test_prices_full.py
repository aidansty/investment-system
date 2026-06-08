from config.universe import get_universe, get_universe_metadata
from data.fetch_prices import fetch_all_prices, load_price_cache

meta = get_universe_metadata()
universe = get_universe()
print(f"Running full universe download: {meta['total']} tickers")
print("This will take 5-8 minutes...\n")

prices = fetch_all_prices(universe)

if prices:
    print(f"\nSUCCESS")
    print(f"Tickers with data: {len(prices)}")
    coverage = len(prices) / len(universe) * 100
    print(f"Coverage: {coverage:.1f}%")

    # Verify data depth
    days_list = [len(v) for v in prices.values()]
    print(f"Avg days per ticker: {sum(days_list)/len(days_list):.0f}")
    print(f"Min days: {min(days_list)}")
    print(f"Max days: {max(days_list)}")

    # Reload from cache to verify persistence
    print("\n=== Verifying cache reload ===")
    cached = load_price_cache()
    print(f"Cache reload: {len(cached)} tickers")
    print("\nFull universe price fetch complete.")
else:
    print("\nFAILED - coverage below 90% threshold")
