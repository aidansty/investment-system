#!/usr/bin/env python3
"""
Full 5-Phase Backtest — Tests the catalyst-driven investment system
against historical data (2024-2025).
"""
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta
import json, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from v4.config.settings import INDUSTRY_STOCK_LEADERS

BACKTEST_START = "2024-01-01"
BACKTEST_END = "2025-12-31"
INITIAL_CAPITAL = 6000
POSITION_SIZE_PCT = 0.15
REDUCED_SIZE_PCT = 0.10
MAX_HOLD_DAYS = 25
TRAILING_STOP_ACTIVATE = 8
TRAILING_STOP_FLOOR_1 = 0
TRAILING_STOP_ACTIVATE_2 = 15
TRAILING_STOP_FLOOR_2 = 5
CHECKPOINT_STOP = -8
MIN_MOMENTUM_EXCESS = 3
PHASE3_MOMENTUM_EXCESS = 5
PHASE4_DAY1_RETURN = 4.0
PHASE4_RVOL_MEGA = 2.5
PHASE4_RVOL_MID = 1.5
MEGA_CAP_VOL_THRESHOLD = 10_000_000

print("=" * 60)
print("INVESTMENT SYSTEM — FULL 5-PHASE BACKTEST")
print(f"Period: {BACKTEST_START} to {BACKTEST_END}")
print(f"Initial capital: ${INITIAL_CAPITAL:,}")
print("=" * 60)
print()

print("Downloading historical data (2-3 minutes)...")
all_tickers = set()
for ind, tickers in INDUSTRY_STOCK_LEADERS.items():
    all_tickers.update(tickers)
all_tickers.add("SPY")
all_tickers = sorted(all_tickers)
print(f"  {len(all_tickers)} tickers...")

batch_size = 50
all_close = {}
all_volume = {}

for i in range(0, len(all_tickers), batch_size):
    batch = all_tickers[i:i+batch_size]
    try:
        data = yf.download(batch, start=BACKTEST_START, end=BACKTEST_END, progress=False, auto_adjust=True)
        if data.empty: continue
        close = data["Close"] if "Close" in data.columns else data
        volume = data["Volume"] if "Volume" in data.columns else None
        for ticker in batch:
            try:
                if len(batch) > 1:
                    if ticker in close.columns:
                        s = close[ticker].dropna()
                        if len(s) > 60:
                            all_close[ticker] = s
                        if volume is not None and ticker in volume.columns:
                            all_volume[ticker] = volume[ticker].dropna()
                else:
                    s = close.dropna()
                    if len(s) > 60:
                        all_close[ticker] = s
                    if volume is not None:
                        all_volume[ticker] = volume.dropna()
            except: continue
    except Exception as e:
        print(f"  Batch error: {e}")
    pct = min(100, (i + batch_size) / len(all_tickers) * 100)
    print(f"  {pct:.0f}% ({len(all_close)} tickers)...")

print(f"  Loaded: {len(all_close)} tickers")
if "SPY" not in all_close:
    print("ERROR: SPY not available"); sys.exit(1)
spy_close = all_close["SPY"]

print("Identifying earnings dates...")
earnings_dates = {}
for ticker, vol_series in all_volume.items():
    if ticker == "SPY" or len(vol_series) < 60: continue
    dates = []
    for i in range(50, len(vol_series)):
        avg_50 = vol_series.iloc[i-50:i].mean()
        if avg_50 > 0 and vol_series.iloc[i] > avg_50 * 3:
            dates.append(vol_series.index[i])
    filtered = []
    for d in dates:
        if not filtered or (d - filtered[-1]).days > 60:
            filtered.append(d)
    earnings_dates[ticker] = filtered
print(f"  Found {sum(len(v) for v in earnings_dates.values())} earnings dates")
print()

print("Running simulation...")
capital = INITIAL_CAPITAL
cash = INITIAL_CAPITAL
positions = {}
trade_log = []
daily_values = []
wash_sale_blocklist = {}

