import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

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

def is_valid_day(dt, nfp_weeks, day_filter=None):
    day = dt.weekday()
    date = dt.date()
    if day == 0: return False  # skip Monday
    if day_filter and dt.day_name() not in day_filter: return False
    if date in nfp_weeks: return day == 1
    return True

def run_true_pending(df, nfp_weeks, rr_ratio, day_filter=None, max_risk=999):
    trades = []
    df['date'] = df['time'].dt.date
    dates = df['date'].unique()
    
    for date in dates:
        day_data = df[df['date'] == date].copy()
        if day_data.empty: continue
        sample_dt = day_data.iloc[0]['time']
        if not is_valid_day(sample_dt, nfp_weeks, day_filter): continue
        
        anchor_candles = day_data[(day_data['time'].dt.hour == 13) & (day_data['time'].dt.minute == 0)]
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
            if candle['high'] > anchor_high and candle['low'] < anchor_low:
                direction = 'long' if candle['close'] >= candle['open'] else 'short'
                break_candle = candle; break
            elif candle['high'] > anchor_high:
                direction = 'long'; break_candle = candle; break
            elif candle['low'] < anchor_low:
                direction = 'short'; break_candle = candle; break
                
        if direction is None: continue
        
        # EXACT PENDING ORDER LOGIC (Knowable at 13:05)
        if direction == 'long':
            entry = anchor_high
            sl = anchor_low - SL_BUFFER  # SL is at anchor low!
            risk = entry - sl
            if risk <= 0: continue
            tp = entry + (risk * rr_ratio)
        else:
            entry = anchor_low
            sl = anchor_high + SL_BUFFER # SL is at anchor high!
            risk = sl - entry
            if risk <= 0: continue
            tp = entry - (risk * rr_ratio)
            
        if risk > max_risk: continue
            
        forward_all = df[df.index > break_candle.name]
        outcome = 'open'
        exit_price = None
        
        for _, fcandle in forward_all.iterrows():
            if fcandle['time'].hour >= EOD_CLOSE_HOUR and fcandle['time'].date() == date:
                outcome = 'eod_close'
                exit_price = fcandle['close']
                break
                
            if direction == 'long':
                if fcandle['low'] <= sl: outcome = 'sl'; exit_price = sl; break
                if fcandle['high'] >= tp: outcome = 'tp'; exit_price = tp; break
            else:
                if fcandle['high'] >= sl: outcome = 'sl'; exit_price = sl; break
                if fcandle['low'] <= tp: outcome = 'tp'; exit_price = tp; break
                
        if outcome == 'open': continue
        
        lot_size = RISK_PER_TRADE / (risk * POINT_VALUE)
        pnl = (exit_price - entry) * POINT_VALUE * lot_size if direction == 'long' else (entry - exit_price) * POINT_VALUE * lot_size
        trades.append({'outcome': outcome, 'pnl': pnl})
        
    return trades

def summarize(trades, label):
    if not trades: return None
    df = pd.DataFrame(trades)
    t = len(df)
    w = len(df[df['outcome'] == 'tp'])
    pnl = df['pnl'].sum()
    gp = df[df['pnl']>0]['pnl'].sum()
    gl = abs(df[df['pnl']<0]['pnl'].sum())
    pf = gp/gl if gl > 0 else 999
    return f"{label:<30} {t:>4}t  {w/t*100:>5.1f}%  ${pnl:>7.0f}  PF: {pf:.2f}"

mt5.initialize()
rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 100000)
mt5.shutdown()
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
nfp_weeks = get_nfp_weeks(df['time'].min().year, df['time'].max().year)

print("\n--- TRUE PENDING ORDER LOGIC (SL at Anchor High/Low) ---")
print(summarize(run_true_pending(df, nfp_weeks, 3.0), "1:3 RR (All Days)"))
print(summarize(run_true_pending(df, nfp_weeks, 3.0, day_filter=['Tuesday','Thursday']), "1:3 RR (Tue/Thu)"))
print(summarize(run_true_pending(df, nfp_weeks, 4.0), "1:4 RR (All Days)"))
print(summarize(run_true_pending(df, nfp_weeks, 4.0, day_filter=['Tuesday','Thursday']), "1:4 RR (Tue/Thu)"))
print(summarize(run_true_pending(df, nfp_weeks, 3.0, day_filter=['Tuesday','Thursday'], max_risk=4.0), "1:3 RR (Tue/Thu, Risk <= $4)"))
