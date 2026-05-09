"""
XAUUSD Strategy Optimizer
Tests: day filters, 1 vs 2 candle break window, anchor times
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

SYMBOL = "XAUUSDm"
SL_BUFFER = 0.50
RR_RATIO = 3.0
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

def run_backtest(df, anchor_time_str, nfp_weeks, max_break_candles=2, skip_days=None):
    """Run backtest with configurable break window and day filters."""
    if skip_days is None:
        skip_days = {0}  # default: skip Monday only
    
    hour, minute = map(int, anchor_time_str.split(":"))
    trades = []
    
    df['date'] = df['time'].dt.date
    dates = df['date'].unique()
    
    for date in dates:
        day_data = df[df['date'] == date].copy()
        if day_data.empty:
            continue
        
        sample_dt = day_data.iloc[0]['time']
        day_of_week = sample_dt.weekday()
        
        # Skip filtered days
        if day_of_week in skip_days:
            continue
        
        # NFP week filter: only Tuesday
        if date in nfp_weeks and day_of_week != 1:
            continue
        
        # Find anchor candle
        anchor_mask = (day_data['time'].dt.hour == hour) & (day_data['time'].dt.minute == minute)
        anchor_candles = day_data[anchor_mask]
        if anchor_candles.empty:
            continue
        
        anchor = anchor_candles.iloc[0]
        anchor_idx = day_data.index.get_loc(anchor.name)
        anchor_high = anchor['high']
        anchor_low = anchor['low']
        
        remaining = day_data.iloc[anchor_idx + 1:]
        if len(remaining) < max_break_candles:
            continue
        
        next_candles = remaining.iloc[:max_break_candles]
        
        direction = None
        break_candle = None
        
        for _, candle in next_candles.iterrows():
            broke_high = candle['high'] > anchor_high
            broke_low = candle['low'] < anchor_low
            
            if broke_high and broke_low:
                if candle['close'] >= candle['open']:
                    direction = 'long'
                else:
                    direction = 'short'
                break_candle = candle
                break
            elif broke_high:
                direction = 'long'
                break_candle = candle
                break
            elif broke_low:
                direction = 'short'
                break_candle = candle
                break
        
        if direction is None:
            continue
        
        if direction == 'long':
            entry = anchor_high
            sl = break_candle['low'] - SL_BUFFER
            risk = entry - sl
            if risk <= 0:
                continue
            tp = entry + (risk * RR_RATIO)
        else:
            entry = anchor_low
            sl = break_candle['high'] + SL_BUFFER
            risk = sl - entry
            if risk <= 0:
                continue
            tp = entry - (risk * RR_RATIO)
        
        break_idx = day_data.index.get_loc(break_candle.name)
        forward_all = df[df.index > break_candle.name]
        
        outcome = 'open'
        exit_price = None
        
        for _, fcandle in forward_all.iterrows():
            if fcandle['time'].hour >= 21 and fcandle['time'].date() == date:
                outcome = 'eod_close'
                exit_price = fcandle['close']
                break
            
            if direction == 'long':
                if fcandle['low'] <= sl:
                    outcome = 'sl'
                    exit_price = sl
                    break
                if fcandle['high'] >= tp:
                    outcome = 'tp'
                    exit_price = tp
                    break
            else:
                if fcandle['high'] >= sl:
                    outcome = 'sl'
                    exit_price = sl
                    break
                if fcandle['low'] <= tp:
                    outcome = 'tp'
                    exit_price = tp
                    break
        
        if outcome == 'open':
            continue
        
        lot_size = RISK_PER_TRADE / (risk * POINT_VALUE)
        if direction == 'long':
            pnl = (exit_price - entry) * POINT_VALUE * lot_size
        else:
            pnl = (entry - exit_price) * POINT_VALUE * lot_size
        
        trades.append({
            'date': str(date),
            'day': sample_dt.strftime('%A'),
            'day_num': day_of_week,
            'direction': direction,
            'pnl': round(pnl, 2),
            'outcome': outcome,
        })
    
    return trades

def calc_stats(trades):
    if not trades:
        return {'trades': 0, 'wr': 0, 'pnl': 0, 'pf': 0}
    df = pd.DataFrame(trades)
    wins = df[df['outcome'] == 'tp']
    losses = df[df['outcome'] == 'sl']
    gross_profit = wins['pnl'].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses['pnl'].sum()) if len(losses) > 0 else 1
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    return {
        'trades': len(df),
        'wins': len(wins),
        'losses': len(losses),
        'wr': round(len(wins) / len(df) * 100, 1),
        'pnl': round(df['pnl'].sum(), 2),
        'pf': round(pf, 2),
    }

def main():
    print("=" * 60)
    print("  XAUUSD Strategy Optimizer")
    print("=" * 60)
    
    if not mt5.initialize():
        print(f"MT5 failed: {mt5.last_error()}")
        sys.exit(1)
    
    symbol_name = SYMBOL
    if mt5.symbol_info(SYMBOL) is None:
        for alt in ["XAUUSD", "XAUUSDm", "GOLD"]:
            if mt5.symbol_info(alt) is not None:
                symbol_name = alt
                break
    
    mt5.symbol_select(symbol_name, True)
    rates = mt5.copy_rates_from_pos(symbol_name, mt5.TIMEFRAME_M5, 0, 100000)
    
    if rates is None or len(rates) == 0:
        print(f"No data: {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    print(f"Data: {df['time'].min().date()} to {df['time'].max().date()} ({len(df):,} candles)")
    
    nfp_weeks = get_nfp_weeks(df['time'].min().year, df['time'].max().year)
    
    # ═══════════════════════════════════════════════════════════
    # TEST 1: Day-of-week breakdown (using 12:55 anchor, 2 candles)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("  TEST 1: Day-of-Week Performance (12:55 anchor, 2 candles)")
    print("=" * 60)
    
    day_names = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday'}
    
    # Run with NO day filter (except NFP rules) to see all days
    all_trades = run_backtest(df.copy(), "12:55", nfp_weeks, max_break_candles=2, skip_days=set())
    
    for day_num in range(5):
        day_trades = [t for t in all_trades if t['day_num'] == day_num]
        s = calc_stats(day_trades)
        marker = " *** AVOID ***" if s['pnl'] < 0 else (" ** WEAK **" if s['pf'] < 1.3 else "")
        print(f"  {day_names[day_num]:12s} | {s['trades']:3d} trades | WR: {s['wr']:5.1f}% | P&L: ${s['pnl']:>8.2f} | PF: {s['pf']:>5.2f}{marker}")
    
    # Same for 13:00
    print("\n" + "=" * 60)
    print("  TEST 1b: Day-of-Week Performance (13:00 anchor, 2 candles)")
    print("=" * 60)
    
    all_trades_1300 = run_backtest(df.copy(), "13:00", nfp_weeks, max_break_candles=2, skip_days=set())
    
    for day_num in range(5):
        day_trades = [t for t in all_trades_1300 if t['day_num'] == day_num]
        s = calc_stats(day_trades)
        marker = " *** AVOID ***" if s['pnl'] < 0 else (" ** WEAK **" if s['pf'] < 1.3 else "")
        print(f"  {day_names[day_num]:12s} | {s['trades']:3d} trades | WR: {s['wr']:5.1f}% | P&L: ${s['pnl']:>8.2f} | PF: {s['pf']:>5.2f}{marker}")
    
    # ═══════════════════════════════════════════════════════════
    # TEST 2: 1 candle vs 2 candles break window
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("  TEST 2: Break Window — 1 Candle vs 2 Candles")
    print("=" * 60)
    
    for anchor in ["12:55", "13:00", "13:30"]:
        print(f"\n  Anchor: {anchor} UTC")
        for candles in [1, 2]:
            trades = run_backtest(df.copy(), anchor, nfp_weeks, max_break_candles=candles, skip_days={0})
            s = calc_stats(trades)
            print(f"    {candles} candle(s) | {s['trades']:3d} trades | WR: {s['wr']:5.1f}% | P&L: ${s['pnl']:>8.2f} | PF: {s['pf']:>5.2f}")
    
    # ═══════════════════════════════════════════════════════════
    # TEST 3: Best combo — skip worst days + best candle window
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("  TEST 3: Optimized Combos (skip Monday + worst day)")
    print("=" * 60)
    
    # Test skipping Monday + each other day
    for anchor in ["12:55", "13:00"]:
        print(f"\n  Anchor: {anchor} UTC")
        for skip_extra in [None, 2, 3, 4]:  # None = Mon only, then Mon+Wed, Mon+Thu, Mon+Fri
            skip = {0}
            label = "Mon only"
            if skip_extra is not None:
                skip.add(skip_extra)
                label = f"Mon + {day_names[skip_extra]}"
            
            for candles in [1, 2]:
                trades = run_backtest(df.copy(), anchor, nfp_weeks, max_break_candles=candles, skip_days=skip)
                s = calc_stats(trades)
                print(f"    Skip {label:15s} | {candles}c | {s['trades']:3d} trades | WR: {s['wr']:5.1f}% | P&L: ${s['pnl']:>8.2f} | PF: {s['pf']:>5.2f}")
    
    mt5.shutdown()
    print("\n" + "=" * 60)
    print("  OPTIMIZATION COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