trading_days = spy_close.index[63:]
for day_idx, today in enumerate(trading_days):
    portfolio_value = cash
    for ticker, pos in positions.items():
        if ticker in all_close and today in all_close[ticker].index:
            portfolio_value += all_close[ticker].loc[today] * pos["shares"]
    daily_values.append({"date": today, "value": portfolio_value})

    to_exit = []
    for ticker, pos in list(positions.items()):
        if ticker not in all_close or today not in all_close[ticker].index: continue
        current = all_close[ticker].loc[today]
        pct_change = (current - pos["entry_price"]) / pos["entry_price"] * 100
        days_held = (today - pos["entry_date"]).days
        if pct_change > pos.get("peak_pct", 0): pos["peak_pct"] = pct_change
        exit_reason = None

        if pos["phase"] == "phase1" and pos.get("catalyst_date"):
            if 0 <= (pos["catalyst_date"] - today).days <= 1:
                exit_reason = f"Phase1 pre-earnings exit ({pct_change:+.1f}%)"

        peak = pos.get("peak_pct", 0)
        if peak >= TRAILING_STOP_ACTIVATE:
            floor = TRAILING_STOP_FLOOR_2 if peak >= TRAILING_STOP_ACTIVATE_2 else TRAILING_STOP_FLOOR_1
            if pct_change <= floor:
                exit_reason = f"Trailing stop: peak +{peak:.1f}% → +{pct_change:.1f}%"

        if pct_change <= CHECKPOINT_STOP:
            exit_reason = f"Checkpoint stop ({pct_change:.1f}%)"
        if days_held >= MAX_HOLD_DAYS and pct_change < 3:
            exit_reason = f"Max hold {days_held}d ({pct_change:+.1f}%)"
        if pos["phase"] == "phase4" and days_held >= 5 and pct_change < 2:
            exit_reason = f"Phase4 drift stalled ({pct_change:+.1f}%)"

        if exit_reason: to_exit.append((ticker, exit_reason, pct_change))

    for ticker, reason, pct in to_exit:
        pos = positions[ticker]
        current = all_close[ticker].loc[today]
        proceeds = current * pos["shares"]
        cash += proceeds
        trade_log.append({"ticker": ticker, "phase": pos["phase"], "entry_date": pos["entry_date"].strftime("%Y-%m-%d"), "exit_date": today.strftime("%Y-%m-%d"), "entry_price": round(pos["entry_price"], 2), "exit_price": round(current, 2), "pct_return": round(pct, 2), "profit": round(proceeds - pos["entry_price"] * pos["shares"], 2), "reason": reason, "days_held": (today - pos["entry_date"]).days})
        if pct < 0: wash_sale_blocklist[ticker] = today
        del positions[ticker]

    if day_idx % 5 != 0: continue
    if len(positions) >= 5 or cash < portfolio_value * POSITION_SIZE_PCT * 0.5: continue

    spy_today_idx = list(spy_close.index).index(today) if today in spy_close.index else -1
    if spy_today_idx < 21: continue
    spy_21d = (spy_close.iloc[spy_today_idx] / spy_close.iloc[spy_today_idx - 21] - 1) * 100

    candidates = []
    for ticker in all_close:
        if ticker == "SPY" or ticker in positions: continue
        if ticker in wash_sale_blocklist and (today - wash_sale_blocklist[ticker]).days <= 30: continue
        if today not in all_close[ticker].index: continue
        cs = all_close[ticker]
        ti = list(cs.index).index(today)
        if ti < 63: continue
        price = cs.iloc[ti]
        if cs.iloc[ti-21] <= 0 or cs.iloc[ti-63] <= 0: continue
        excess_21d = (price / cs.iloc[ti-21] - 1) * 100 - spy_21d

        vol_s = all_volume.get(ticker)
        avg_vol, last_vol, rvol = 0, 0, 0
        if vol_s is not None and today in vol_s.index:
            vi = list(vol_s.index).index(today)
            if vi >= 50:
                avg_vol = vol_s.iloc[vi-50:vi].mean()
                last_vol = vol_s.iloc[vi]
                rvol = last_vol / avg_vol if avg_vol > 0 else 0
        if 0 < avg_vol < 500_000: continue
        is_mega = avg_vol > MEGA_CAP_VOL_THRESHOLD
        day1_ret = (price / cs.iloc[ti-1] - 1) * 100 if cs.iloc[ti-1] > 0 else 0

        upcoming_earn = None
        if ticker in earnings_dates:
            for ed in earnings_dates[ticker]:
                if 1 <= (ed - today).days <= 30:
                    upcoming_earn = ed; break

        if excess_21d > MIN_MOMENTUM_EXCESS and upcoming_earn:
            candidates.append({"ticker": ticker, "phase": "phase1", "score": excess_21d + 10, "catalyst_date": upcoming_earn, "size_pct": POSITION_SIZE_PCT})
        if excess_21d > MIN_MOMENTUM_EXCESS and rvol > 1.8 and day1_ret > 2 and not upcoming_earn:
            candidates.append({"ticker": ticker, "phase": "phase2", "score": excess_21d + rvol * 3, "catalyst_date": None, "size_pct": POSITION_SIZE_PCT})
        if excess_21d > PHASE3_MOMENTUM_EXCESS and rvol > 1.5 and day1_ret > 1.5:
            if not any(c["ticker"] == ticker for c in candidates):
                candidates.append({"ticker": ticker, "phase": "phase3", "score": excess_21d + day1_ret * 2, "catalyst_date": None, "size_pct": POSITION_SIZE_PCT})
        req_rvol = PHASE4_RVOL_MEGA if is_mega else PHASE4_RVOL_MID
        if day1_ret >= PHASE4_DAY1_RETURN and rvol >= req_rvol:
            if not any(c["ticker"] == ticker for c in candidates):
                candidates.append({"ticker": ticker, "phase": "phase4", "score": day1_ret * 3 + rvol * 2 + excess_21d, "catalyst_date": None, "size_pct": POSITION_SIZE_PCT})
        if rvol > 3.0 and day1_ret > 3 and excess_21d < MIN_MOMENTUM_EXCESS:
            if not any(c["ticker"] == ticker for c in candidates):
                candidates.append({"ticker": ticker, "phase": "phase5", "score": rvol * 2 + day1_ret, "catalyst_date": None, "size_pct": REDUCED_SIZE_PCT})

    candidates.sort(key=lambda x: -x["score"])
    for c in candidates[:2]:
        ticker = c["ticker"]
        if ticker in positions or cash < portfolio_value * c["size_pct"] * 0.5: continue
        price = all_close[ticker].loc[today]
        alloc = portfolio_value * c["size_pct"]
        shares = alloc / price if price > 0 else 0
        if shares <= 0: continue
        cash -= alloc
        positions[ticker] = {"entry_price": price, "entry_date": today, "shares": shares, "phase": c["phase"], "catalyst_date": c.get("catalyst_date"), "peak_pct": 0}

