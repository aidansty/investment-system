import argparse, json, os, sys
from datetime import datetime
try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print('pip install yfinance pandas')
    sys.exit(1)

# ── Strategy parameters ──────────────────────────────────────────────────────
# Three core principles:
# 1. High conviction only (score >= 75 with catalyst)
# 2. Size by conviction (15-25% on strongest, 8-12% on medium)
# 3. Hold until thesis breaks — not on dips, not on calendar

INDUSTRY_MAP = {
    'Semiconductors': {'etf': 'SOXX', 'stocks': ['NVDA','AMD','MU','AVGO','TSM']},
    'Software':       {'etf': 'IGV',  'stocks': ['MSFT','CRM','NOW','ADBE','ORCL']},
    'Cybersecurity':  {'etf': 'CIBR', 'stocks': ['CRWD','PANW','ZS','FTNT','S']},
    'AI_Infra':       {'etf': 'BOTZ', 'stocks': ['NVDA','MSFT','GOOGL','AMZN','META']},
    'Cloud':          {'etf': 'SKYY', 'stocks': ['AMZN','MSFT','GOOGL','NET','SNOW']},
    'Defense':        {'etf': 'ITA',  'stocks': ['LMT','RTX','NOC','GD','HII']},
    'Biotech':        {'etf': 'IBB',  'stocks': ['AMGN','GILD','REGN','VRTX','MRNA']},
    'Financials':     {'etf': 'XLF',  'stocks': ['JPM','BAC','GS','MS','V']},
    'ConsDisc':       {'etf': 'XLY',  'stocks': ['AMZN','TSLA','HD','NKE','SBUX']},
    'Energy':         {'etf': 'XOP',  'stocks': ['XOM','CVX','COP','SLB','EOG']},
}

BENCHMARK         = 'SPY'
LOOKBACK          = 63    # 63-day momentum window
MIN_CONVICTION    = 75    # Higher threshold — only high conviction entries
HOLD_CONVICTION   = 40    # Exit only when thesis clearly broken (lower than before)
MAX_POS           = 4     # Up to 4 positions
MIN_HOLD_DAYS     = 21    # Minimum 21 days before any rotation check
THESIS_BREAK_DAYS = 10    # Must be below HOLD_CONVICTION for 10 days before exit
TRADE_COST        = 0.001 # 0.1% per trade
PORTFOLIO_FLOOR   = 0.125 # 12.5% max drawdown kill criteria

# Position sizing by conviction
def conviction_to_size(conv, n_positions, cash):
    if conv >= 88:
        pct = 0.25  # 25% of active sleeve
    elif conv >= 80:
        pct = 0.20  # 20%
    elif conv >= 75:
        pct = 0.15  # 15%
    else:
        pct = 0.10  # 10%
    return cash * pct

def excess_to_conviction(exc):
    if exc >= 25: return 95
    if exc >= 18: return 88
    if exc >= 12: return 82
    if exc >= 8:  return 77
    if exc >= 5:  return 72
    if exc >= 2:  return 65
    if exc >= 0:  return 55
    return max(0, int(40 + exc * 2))

def get_momentum_multi(prices, ticker, idx):
    # Combine 63-day sustained momentum with 21-day breakout detection
    conv_63, exc_63 = get_momentum(prices, ticker, idx, lookback=63)
    conv_21, exc_21 = get_momentum(prices, ticker, idx, lookback=21)
    # If both timeframes confirm momentum, boost conviction
    if exc_63 > 0 and exc_21 > 0:
        combined_exc = (exc_63 * 0.6) + (exc_21 * 0.4)
        return excess_to_conviction(combined_exc), round(combined_exc, 2)
    # If 21-day breakout is very strong but 63-day not yet confirmed
    elif exc_21 > 15 and exc_63 > -5:
        # Early breakout — return reduced conviction
        return max(75, int(excess_to_conviction(exc_21) * 0.85)), round(exc_21, 2)
    return conv_63, exc_63

def get_momentum(prices, ticker, idx, lookback=63):

    if ticker not in prices.columns: return 0, 0.0
    si = max(0, idx - lookback)
    try:
        sp_s = prices[BENCHMARK].iloc[si]
        sp_e = prices[BENCHMARK].iloc[idx]
        t_s  = prices[ticker].iloc[si]
        t_e  = prices[ticker].iloc[idx]
        if any(v != v or v <= 0 for v in [sp_s,sp_e,t_s,t_e]): return 0, 0.0
        exc = ((t_e-t_s)/t_s - (sp_e-sp_s)/sp_s) * 100
        return excess_to_conviction(exc), round(exc,2)
    except: return 0, 0.0

