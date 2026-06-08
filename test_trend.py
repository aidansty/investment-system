from data.fetch_prices import load_price_cache
from signals.relative_strength import calculate_relative_strength, get_rs_qualified
from signals.trend_filter import apply_trend_filter, passes_trend_filter

print("=== Testing Trend Filter ===")
prices = load_price_cache()

rs_scores = calculate_relative_strength(prices)
rs_qualified = get_rs_qualified(rs_scores)

print(f"\nRS qualified: {len(rs_qualified)} tickers")

trend_qualified = apply_trend_filter(prices, rs_qualified)

print(f"After trend filter: {len(trend_qualified)} tickers")
print(f"Eliminated by trend: {len(rs_qualified) - len(trend_qualified)}")

print(f"\nTop 10 after both filters:")
for ticker in trend_qualified[:10]:
    d = rs_scores[ticker]
    price = prices[ticker][-1]
    sma50 = sum(prices[ticker][-50:]) / 50
    pct_above = ((price / sma50) - 1) * 100
    print(f"  {ticker}: RS {d['rs_score']:+.1f}pp | "
          f"${price:.2f} vs 50d SMA ${sma50:.2f} ({pct_above:+.1f}%)")
