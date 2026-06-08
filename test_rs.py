from data.fetch_prices import load_price_cache
from signals.relative_strength import calculate_relative_strength, get_rs_qualified

print("=== Testing Relative Strength ===")
prices = load_price_cache()

if not prices:
    print("FAILED: No price cache")
    exit()

rs_scores = calculate_relative_strength(prices)

if rs_scores:
    qualified = get_rs_qualified(rs_scores)

    print(f"\nTop 10 strongest RS stocks:")
    for ticker in qualified[:10]:
        d = rs_scores[ticker]
        print(f"  {ticker}: RS {d['rs_score']:+.1f}pp | "
              f"stock {d['ticker_return']:+.1f}% | "
              f"SPY {d['spy_return']:+.1f}%")

    print(f"\nBottom 5 RS stocks (weakest but still qualifying):")
    for ticker in qualified[-5:]:
        d = rs_scores[ticker]
        print(f"  {ticker}: RS {d['rs_score']:+.1f}pp | "
              f"stock {d['ticker_return']:+.1f}%")

    print(f"\nTotal scored: {len(rs_scores)}")
    print(f"Outperforming SPY: {len(qualified)}")
    print(f"Underperforming SPY: {len(rs_scores) - len(qualified)}")
    print(f"SPY 63d return: {rs_scores[qualified[0]]['spy_return']:+.1f}%")
else:
    print("FAILED")
