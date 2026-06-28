"""
V4 Backtester — Validates the rules engine against historical data.
Run: python3 -m v4.intelligence.backtest --start 2020-01-01 --end 2025-01-01
"""
import argparse, json, os, sys
from datetime import datetime, timedelta

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Install: pip install yfinance pandas")
    sys.exit(1)

INDUSTRY_ETFS = ["SOXX","IGV","CIBR","BOTZ","SKYY","FIVG","IBB","IHI","IHF","XPH","ITA","ICLN","XOP","XLF","KRE","XLY","ROBO","IYT","XHB","VNQ","PBW"]
BENCHMARK = "SPY"
LOOKBACK_DAYS = 63
TRANSACTION_COST = 0.001

def fetch_history(tickers, start, end):
    print(f"Fetching {len(tickers)} tickers ({start} to {end})...")
    data = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    return data["Close"] if "Close" in data.columns else data

def momentum_scores(prices, date_idx):
    scores = {}
    start_idx = max(0, date_idx - LOOKBACK_DAYS)
    spy_r = (prices[BENCHMARK].iloc[date_idx] - prices[BENCHMARK].iloc[start_idx]) / prices[BENCHMARK].iloc[start_idx]
    for etf in [c for c in prices.columns if c != BENCHMARK]:
        try:
            s, e = prices[etf].iloc[start_idx], prices[etf].iloc[date_idx]
            if s > 0 and not pd.isna(s) and not pd.isna(e):
                scores[etf] = round(((e-s)/s - spy_r)*100, 2)
        except: pass
    return scores

def run_backtest(start, end, capital=10000.0):
    print(f"\n{'='*55}\nV4 BACKTEST: {start} to {end}\nCapital: ${capital:,.0f}\n{'='*55}")
    prices = fetch_history(INDUSTRY_ETFS + [BENCHMARK], start, end)
    if prices.empty: print("No data"); return {}

    spy_start = prices[BENCHMARK].iloc[LOOKBACK_DAYS]
    strategy_val = capital
    holdings = []
    values = []
    trades = 0

    idx = LOOKBACK_DAYS
    while idx < len(prices):
        scores = momentum_scores(prices, idx)
        top = sorted([k for k,v in scores.items() if v > 0], key=lambda k: scores[k], reverse=True)[:3]
        new_set = set(top)
        old_set = {h["etf"] for h in holdings}

        if holdings:
            strategy_val = sum(h["shares"] * prices[h["etf"]].iloc[idx] for h in holdings if h["etf"] in prices.columns and not pd.isna(prices[h["etf"]].iloc[idx]))

        if new_set != old_set and top:
            n_trades = len(new_set.symmetric_difference(old_set))
            strategy_val *= (1 - TRANSACTION_COST * n_trades * 0.5)
            alloc = strategy_val / len(top)
            holdings = []
            for etf in top:
                price = prices[etf].iloc[idx]
                if not pd.isna(price) and price > 0:
                    holdings.append({"etf": etf, "shares": alloc/price})
            trades += 1

        spy_val = capital * (prices[BENCHMARK].iloc[idx] / spy_start)
        values.append({"date": str(prices.index[idx].date()), "strategy": round(strategy_val,2), "spy": round(spy_val,2)})
        idx += 5  # weekly

    if not values: print("No results"); return {}

    final_s = values[-1]["strategy"]
    final_spy = values[-1]["spy"]
    s_ret = (final_s - capital) / capital * 100
    spy_ret = (final_spy - capital) / capital * 100
    alpha = s_ret - spy_ret

    peak = capital
    max_dd = 0
    for v in values:
        if v["strategy"] > peak: peak = v["strategy"]
        dd = (v["strategy"] - peak) / peak * 100
        if dd < max_dd: max_dd = dd

    years = (datetime.strptime(end,"%Y-%m-%d") - datetime.strptime(start,"%Y-%m-%d")).days / 365.25
    s_cagr = ((final_s/capital)**(1/years)-1)*100 if years > 0 else 0
    spy_cagr = ((final_spy/capital)**(1/years)-1)*100 if years > 0 else 0

    results = {"period": f"{start} to {end}", "years": round(years,1), "strategy_return": round(s_ret,2), "spy_return": round(spy_ret,2), "alpha": round(alpha,2), "strategy_cagr": round(s_cagr,2), "spy_cagr": round(spy_cagr,2), "max_drawdown": round(max_dd,2), "final_strategy": round(final_s,2), "final_spy": round(final_spy,2), "trades": trades}

    print(f"\nRESULTS\n{'='*55}")
    print(f"Strategy: {s_ret:+.1f}% (CAGR {s_cagr:+.1f}%)")
    print(f"SPY:      {spy_ret:+.1f}% (CAGR {spy_cagr:+.1f}%)")
    print(f"Alpha:    {alpha:+.1f}%")
    print(f"Max DD:   {max_dd:.1f}%")
    print(f"Trades:   {trades}")
    print(f"{'✅ BEAT SPY' if alpha > 0 else '❌ UNDERPERFORMED'} by {abs(alpha):.1f}%\n")

    os.makedirs("data/backtest", exist_ok=True)
    with open(f"data/backtest/result_{start[:4]}_{end[:4]}.json","w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved to data/backtest/result_{start[:4]}_{end[:4]}.json")
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2025-01-01")
    parser.add_argument("--capital", type=float, default=10000.0)
    args = parser.parse_args()
    run_backtest(args.start, args.end, args.capital)
