"""
Advanced Strategy Lab — Tests that need raw candle data from MT5
Tests: Trailing Stop, RR variations, Long-only, Partial TP
Anchor: 13:00 UTC (recommended)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ── CONFIG ──
SYMBOL = "XAUUSDm"
ANCHOR_TIME = "13:00"
SL_BUFFER = 0.50
EOD_CLOSE_HOUR = 21
RISK_PER_TRADE = 30
POINT_VALUE = 100

def get_nfp_weeks(start_year, end_year):
    nfp_weeks = set()
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            first_day = datetime(year, month, 1)
            days_until_friday = (4 - first_day.weekday()) % 7
            first_friday = first_day + timedelta(days=days_until_friday)
            monday = first_friday - timedelta(days=first_friday.weekday())
            for d in range(5):
                nfp_weeks.add((monday + timedelta(days=d)).date())
    return nfp_weeks

def is_valid_day(dt, nfp_weeks, day_filter=None):
    day = dt.weekday()
    date = dt.date()
    if day == 0: return False  # skip Monday
    if day_filter and dt.day_name() not in day_filter:
        return False
    if date in nfp_weeks:
        return day == 1
    return True

def run_variant(df, nfp_weeks, rr_ratio=3.0, trailing_be=False, partial_tp_at=0, 
                long_only=False, short_only=False, max_risk=999, min_risk=0,
                day_filter=None, label=""):
    """Run a single backtest variant."""
    hour, minute = 13, 0
    trades = []
    df['date'] = df['time'].dt.date
    dates = df['date'].unique()
    
    for date in dates:
        day_data = df[df['date'] == date].copy()
        if day_data.empty: continue
        sample_dt = day_data.iloc[0]['time']
        if not is_valid_day(sample_dt, nfp_weeks, day_filter): continue
        
        anchor_mask = (day_data['time'].dt.hour == hour) & (day_data['time'].dt.minute == minute)
        anchor_candles = day_data[anchor_mask]
        if anchor_candles.empty: continue
        
        anchor = anchor_candles.iloc[0]
        anchor_idx = day_data.index.get_loc(anchor.name)
        anchor_high = anchor['high']
        anchor_low = anchor['low']
        
        remaining = day_data.iloc[anchor_idx + 1:]
        if len(remaining) < 2: continue
        next_two = remaining.iloc[:2]
        
        direction = None
        break_candle = None
        for _, candle in next_two.iterrows():
            broke_high = candle['high'] > anchor_high
            broke_low = candle['low'] < anchor_low
            if broke_high and broke_low:
                direction = 'long' if candle['close'] >= candle['open'] else 'short'
                break_candle = candle; break
            elif broke_high:
                direction = 'long'; break_candle = candle; break
            elif broke_low:
                direction = 'short'; break_candle = candle; break
        
        if direction is None: continue
        if long_only and direction == 'short': continue
        if short_only and direction == 'long': continue
        
        # Calculate entry, SL, TP
        if direction == 'long':
            entry = anchor_high
            sl = break_candle['low'] - SL_BUFFER
            risk = entry - sl
            if risk <= 0: continue
            tp = entry + (risk * rr_ratio)
        else:
            entry = anchor_low
            sl = break_candle['high'] + SL_BUFFER
            risk = sl - entry
            if risk <= 0: continue
            tp = entry - (risk * rr_ratio)
        
        # Apply risk size filter
        if risk > max_risk or risk < min_risk: continue
        
        # Walk forward
        forward_all = df[df.index > break_candle.name]
        outcome = 'open'
        exit_price = None
        current_sl = sl
        partial_closed = False
        partial_pnl = 0
        lot_size = RISK_PER_TRADE / (risk * POINT_VALUE)
        remaining_lots = lot_size
        
        # Trailing/partial state
        be_activated = False
        
        for _, fcandle in forward_all.iterrows():
            if fcandle['time'].hour >= EOD_CLOSE_HOUR and fcandle['time'].date() == date:
                outcome = 'eod_close'
                exit_price = fcandle['close']
                break
            
            if direction == 'long':
                # Check trailing stop to BE after 1R
                if trailing_be and not be_activated:
                    if fcandle['high'] >= entry + risk:  # hit 1R
                        current_sl = entry  # move SL to breakeven
                        be_activated = True
                
                # Check partial TP
                if partial_tp_at > 0 and not partial_closed:
                    if fcandle['high'] >= entry + (risk * partial_tp_at):
                        # Close half at partial_tp_at R
                        half_lots = lot_size / 2
                        partial_pnl = (risk * partial_tp_at) * POINT_VALUE * half_lots
                        remaining_lots = half_lots
                        partial_closed = True
                        current_sl = entry  # also move SL to BE for remainder
                
                if fcandle['low'] <= current_sl:
                    outcome = 'sl'
                    exit_price = current_sl
                    break
                if fcandle['high'] >= tp:
                    outcome = 'tp'
                    exit_price = tp
                    break
            else:  # short
                if trailing_be and not be_activated:
                    if fcandle['low'] <= entry - risk:
                        current_sl = entry
                        be_activated = True
                
                if partial_tp_at > 0 and not partial_closed:
                    if fcandle['low'] <= entry - (risk * partial_tp_at):
                        half_lots = lot_size / 2
                        partial_pnl = (risk * partial_tp_at) * POINT_VALUE * half_lots
                        remaining_lots = half_lots
                        partial_closed = True
                        current_sl = entry
                
                if fcandle['high'] >= current_sl:
                    outcome = 'sl'
                    exit_price = current_sl
                    break
                if fcandle['low'] <= tp:
                    outcome = 'tp'
                    exit_price = tp
                    break
        
        if outcome == 'open': continue
        
        # Calculate P&L
        if direction == 'long':
            main_pnl = (exit_price - entry) * POINT_VALUE * remaining_lots
        else:
            main_pnl = (entry - exit_price) * POINT_VALUE * remaining_lots
        
        total_pnl = main_pnl + partial_pnl
        
        trades.append({
            'date': str(date),
            'direction': direction,
            'entry': entry, 'sl': sl, 'tp': tp,
            'exit_price': exit_price,
            'pnl': round(total_pnl, 2),
            'outcome': outcome,
            'risk': risk,
            'be_activated': be_activated if trailing_be else None,
            'partial_closed': partial_closed if partial_tp_at > 0 else None,
        })
    
    return trades

def summarize(trades, label):
    if not trades:
        return None
    df = pd.DataFrame(trades)
    t = len(df); w = len(df[df['outcome'] == 'tp'])
    wr = w / t * 100
    pnl = df['pnl'].sum()
    gp = df[df['pnl'] > 0]['pnl'].sum()
    gl = abs(df[df['pnl'] < 0]['pnl'].sum())
    pf = gp / gl if gl > 0 else 999
    cum = df['pnl'].cumsum()
    dd = (cum.cummax() - cum).max()
    return {'label': label, 't': t, 'wr': wr, 'pnl': pnl, 'pf': pf, 'dd': dd, 'pt': pnl/t}

def print_row(s):
    if s is None: return
    print(f"  {s['label']:<45} {s['t']:>4}t {s['wr']:>5.1f}% ${s['pnl']:>8.0f}  PF={s['pf']:>5.2f}  DD=${s['dd']:>5.0f}  $/t=${s['pt']:>5.1f}")

# ── MAIN ──
print("Connecting to MT5...")
if not mt5.initialize():
    print(f"MT5 failed: {mt5.last_error()}")
    sys.exit(1)

print(f"Connected: {mt5.account_info().login} @ {mt5.account_info().server}")

# Find symbol
symbol_name = SYMBOL
if mt5.symbol_info(SYMBOL) is None:
    for alt in ["XAUUSD", "XAUUSDm", "GOLD", "GOLDm"]:
        if mt5.symbol_info(alt):
            symbol_name = alt; break

mt5.symbol_select(symbol_name, True)
rates = mt5.copy_rates_from_pos(symbol_name, mt5.TIMEFRAME_M5, 0, 100000)
mt5.shutdown()

if rates is None or len(rates) == 0:
    print("No data!"); sys.exit(1)

df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
print(f"Got {len(df):,} candles: {df['time'].min().date()} to {df['time'].max().date()}")

nfp_weeks = get_nfp_weeks(df['time'].min().year, df['time'].max().year)

# ── RUN ALL VARIANTS ──
header = f"\n{'':>47} {'TR':>4}  {'WR':>5}  {'P&L':>9}  {'PF':>8}  {'MaxDD':>8}  {'$/trade':>9}"
divider = "-" * 105

print("\n" + "=" * 105)
print("  ADVANCED STRATEGY LAB — 13:00 UTC")
print("=" * 105)
print(header)
print(divider)

# Baseline
print_row(summarize(run_variant(df.copy(), nfp_weeks), "BASELINE: 1:3 RR, all days"))

# ── RR VARIATIONS ──
print(f"\n-- RR RATIO TESTS --")
for rr in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
    trades = run_variant(df.copy(), nfp_weeks, rr_ratio=rr)
    print_row(summarize(trades, f"1:{rr:.1f} RR"))

# ── TRAILING STOP ──
print(f"\n-- TRAILING STOP TO BREAKEVEN (after 1R) --")
for rr in [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
    trades = run_variant(df.copy(), nfp_weeks, rr_ratio=rr, trailing_be=True)
    s = summarize(trades, f"1:{rr:.1f} RR + trail BE@1R")
    print_row(s)
    if s and rr == 3.0:
        # Count how many times BE saved us
        tdf = pd.DataFrame(trades)
        be_saves = len(tdf[(tdf['be_activated'] == True) & (tdf['outcome'] == 'sl') & (tdf['pnl'] == 0)])
        print(f"    ^ BE saved from full loss {be_saves} times")

# ── PARTIAL TP ──
print(f"\n-- PARTIAL CLOSE (50% at XR, rest rides to 3R) --")
for pt in [1.0, 1.5, 2.0]:
    trades = run_variant(df.copy(), nfp_weeks, rr_ratio=3.0, partial_tp_at=pt)
    print_row(summarize(trades, f"Partial 50% at {pt:.1f}R, rest to 3R"))

# ── LONG ONLY ──
print(f"\n-- DIRECTION FILTERS --")
print_row(summarize(run_variant(df.copy(), nfp_weeks, long_only=True), "LONG ONLY"))
print_row(summarize(run_variant(df.copy(), nfp_weeks, short_only=True), "SHORT ONLY"))

# ── BEST COMBOS WITH FILTERS ──
print(f"\n-- BEST COMBOS (Tue+Thu, risk filters + advanced) --")

combos = [
    ("Tue+Thu, risk<=3.5, 1:3", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5)),
    ("Tue+Thu, risk<=3.5, 1:3 + trail BE", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5, trailing_be=True)),
    ("Tue+Thu, risk<=3.5, 1:2.5", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5, rr_ratio=2.5)),
    ("Tue+Thu, risk<=3.5, 1:2.5 + trail BE", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5, rr_ratio=2.5, trailing_be=True)),
    ("Tue+Thu, risk<=3.5, 1:4", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5, rr_ratio=4.0)),
    ("Tue+Thu, risk<=3.5, 1:4 + trail BE", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5, rr_ratio=4.0, trailing_be=True)),
    ("Tue+Thu, risk<=4.5, 1:3 + trail BE", dict(day_filter=['Tuesday','Thursday'], max_risk=4.5, trailing_be=True)),
    ("Tue+Thu, risk<=4.5, 1:3, LONG ONLY", dict(day_filter=['Tuesday','Thursday'], max_risk=4.5, long_only=True)),
    ("Tue+Thu, risk<=3.5, 1:3, LONG ONLY", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5, long_only=True)),
    ("Tue+Thu, risk<=3.5, partial@1R", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5, partial_tp_at=1.0)),
    ("Tue+Thu, risk<=4.5, 1:2 + trail BE", dict(day_filter=['Tuesday','Thursday'], max_risk=4.5, rr_ratio=2.0, trailing_be=True)),
    ("Tue+Thu, risk<=4.5, 1:2", dict(day_filter=['Tuesday','Thursday'], max_risk=4.5, rr_ratio=2.0)),
    ("All days, risk<=3.5, 1:3 + trail BE", dict(max_risk=3.5, trailing_be=True)),
    ("All days, risk<=3.5, LONG ONLY", dict(max_risk=3.5, long_only=True)),
    ("All days, risk<=3.5, LONG + trail BE", dict(max_risk=3.5, long_only=True, trailing_be=True)),
]

results = []
for label, kwargs in combos:
    trades = run_variant(df.copy(), nfp_weeks, **kwargs)
    s = summarize(trades, label)
    if s: 
        print_row(s)
        results.append(s)

# ── FINAL RANKING ──
# Collect everything worth ranking
all_key = [
    ("BASELINE 1:3", {}),
    ("1:2 RR", dict(rr_ratio=2.0)),
    ("1:3 + trail BE", dict(trailing_be=True)),
    ("1:4 + trail BE", dict(rr_ratio=4.0, trailing_be=True)),
    ("Tue+Thu, risk<=3.5, 1:3", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5)),
    ("Tue+Thu, risk<=3.5, trail BE", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5, trailing_be=True)),
    ("Tue+Thu, risk<=3.5, 1:4+trail", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5, rr_ratio=4.0, trailing_be=True)),
    ("Tue+Thu, risk<=4.5, 1:3", dict(day_filter=['Tuesday','Thursday'], max_risk=4.5)),
    ("Tue+Thu, risk<=4.5, trail BE", dict(day_filter=['Tuesday','Thursday'], max_risk=4.5, trailing_be=True)),
    ("All days, risk<=3.5, trail BE", dict(max_risk=3.5, trailing_be=True)),
    ("risk<=3.5", dict(max_risk=3.5)),
    ("LONG ONLY", dict(long_only=True)),
    ("Tue+Thu, risk<=3.5, LONG", dict(day_filter=['Tuesday','Thursday'], max_risk=3.5, long_only=True)),
]

final = []
for label, kwargs in all_key:
    trades = run_variant(df.copy(), nfp_weeks, **kwargs)
    s = summarize(trades, label)
    if s and s['t'] >= 15:
        final.append(s)

print(f"\n\n{'='*105}")
print("  FINAL RANKINGS")
print(f"{'='*105}")

print(f"\n  -- BY TOTAL PROFIT --")
print(header); print(divider)
for s in sorted(final, key=lambda x: x['pnl'], reverse=True)[:10]:
    print_row(s)

print(f"\n  -- BY PROFIT FACTOR --")
print(header); print(divider)
for s in sorted(final, key=lambda x: x['pf'], reverse=True)[:10]:
    print_row(s)

print(f"\n  -- BY $/TRADE (efficiency) --")
print(header); print(divider)
for s in sorted(final, key=lambda x: x['pt'], reverse=True)[:10]:
    print_row(s)

print("\nDone!")