for ticker in list(positions.keys()):
    final = trading_days[-1]
    if ticker in all_close and final in all_close[ticker].index:
        current = all_close[ticker].loc[final]
        pos = positions[ticker]
        pct = (current - pos["entry_price"]) / pos["entry_price"] * 100
        cash += current * pos["shares"]
        trade_log.append({"ticker": ticker, "phase": pos["phase"], "entry_date": pos["entry_date"].strftime("%Y-%m-%d"), "exit_date": final.strftime("%Y-%m-%d"), "entry_price": round(pos["entry_price"], 2), "exit_price": round(current, 2), "pct_return": round(pct, 2), "profit": round(current * pos["shares"] - pos["entry_price"] * pos["shares"], 2), "reason": "End of backtest", "days_held": (final - pos["entry_date"]).days})

print()
print("=" * 60)
print("BACKTEST RESULTS")
print("=" * 60)

final_value = daily_values[-1]["value"] if daily_values else INITIAL_CAPITAL
total_return = (final_value - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
spy_start = spy_close.iloc[63]
spy_end = spy_close.iloc[-1]
spy_return = (spy_end - spy_start) / spy_start * 100

print(f"\nPortfolio return: {total_return:+.1f}% (${INITIAL_CAPITAL:,} → ${final_value:,.0f})")
print(f"SPY return:       {spy_return:+.1f}%")
print(f"Alpha vs SPY:     {total_return - spy_return:+.1f}pp")

if trade_log:
    wins = [t for t in trade_log if t["pct_return"] > 0]
    losses = [t for t in trade_log if t["pct_return"] <= 0]
    print(f"\nTotal trades:     {len(trade_log)}")
    print(f"Win rate:         {len(wins)/len(trade_log)*100:.1f}% ({len(wins)}W / {len(losses)}L)")
    print(f"Avg winner:       +{np.mean([t['pct_return'] for t in wins]):.1f}%" if wins else "")
    print(f"Avg loser:        {np.mean([t['pct_return'] for t in losses]):.1f}%" if losses else "")
    print(f"Avg hold:         {np.mean([t['days_held'] for t in trade_log]):.0f} days")
    print(f"Total profit:     ${sum(t['profit'] for t in trade_log):+,.0f}")

    print("\nRESULTS BY PHASE:")
    for phase in ["phase1", "phase2", "phase3", "phase4", "phase5"]:
        pt = [t for t in trade_log if t["phase"] == phase]
        if pt:
            pw = [t for t in pt if t["pct_return"] > 0]
            label = {"phase1": "Pre-earnings run-up", "phase2": "Momentum + catalyst", "phase3": "Momentum + bullish news", "phase4": "Post-catalyst RVOL", "phase5": "Strong catalyst (reduced)"}[phase]
            print(f"  {label}: {len(pt)} trades | WR {len(pw)/len(pt)*100:.0f}% | Avg {np.mean([t['pct_return'] for t in pt]):+.1f}% | ${sum(t['profit'] for t in pt):+,.0f}")

    print("\nTOP 10 TRADES:")
    for t in sorted(trade_log, key=lambda x: -x["pct_return"])[:10]:
        print(f"  {t['ticker']} ({t['phase']}): {t['pct_return']:+.1f}% in {t['days_held']}d | ${t['profit']:+,.0f} | {t['entry_date']}")

    print("\nWORST 5 TRADES:")
    for t in sorted(trade_log, key=lambda x: x["pct_return"])[:5]:
        print(f"  {t['ticker']} ({t['phase']}): {t['pct_return']:+.1f}% in {t['days_held']}d | ${t['profit']:+,.0f} | {t['reason']}")

    print("\nEXIT REASONS:")
    reasons = {}
    for t in trade_log:
        r = t["reason"].split(":")[0] if ":" in t["reason"] else t["reason"]
        reasons[r] = reasons.get(r, 0) + 1
    for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {r}: {c}")

os.makedirs("data", exist_ok=True)
with open("data/backtest_results.json", "w") as f:
    json.dump({"period": f"{BACKTEST_START} to {BACKTEST_END}", "initial_capital": INITIAL_CAPITAL, "final_value": round(final_value, 2), "portfolio_return": round(total_return, 2), "spy_return": round(spy_return, 2), "alpha": round(total_return - spy_return, 2), "trades": trade_log}, f, indent=2, default=str)
print("\nFull results saved to data/backtest_results.json")
