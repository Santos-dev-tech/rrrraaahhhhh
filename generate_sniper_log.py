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

def run_sniper_backtest(df, nfp_weeks):
    trades = []
    df['date'] = df['time'].dt.date
    dates = df['date'].unique()
    
    for date in dates:
        day_data = df[df['date'] == date].copy()
        if day_data.empty: continue
        sample_dt = day_data.iloc[0]['time']
        
        # Rule: Trade ONLY Tuesday and Thursday
        day = sample_dt.weekday()
        if day not in [1, 3]: continue
        
        # Rule: Skip NFP week except Tuesday
        if sample_dt.date() in nfp_weeks and day != 1:
            continue
            
        anchor_candles = day_data[(day_data['time'].dt.hour == 13) & (day_data['time'].dt.minute == 0)]
        if anchor_candles.empty: continue
        
        anchor = anchor_candles.iloc[0]
        anchor_idx = day_data.index.get_loc(anchor.name)
        anchor_high = anchor['high']
        anchor_low = anchor['low']
        
        # Rule: Risk <= 3.50
        anchor_risk = anchor_high - anchor_low
        if anchor_risk > 3.5: continue
        
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
        
        # Rule: Stop loss below break candle (Active Management)
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
            'exit_price': exit_price,
            'outcome': outcome,
            'pnl': round(pnl, 2)
        })
        
    return trades

def build_html_report(trades):
    # Sort trades chronologically
    trades.sort(key=lambda x: x['date'], reverse=True)
    
    t = len(trades)
    wins = len([x for x in trades if x['outcome'] == 'tp'])
    wr = (wins / t * 100) if t > 0 else 0
    pnl = sum([x['pnl'] for x in trades])
    gp = sum([x['pnl'] for x in trades if x['pnl'] > 0])
    gl = abs(sum([x['pnl'] for x in trades if x['pnl'] < 0]))
    pf = gp/gl if gl > 0 else 999
    
    rows = ""
    for row in trades:
        outcome_class = "success" if row['outcome'] == 'tp' else "danger"
        pnl_class = "success" if row['pnl'] > 0 else ("danger" if row['pnl'] < 0 else "")
        direction_badge = f"<span class='badge {'success' if row['direction'] == 'long' else 'danger'}'>{row['direction'].upper()}</span>"
        
        rows += f"""
        <tr>
            <td>{row['date'].strftime('%Y-%m-%d')}</td>
            <td>{direction_badge}</td>
            <td style="font-family: monospace;">{row['entry']:.2f}</td>
            <td style="font-family: monospace; color: var(--danger);">{row['sl']:.2f}</td>
            <td style="font-family: monospace; color: var(--success);">{row['tp']:.2f}</td>
            <td style="font-family: monospace;">{row['exit_price']:.2f}</td>
            <td class="bold {pnl_class}">${row['pnl']:.2f}</td>
            <td><span class='badge {outcome_class}'>{row['outcome'].upper()}</span></td>
        </tr>
        """
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Sniper Setup: Full Trade Log</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Outfit:wght@600;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #05070a; --surface: #111827; --primary: #3b82f6;
            --text: #f9fafb; --text-muted: #9ca3af; --success: #10b981; --danger: #ef4444;
            --border: #374151;
        }}
        body {{ font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); padding: 3rem 2rem; margin: 0; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ font-family: 'Outfit', sans-serif; font-size: 2.8rem; text-align: center; margin-bottom: 0.5rem; }}
        .subtitle {{ text-align: center; color: var(--text-muted); margin-bottom: 3rem; font-size: 1.1rem; }}
        
        .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.5rem; margin-bottom: 3rem; }}
        .stat-card {{ background: var(--surface); border: 1px solid var(--border); padding: 1.5rem; border-radius: 12px; text-align: center; }}
        .stat-label {{ color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.5rem; display: block; }}
        .stat-val {{ font-family: 'Outfit', sans-serif; font-size: 2.2rem; font-weight: 800; }}
        
        .table-container {{ background: var(--surface); border-radius: 12px; border: 1px solid var(--border); overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 1rem 1.5rem; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; background: rgba(0,0,0,0.2); font-weight: 600; }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover td {{ background: rgba(255,255,255,0.02); }}
        
        .badge {{ padding: 0.35rem 0.75rem; border-radius: 6px; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.5px; }}
        .badge.success {{ background: rgba(16, 185, 129, 0.1); color: var(--success); }}
        .badge.danger {{ background: rgba(239, 68, 68, 0.1); color: var(--danger); }}
        .bold {{ font-weight: 600; }}
        .success {{ color: var(--success); }}
        .danger {{ color: var(--danger); }}
    </style>
</head>
<body>
    <div class="container">
        <h1>The "Sniper" Setup</h1>
        <div class="subtitle">13:00 UTC | Tue & Thu Only | Risk ≤ $3.50 | 1:3 RR | Stop Loss Trailed to Break Candle</div>
        
        <div class="summary-grid">
            <div class="stat-card">
                <span class="stat-label">Win Rate</span>
                <span class="stat-val" style="color: {'var(--success)' if wr >= 40 else 'var(--text)'};">{wr:.1f}%</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Net P&L</span>
                <span class="stat-val success">${pnl:,.0f}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Profit Factor</span>
                <span class="stat-val">{pf:.2f}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Total Trades</span>
                <span class="stat-val">{t}</span>
            </div>
        </div>
        
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Direction</th>
                        <th>Entry Price</th>
                        <th>Stop Loss</th>
                        <th>Take Profit</th>
                        <th>Exit Price</th>
                        <th>P&L</th>
                        <th>Outcome</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>"""
    with open('sniper_setup_log.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Report generated: sniper_setup_log.html")

print("Connecting to MT5...")
mt5.initialize()
rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 100000)
mt5.shutdown()

df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')

nfp_weeks = get_nfp_weeks(df['time'].min().year, df['time'].max().year)

print("Running Sniper Backtest...")
trades = run_sniper_backtest(df.copy(), nfp_weeks)

build_html_report(trades)
