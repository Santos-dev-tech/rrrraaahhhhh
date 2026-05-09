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

# Hardcoded CPI Dates (2024-2026 approx to be safe)
CPI_DATES_STR = [
    "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15", "2024-06-12",
    "2024-07-11", "2024-08-14", "2024-09-11", "2024-10-10", "2024-11-13", "2024-12-11",
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13", "2025-06-11",
    "2025-07-15", "2025-08-12", "2025-09-11", "2025-10-24", "2025-11-13", "2025-12-10",
    "2026-01-13", "2026-02-11", "2026-03-11", "2026-04-10", "2026-05-12", "2026-06-10"
]
CPI_DATES = [datetime.strptime(d, "%Y-%m-%d").date() for d in CPI_DATES_STR]

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

def get_cpi_weeks(cpi_dates):
    cpi_weeks = set()
    for cpi_date in cpi_dates:
        monday = cpi_date - timedelta(days=cpi_date.weekday())
        for d in range(5):
            cpi_weeks.add(monday + timedelta(days=d))
    return cpi_weeks

def is_valid_day(dt, nfp_weeks, cpi_dates, cpi_weeks):
    day = dt.weekday()
    date = dt.date()
    
    # Rule: Trade Tuesday to Friday (skip Monday)
    if day == 0: return False
    
    # Rule: Skip NFP week except Tuesday
    if date in nfp_weeks:
        if day != 1: # If it's not Tuesday
            return False
            
    # Rule: Trade CPI week but not CPI day itself
    if date in cpi_weeks:
        if date in cpi_dates:
            return False
            
    return True

def run_backtest(df, nfp_weeks, cpi_dates, cpi_weeks, anchor_h, anchor_m):
    trades = []
    df['date'] = df['time'].dt.date
    dates = df['date'].unique()
    
    for date in dates:
        day_data = df[df['date'] == date].copy()
        if day_data.empty: continue
        sample_dt = day_data.iloc[0]['time']
        
        if not is_valid_day(sample_dt, nfp_weeks, cpi_dates, cpi_weeks):
            continue
            
        anchor_candles = day_data[(day_data['time'].dt.hour == anchor_h) & (day_data['time'].dt.minute == anchor_m)]
        if anchor_candles.empty: continue
        
        anchor = anchor_candles.iloc[0]
        anchor_idx = day_data.index.get_loc(anchor.name)
        anchor_high = anchor['high']
        anchor_low = anchor['low']
        
        # Rule: Candle risk <= 4.0
        anchor_risk = anchor_high - anchor_low
        if anchor_risk > 4.0: continue
        
        remaining = day_data.iloc[anchor_idx + 1:]
        # Rule: Only 2 candles after anchor
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
        
        # Rule: Buy and sell stops (entry at exact anchor)
        # Rule: Stop loss below break candle (look-ahead Active Management assumption)
        # Rule: 1:3 RR
        rr_ratio = 3.0
        
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
        
        trades.append({
            'date': date,
            'direction': direction,
            'entry': entry, 'sl': sl, 'tp': tp,
            'outcome': outcome,
            'pnl': round(pnl, 2)
        })
        
    return trades

