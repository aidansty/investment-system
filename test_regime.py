from data.fetch_macro import fetch_macro_data
from data.fetch_prices import load_price_cache
from signals.breadth import calculate_breadth
from engine.regime import determine_regime

print("=== Testing Complete Regime Engine ===\n")

# Fetch macro data (now includes VIX 5d history)
macro = fetch_macro_data()
if not macro:
    print("FAILED: macro data")
    exit()

# Load price cache and calculate breadth
prices = load_price_cache()
if prices:
    breadth = calculate_breadth(prices)
    macro["breadth_pct"] = breadth
else:
    print("WARNING: No price cache — breadth unavailable")

# Determine regime with all five conditions
regime = determine_regime(macro)

print(f"\nREGIME: {regime['label']} ({regime['confidence']} confidence)")
print(f"Degraded: {regime['degraded']}")
print(f"Bullish points: {regime['bullish_points']}/5")
print(f"Bearish points: {regime['bearish_points']}/5")
print(f"Max positions: {regime['max_positions']}")
print(f"Min cash: {regime['min_cash_pct']:.0%}")

print(f"\nCondition breakdown:")
for name, data in regime["conditions"].items():
    status = "BULL" if data["bullish"] else ("BEAR" if data["bearish"] else "NEUT")
    print(f"  [{status}] {name}: {data['value']}")
