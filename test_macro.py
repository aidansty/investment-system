from data.fetch_macro import fetch_macro_data

macro = fetch_macro_data()
if macro:
    print("SUCCESS")
    print(f'SPY close: {macro["spy_close"]:.2f}')
    print(f'50d SMA:   {macro["spy_sma_50"]:.2f}')
    print(f'200d SMA:  {macro["spy_sma_200"]:.2f}')
    print(f'VIX:       {macro["vix"]:.1f}')
    print(f'SPY above 50d SMA:  {macro["spy_close"] > macro["spy_sma_50"]}')
    print(f'50d above 200d SMA: {macro["spy_sma_50"] > macro["spy_sma_200"]}')
else:
    print("FAILED")