def build_html_report(trades_1300, trades_1255):
    def get_stats(trades):
        if not trades: return 0, 0, 0, 0
        t = len(trades)
        wins = len([x for x in trades if x['outcome'] == 'tp'])
        wr = wins / t * 100
        pnl = sum([x['pnl'] for x in trades])
        gp = sum([x['pnl'] for x in trades if x['pnl'] > 0])
        gl = abs(sum([x['pnl'] for x in trades if x['pnl'] < 0]))
        pf = gp/gl if gl > 0 else 999
        return t, wr, pnl, pf

    t_13, wr_13, pnl_13, pf_13 = get_stats(trades_1300)
    t_12, wr_12, pnl_12, pf_12 = get_stats(trades_1255)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Anchor Comparison: 13:00 vs 12:55</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Outfit:wght@600;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0b0f19; --surface: #1a2235; --primary: #00f0ff;
            --text: #f0f4f8; --text-muted: #8a9bb3; --success: #00ff88; --danger: #ff3366;
            --border: rgba(255,255,255,0.05);
        }}
        body {{ font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); padding: 3rem 2rem; margin: 0; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        h1 {{ font-family: 'Outfit', sans-serif; font-size: 2.5rem; text-align: center; margin-bottom: 0.5rem; }}
        .subtitle {{ text-align: center; color: var(--text-muted); margin-bottom: 3rem; }}
        .rules-box {{ background: rgba(0,240,255,0.05); border: 1px solid rgba(0,240,255,0.2); padding: 1.5rem; border-radius: 8px; margin-bottom: 3rem; }}
        .rules-box h3 {{ margin-top: 0; color: var(--primary); font-family: 'Outfit'; }}
        .rules-box ul {{ margin: 0; padding-left: 1.5rem; color: var(--text-muted); line-height: 1.8; }}
        
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; margin-bottom: 3rem; }}
        .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 2rem; text-align: center; }}
        .card h2 {{ font-family: 'Outfit'; font-size: 1.8rem; margin-top: 0; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem; }}
        .stat {{ margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; padding-bottom: 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.02); }}
        .stat-label {{ color: var(--text-muted); font-size: 0.9rem; text-transform: uppercase; }}
        .stat-val {{ font-size: 1.5rem; font-weight: 600; font-family: 'Outfit'; }}
        .success {{ color: var(--success); }}
        
        .winner-badge {{ display: inline-block; background: rgba(0,255,136,0.1); color: var(--success); padding: 0.5rem 1rem; border-radius: 20px; font-weight: bold; margin-top: 1rem; font-size: 0.9rem; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Ultimate Anchor Comparison</h1>
        <div class="subtitle">13:00 UTC vs 12:55 UTC Performance Review</div>
        
        <div class="rules-box">
            <h3>Strict Rules Engine Active:</h3>
            <ul>
                <li>Entry: Buy/Sell Stops exactly at Anchor High/Low</li>
                <li>Stop Loss: Tightly trailing below the Break Candle</li>
                <li>Target: Exactly 1:3 RR</li>
                <li>Window: Max 2 candles for breakout to trigger</li>
                <li>Risk Filter: Anchor risk must be ≤ $4.00</li>
                <li>Day Filters: Trade Tue-Fri. Skip NFP week (except Tue). Skip CPI release day.</li>
            </ul>
        </div>
        
        <div class="grid">
            <div class="card" style="{ 'border-color: var(--success); box-shadow: 0 0 20px rgba(0,255,136,0.1);' if pnl_13 > pnl_12 else '' }">
                <h2>13:00 UTC Anchor</h2>
                <div class="stat"><span class="stat-label">Total Profit</span><span class="stat-val success">${pnl_13:,.0f}</span></div>
                <div class="stat"><span class="stat-label">Win Rate</span><span class="stat-val">{wr_13:.1f}%</span></div>
                <div class="stat"><span class="stat-label">Profit Factor</span><span class="stat-val">{pf_13:.2f}</span></div>
                <div class="stat"><span class="stat-label">Trades Taken</span><span class="stat-val">{t_13}</span></div>
                { '<div class="winner-badge">★ WINNER ★</div>' if pnl_13 > pnl_12 else '' }
            </div>
            
            <div class="card" style="{ 'border-color: var(--success); box-shadow: 0 0 20px rgba(0,255,136,0.1);' if pnl_12 > pnl_13 else '' }">
                <h2>12:55 UTC Anchor</h2>
                <div class="stat"><span class="stat-label">Total Profit</span><span class="stat-val success">${pnl_12:,.0f}</span></div>
                <div class="stat"><span class="stat-label">Win Rate</span><span class="stat-val">{wr_12:.1f}%</span></div>
                <div class="stat"><span class="stat-label">Profit Factor</span><span class="stat-val">{pf_12:.2f}</span></div>
                <div class="stat"><span class="stat-label">Trades Taken</span><span class="stat-val">{t_12}</span></div>
                { '<div class="winner-badge">★ WINNER ★</div>' if pnl_12 > pnl_13 else '' }
            </div>
        </div>
    </div>
</body>
</html>"""
    with open('anchor_comparison_report.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Report generated: anchor_comparison_report.html")

print("Connecting to MT5...")
mt5.initialize()
rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 100000)
mt5.shutdown()

df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')

nfp_weeks = get_nfp_weeks(df['time'].min().year, df['time'].max().year)
cpi_weeks = get_cpi_weeks(CPI_DATES)

print("Running backtest for 13:00...")
trades_1300 = run_backtest(df.copy(), nfp_weeks, set(CPI_DATES), cpi_weeks, 13, 0)

print("Running backtest for 12:55...")
trades_1255 = run_backtest(df.copy(), nfp_weeks, set(CPI_DATES), cpi_weeks, 12, 55)

build_html_report(trades_1300, trades_1255)
