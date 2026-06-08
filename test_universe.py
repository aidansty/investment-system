import yfinance as yf
import warnings
import time
warnings.filterwarnings('ignore')

from config.universe import get_universe, get_universe_metadata

universe = get_universe()
meta = get_universe_metadata()
print(f"Universe v{meta['version']} — testing {meta['total']} tickers...")
print("This will take 3-4 minutes.\n")

passed = []
failed = []

# Batch download all at once — faster and more reliable than individual calls
batch = " ".join(universe)
data = yf.download(batch, period="5d", auto_adjust=True, progress=False, threads=True)

if hasattr(data['Close'], 'columns'):
    returned = set(data['Close'].columns.tolist())
    for ticker in universe:
        if ticker in returned and not data['Close'][ticker].isna().all():
            passed.append(ticker)
        else:
            failed.append(ticker)
else:
    print("Unexpected data structure returned")

pct = len(passed) / len(universe) * 100
print(f"Passed: {len(passed)}/{len(universe)} ({pct:.1f}%)")

if failed:
    print(f"\nFailed ({len(failed)}):")
    for t in sorted(failed):
        print(f"  {t}")
else:
    print("\nAll tickers returned clean data.")

if pct >= 95:
    print(f"\nPASS — Universe meets 95% threshold. Safe to freeze.")
else:
    print(f"\nFAIL — Below 95% threshold. Review failed tickers before freezing.")