def scan_industries(prices, idx):
    out = []
    for name, d in INDUSTRY_MAP.items():
        conv, exc = get_momentum_multi(prices, d['etf'], idx)
        if conv >= MIN_CONVICTION:
            out.append({'industry':name,'etf':d['etf'],'etf_conv':conv,'exc':exc})
    return sorted(out, key=lambda x: x['etf_conv'], reverse=True)

def pick_best_security(prices, idx, ind_data):
    etf = ind_data['etf']
    best_t, best_c = etf, ind_data['etf_conv']
    for stk in INDUSTRY_MAP[ind_data['industry']]['stocks']:
        c, _ = get_momentum_multi(prices, stk, idx)
        if c > best_c + 5:
            best_t, best_c = stk, c
    return best_t, best_c

def port_value(holdings, prices, idx):
    val = 0.0
    for h in holdings:
        if h['ticker'] in prices.columns:
            p = prices[h['ticker']].iloc[idx]
            if p == p and p > 0:
                val += h['shares'] * p
    return val

def run_backtest(start, end, capital=10000.0):
    sep = '=' * 60
    print(sep)
    print('V4 CONVICTION-BASED BACKTEST  ' + start + ' to ' + end)
    print('Capital $' + str(int(capital)) + ' | MinConv=' + str(MIN_CONVICTION) + ' | HoldConv=' + str(HOLD_CONVICTION) + ' | MaxPos=' + str(MAX_POS))
    print('Size by conviction: 88+=25%, 80+=20%, 75+=15%')
    print('Hold until thesis breaks (' + str(THESIS_BREAK_DAYS) + ' days below ' + str(HOLD_CONVICTION) + ')')
    print(sep)
    print('')

    tickers = list(set(
        [v['etf'] for v in INDUSTRY_MAP.values()] +
        [s for v in INDUSTRY_MAP.values() for s in v['stocks']] +
        [BENCHMARK]
    ))
    print('Fetching ' + str(len(tickers)) + ' tickers...')
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    prices = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw
    print('Got ' + str(len(prices)) + ' days, ' + str(len(prices.columns)) + ' tickers')
    print('')

    if len(prices) < LOOKBACK + 5:
        print('Not enough data')
        return {}

    cash         = capital
    holdings     = []
    spy_ref      = prices[BENCHMARK].iloc[LOOKBACK]
    log          = []
    curve        = []
    peak_value   = capital
    defensive    = False
    last_scan    = LOOKBACK
    used_tickers = set()

    for idx in range(LOOKBACK, len(prices)):
        date_str = str(prices.index[idx].date())

        # Track peak and check kill criteria
        total_now = cash + port_value(holdings, prices, idx)
        if total_now > peak_value:
            peak_value = total_now
        drawdown = (total_now - peak_value) / peak_value if peak_value > 0 else 0

        if drawdown <= -PORTFOLIO_FLOOR and not defensive:
            defensive = True
            log.append({'date':date_str,'action':'DEFENSIVE','ticker':'','conv':0,'industry':'Kill criteria hit','type':'','size':0})

        # Exit defensive mode when recovered to -5% from peak
        if defensive and drawdown > -0.05:
            defensive = False
            log.append({'date':date_str,'action':'DEFENSIVE_EXIT','ticker':'','conv':0,'industry':'Recovered','type':'','size':0})

        # Daily thesis check — only exit if conviction broken for THESIS_BREAK_DAYS
        # This is the key change: we do NOT exit on short-term dips
        to_exit = []
        for h in holdings:
            c, _ = get_momentum(prices, h['ticker'], idx)
            h['conv'] = c
            # Only count low conviction days — reset if conviction recovers
            if c < HOLD_CONVICTION:
                h['low_days'] = h.get('low_days', 0) + 1
            else:
                h['low_days'] = 0  # Reset — conviction recovered, thesis intact
            # Exit only after THESIS_BREAK_DAYS consecutive low conviction days
            if h.get('low_days', 0) >= THESIS_BREAK_DAYS:
                to_exit.append(h['ticker'])

        # Execute thesis-break exits
        for tk in to_exit:
            h = next((x for x in holdings if x['ticker'] == tk), None)
            if h and tk in prices.columns:
                p = prices[tk].iloc[idx]
                if p > 0:
                    proceeds = h['shares'] * p * (1 - TRADE_COST)
                    cash += proceeds
                    gain = (p - h.get('entry_price',p)) / h.get('entry_price',p) * 100
                    log.append({'date':date_str,'action':'THESIS_BREAK_EXIT','ticker':tk,'conv':h.get('conv',0),'industry':h.get('industry',''),'type':h.get('type',''),'gain_pct':round(gain,1),'size':0})
            holdings = [x for x in holdings if x['ticker'] != tk]
            used_tickers.discard(tk)

        # Scan for new entries — check every MIN_HOLD_DAYS
        if not defensive and (idx - last_scan >= MIN_HOLD_DAYS or not holdings):
            last_scan = idx
            top_inds = scan_industries(prices, idx)

            if top_inds:
                seen = set(h['ticker'] for h in holdings)
                new_recs = []

                for ind in top_inds:
                    tk, conv = pick_best_security(prices, idx, ind)
                    if tk not in seen and conv >= MIN_CONVICTION:
                        new_recs.append({'ticker':tk,'conv':conv,'industry':ind['industry'],'type':'stock' if tk!=ind['etf'] else 'etf'})
                        seen.add(tk)

                # Direct stock breakout scan — catch leaders before ETF catches up
                direct_breakouts = []
                all_stocks = list(set(s for v in INDUSTRY_MAP.values() for s in v['stocks']))
                seen_direct = set(r['ticker'] for r in new_recs) | set(h['ticker'] for h in holdings)
                for stk in all_stocks:
                    if stk in seen_direct: continue
                    c, exc = get_momentum_multi(prices, stk, idx)
                    if c >= 88 and exc > 20:  # Only very strong breakouts
                        # Find which industry this belongs to
                        stk_industry = next((name for name, d in INDUSTRY_MAP.items() if stk in d['stocks']), 'Unknown')
                        direct_breakouts.append({'ticker':stk,'conv':c,'industry':stk_industry,'type':'stock','breakout':True})
                        seen_direct.add(stk)
                # Add top breakout if not already in recs
                if direct_breakouts:
                    best_breakout = max(direct_breakouts, key=lambda x: x['conv'])
                    new_recs.append(best_breakout)

                # Only enter if we have room and cash
                slots = MAX_POS - len(holdings)
                new_recs = sorted(new_recs, key=lambda x: x['conv'], reverse=True)[:slots]

                # Check if any new rec is significantly better than weakest current holding
                if holdings and new_recs:
                    weakest = min(holdings, key=lambda h: h.get('conv', 50))
                    new_recs = [r for r in new_recs if r['conv'] > weakest.get('conv',50) + 8]

                for rec in new_recs:
                    tk = rec['ticker']
                    if tk not in prices.columns: continue
                    p = prices[tk].iloc[idx]
                    if p <= 0 or p != p: continue

                    # Size by conviction
                    alloc = conviction_to_size(rec['conv'], len(holdings)+1, cash)
                    alloc = min(alloc, cash * 0.9)  # Never spend more than 90% of cash
                    if alloc < 50: continue  # Skip if allocation too small

                    shares = alloc * (1 - TRADE_COST) / p
                    cash -= alloc
                    days_to_lt = 366  # Track for tax awareness
                    holdings.append({
                        'ticker': tk,
                        'shares': shares,
                        'conv': rec['conv'],
                        'low_days': 0,
                        'entry_day': idx,
                        'entry_price': p,
                        'type': rec['type'],
                        'industry': rec['industry'],
                    })
                    log.append({
                        'date': date_str,
                        'action': 'ENTER',
                        'ticker': tk,
                        'conv': rec['conv'],
                        'industry': rec['industry'],
                        'type': rec['type'],
                        'size': round(alloc, 2),
                        'gain_pct': 0,
                    })

        pv = round(cash + port_value(holdings, prices, idx), 2)
        sv = round(capital * prices[BENCHMARK].iloc[idx] / spy_ref, 2)
        curve.append({'date':date_str,'strategy':pv,'spy':sv,'holdings':[h['ticker'] for h in holdings],'cash':round(cash,2)})

    if not curve: print('No results'); return {}

    final_s   = curve[-1]['strategy']
    final_spy = curve[-1]['spy']
    s_ret     = (final_s - capital) / capital * 100
    s_spy     = (final_spy - capital) / capital * 100
    alpha     = s_ret - s_spy

    peak = capital
    max_dd = 0.0
    for c in curve:
        if c['strategy'] > peak: peak = c['strategy']
        dd = (c['strategy'] - peak) / peak * 100
        if dd < max_dd: max_dd = dd

    yrs = (datetime.strptime(end,'%Y-%m-%d') - datetime.strptime(start,'%Y-%m-%d')).days / 365.25
    s_cagr   = ((final_s/capital)**(1/yrs)-1)*100 if yrs > 0 and final_s > 0 else 0
    spy_cagr = ((final_spy/capital)**(1/yrs)-1)*100 if yrs > 0 else 0

    enters = [t for t in log if t['action']=='ENTER']
    exits  = [t for t in log if t['action']=='THESIS_BREAK_EXIT']
    wins   = [t for t in exits if t.get('gain_pct',0) > 0]

    print(sep)
    print('RESULTS')
    print(sep)
    print('Period:         ' + start + ' to ' + end + '  (' + str(round(yrs,1)) + ' yrs)')
    print('Strategy:       ' + ('+' if s_ret>=0 else '') + str(round(s_ret,1)) + '%  CAGR ' + ('+' if s_cagr>=0 else '') + str(round(s_cagr,1)) + '%')
    print('SPY:            ' + ('+' if s_spy>=0 else '') + str(round(s_spy,1)) + '%  CAGR ' + ('+' if spy_cagr>=0 else '') + str(round(spy_cagr,1)) + '%')
    print('Alpha:          ' + ('+' if alpha>=0 else '') + str(round(alpha,1)) + '%')
    print('Final value:    $' + str(round(final_s,2)) + '  vs SPY $' + str(round(final_spy,2)))
    print('Max drawdown:   ' + str(round(max_dd,1)) + '%')
    print('Entries:        ' + str(len(enters)))
    print('Thesis exits:   ' + str(len(exits)) + '  (' + str(len(wins)) + ' winners, ' + str(len(exits)-len(wins)) + ' losers)')
    print('Stock entries:  ' + str(sum(1 for t in enters if t.get('type')=='stock')))
    print('ETF entries:    ' + str(sum(1 for t in enters if t.get('type')=='etf')))
    verdict = 'BEAT SPY' if alpha > 0 else 'UNDERPERFORMED SPY'
    print(verdict + ' by ' + str(abs(round(alpha,1))) + '%')
    print(sep)
    print('')
    print('All trades:')
    for t in log:
        if t['action'] in ('ENTER','THESIS_BREAK_EXIT'):
            gain = ('  gain=' + str(t.get('gain_pct',0)) + '%') if t['action']=='THESIS_BREAK_EXIT' else ('  size=$' + str(t.get('size',0)))
            print('  ' + t['date'] + '  ' + t['action'] + '  ' + t.get('ticker','') + '  ' + t.get('industry','') + '  conv=' + str(t.get('conv','-')) + gain)

    res = {
        'period': start + ' to ' + end,
        'years': round(yrs,1),
        'strategy_return': round(s_ret,2),
        'spy_return': round(s_spy,2),
        'alpha': round(alpha,2),
        'strategy_cagr': round(s_cagr,2),
        'spy_cagr': round(spy_cagr,2),
        'max_drawdown': round(max_dd,2),
        'final_strategy': round(final_s,2),
        'final_spy': round(final_spy,2),
        'entries': len(enters),
        'thesis_exits': len(exits),
        'win_rate': round(len(wins)/len(exits)*100,1) if exits else 0,
    }
    os.makedirs('data/backtest', exist_ok=True)
    fname = 'data/backtest/conviction_' + start[:4] + '_' + end[:4] + '.json'
    with open(fname,'w') as f: json.dump(res,f,indent=2)
    print('Saved to ' + fname)
    return res

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--start', default='2020-01-01')
    p.add_argument('--end',   default='2025-01-01')
    p.add_argument('--capital', type=float, default=10000.0)
    a = p.parse_args()
    run_backtest(a.start, a.end, a.capital)