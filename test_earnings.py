from data.fetch_prices import load_price_cache
from data.fetch_fundamentals import fetch_fundamentals_batch
from signals.relative_strength import calculate_relative_strength, get_rs_qualified
from signals.trend_filter import apply_trend_filter
from signals.earnings_proxy import apply_earnings_filter, get_beat_streak

print("=== Testing Earnings Proxy Signal ===\n")

prices = load_price_cache()
rs_scores = calculate_relative_strength(prices)
rs_qualified = get_rs_qualified(rs_scores)
trend_qualified = apply_trend_filter(prices, rs_qualified)

print(f"After RS + trend filter: {len(trend_qualified)} tickers")
print("Fetching fundamentals (~3 minutes)...\n")

fundamentals = fetch_fundamentals_batch(trend_qualified)

passed, streak_data, diagnostics = apply_earnings_filter(
    fundamentals, trend_qualified
)

print(f"\nFinal candidates after all three filters: {len(passed)}")
print(f"\nTop 15 candidates:")
for ticker in passed[:15]:
    streak = streak_data.get(ticker, 0)
    rs = rs_scores[ticker]["rs_score"]
    print(f"  {ticker}: {streak} consecutive beats | RS {rs:+.1f}pp")

print(f"\nDiagnostics:")
print(f"  Passed:               {diagnostics['passed']}")
print(f"  Insufficient streak:  {diagnostics['insufficient_streak']}")
print(f"  No history:           {diagnostics['no_history']}")
print(f"  Fetch failed:         {diagnostics['fetch_failed']}")
print(f"  Missing from fetch:   {diagnostics['not_in_fundamentals']}")
print(f"\nStreak distribution:")
dist = diagnostics["streak_distribution"]
for k in [0, 1, 2, 3, 4, "5+"]:
    print(f"  {k} beats: {dist[k]} tickers")
