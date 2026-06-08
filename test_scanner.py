from data.fetch_macro import fetch_macro_data
from data.fetch_prices import load_price_cache
from data.fetch_fundamentals import fetch_fundamentals_batch
from signals.breadth import calculate_breadth
from signals.relative_strength import calculate_relative_strength, get_rs_qualified
from signals.trend_filter import apply_trend_filter
from engine.regime import determine_regime
from engine.scanner import run_full_scan

print("=== Full Pipeline Test ===\n")

# Macro + regime
macro = fetch_macro_data()
prices = load_price_cache()
breadth = calculate_breadth(prices)
macro["breadth_pct"] = breadth
regime = determine_regime(macro)

print(f"Regime: {regime['label']} ({regime['confidence']})")

# Get technically qualified tickers for fundamentals fetch
rs_scores = calculate_relative_strength(prices)
rs_qualified = get_rs_qualified(rs_scores)
trend_qualified = apply_trend_filter(prices, rs_qualified)

print(f"Technically qualified: {len(trend_qualified)} tickers")
print("Fetching fundamentals (~3 minutes)...\n")

fundamentals = fetch_fundamentals_batch(trend_qualified)

# Run full scan
results = run_full_scan(prices, fundamentals, regime)
stats = results["scan_stats"]

print(f"\n=== SCAN RESULTS ===")
print(f"Universe:          {stats['universe_size']} tickers")
print(f"RS qualified:      {stats['rs_qualified']}")
print(f"Trend qualified:   {stats['trend_qualified']}")
print(f"Earnings qualify:  {stats['earnings_qualified']}")
print(f"Strong candidates: {stats['strong_count']}")
print(f"Developing:        {stats['developing_count']}")

print(f"\n=== STRONG CANDIDATES ===")
for c in results["strong"]:
    catalyst_str = (f"earnings in {c['days_to_catalyst']}d"
                   if c["has_catalyst"] else "no catalyst")
    print(f"  {c['ticker']}: score {c['composite_score']:.3f} | "
          f"RS {c['rs_score']:+.1f}pp | "
          f"{c['beat_streak']} beats | "
          f"{catalyst_str}")

print(f"\n=== DEVELOPING CANDIDATES ===")
for c in results["developing"][:10]:
    catalyst_str = (f"earnings in {c['days_to_catalyst']}d"
                   if c["has_catalyst"] else "no catalyst")
    print(f"  {c['ticker']}: score {c['composite_score']:.3f} | "
          f"RS {c['rs_score']:+.1f}pp | "
          f"{c['beat_streak']} beats | "
          f"{catalyst_str}")
