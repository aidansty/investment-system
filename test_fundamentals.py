from data.fetch_fundamentals import fetch_fundamentals_batch

test_tickers = ["AAPL", "NVDA", "MSFT", "AMD", "META"]

print("=== Testing Fundamentals Fetch ===\n")
results = fetch_fundamentals_batch(test_tickers)

for ticker, data in results.items():
    earnings = data["earnings"]
    calendar = data["calendar"]
    status = data["status"]

    print(f"{ticker} [{status}]:")

    if earnings:
        beats = sum(1 for q in earnings if q["beat"])
        print(f"  Earnings: {len(earnings)} quarters | "
              f"{beats} beats | {len(earnings)-beats} misses")
        for q in earnings[:3]:
            beat_str = "BEAT" if q["beat"] else "MISS"
            print(f"    {q['period']}: actual {q['actual']} vs "
                  f"est {q['estimate']} [{beat_str}] "
                  f"({q['surprise_pct']:+.1f}%)")
    else:
        print(f"  No earnings history")

    if calendar:
        next_date = calendar[0].get("date", "unknown")
        print(f"  Next earnings: {next_date}")
    else:
        print(f"  No upcoming earnings in 60 days")
    print()
