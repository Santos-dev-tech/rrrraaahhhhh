import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

# ── CONFIG ──
SYMBOL = "XAUUSDm"
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

def is_valid_day(dt, nfp_weeks):
    day = dt.weekday()
    date = dt.date()
    if day == 0: return False  # skip Monday
    if date in nfp_weeks:
        return day == 1
    return True

def run_be_test(df, nfp_weeks, trail_be_at):
    hour, minute = 13, 0
    trades = []
    df['date'] = df['time'].dt.date
    dates = df['date'].unique()
    rr_ratio = 3.0
    
    for date in dates:
        day_data = df[df['date'] == date].copy()
        if day_data.empty: continue
        sample_dt = day_data.iloc[0]['time']
        if not is_valid_day(sample_dt, nfp_weeks): continue
        
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
        
        forward_all = df[df.index > break_candle.name]
        outcome = 'open'
        exit_price = None
        current_sl = sl
        lot_size = RISK_PER_TRADE / (risk * POINT_VALUE)
        be_activated = False
        
        for _, fcandle in forward_all.iterrows():
            if fcandle['time'].hour >= EOD_CLOSE_HOUR and fcandle['time'].date() == date:
                outcome = 'eod_close'
                exit_price = fcandle['close']
                break
            
            if direction == 'long':
                # Check BE threshold
                if trail_be_at is not None and not be_activated:
                    if fcandle['high'] >= entry + (risk * trail_be_at):
                        current_sl = entry
                        be_activated = True
                
                if fcandle['low'] <= current_sl:
                    outcome = 'sl'
                    exit_price = current_sl
                    break
                if fcandle['high'] >= tp:
                    outcome = 'tp'
                    exit_price = tp
                    break
            else:
                if trail_be_at is not None and not be_activated:
                    if fcandle['low'] <= entry - (risk * trail_be_at):
                        current_sl = entry
                        be_activated = True
                
                if fcandle['high'] >= current_sl:
                    outcome = 'sl'
                    exit_price = current_sl
                    break
                if fcandle['low'] <= tp:
                    outcome = 'tp'
                    exit_price = tp
                    break
        
        if outcome == 'open': continue
        
        if direction == 'long':
            pnl = (exit_price - entry) * POINT_VALUE * lot_size
        else:
            pnl = (entry - exit_price) * POINT_VALUE * lot_size
            
        trades.append({
            'outcome': outcome,
            'pnl': round(pnl, 2),
            'be_activated': be_activated
        })
    
    return trades

def summarize(trades, label):
    if not trades: return None
    df = pd.DataFrame(trades)
    t = len(df)
    wins = len(df[df['outcome'] == 'tp'])
    wr = wins / t * 100
    pnl = df['pnl'].sum()
    gp = df[df['pnl'] > 0]['pnl'].sum()
    gl = abs(df[df['pnl'] < 0]['pnl'].sum())
    pf = gp / gl if gl > 0 else 999
    
    # Calculate how many times BE saved a full loss vs how many times it choked a win
    # A choked win is theoretically impossible to know without re-running the trade without BE,
    # but we can look at the overall delta in wins.
    be_saves = len(df[(df['be_activated'] == True) & (df['pnl'] == 0)])
    
    return {
        'label': label, 't': t, 'wr': wr, 'pnl': pnl, 'pf': pf, 'be_saves': be_saves
    }

print("Connecting to MT5...")
if not mt5.initialize():
    print("MT5 failed")
    sys.exit(1)

symbol_name = SYMBOL
if mt5.symbol_info(SYMBOL) is None:
    for alt in ["XAUUSD", "XAUUSDm", "GOLD", "GOLDm"]:
        if mt5.symbol_info(alt):
            symbol_name = alt; break

mt5.symbol_select(symbol_name, True)
rates = mt5.copy_rates_from_pos(symbol_name, mt5.TIMEFRAME_M5, 0, 100000)
mt5.shutdown()

df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
nfp_weeks = get_nfp_weeks(df['time'].min().year, df['time'].max().year)

print(f"\n{'':>30} {'TR':>4}  {'WR':>5}  {'P&L':>8}  {'PF':>5}  {'Saved by BE':>12}")
print("-" * 80)

baseline_trades = run_be_test(df.copy(), nfp_weeks, None)
b = summarize(baseline_trades, "Baseline 1:3 (No BE Trail)")
print(f"  {b['label']:<28} {b['t']:>4}t {b['wr']:>5.1f}% ${b['pnl']:>7.0f}  {b['pf']:>5.2f}  {'N/A':>12}")

base_wins = len([t for t in baseline_trades if t['outcome'] == 'tp'])

for be_thresh in [0.5, 1.0, 1.5, 2.0, 2.5]:
    trades = run_be_test(df.copy(), nfp_weeks, be_thresh)
    s = summarize(trades, f"Move to BE at {be_thresh:.1f}R")
    wins = len([t for t in trades if t['outcome'] == 'tp'])
    choked_wins = base_wins - wins
    
    # We also want to know the "net cash difference"
    diff = s['pnl'] - b['pnl']
    
    print(f"  {s['label']:<28} {s['t']:>4}t {s['wr']:>5.1f}% ${s['pnl']:>7.0f}  {s['pf']:>5.2f}  {s['be_saves']:>6} trades")
    print(f"       -> Saved {s['be_saves']} losses (+${s['be_saves']*30}), but choked {choked_wins} wins (-${choked_wins*90}). Net effect: ${diff:.0f}")

print("\nDone!")
