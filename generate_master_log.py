import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
from datetime import timedelta

def generate_master_log():
    try:
        # Load the base CSV that contains the Tue-Fri trades (with NFP filter applied)
        df = pd.read_csv('trades_1300.csv')
        df['date'] = pd.to_datetime(df['date'])
        
        # Get the absolute max date to calculate the exactly 1-year cutoff
        max_date = df['date'].max()
        cutoff_date = max_date - pd.DateOffset(years=1)
        
        # Apply 1 Year Filter
        df = df[df['date'] >= cutoff_date]
        
        # Apply Risk <= $4.00 Filter
        df['risk_size'] = abs(df['entry'] - df['sl'])
        df = df[df['risk_size'] <= 4.0]
        
        # Sort chronologically descending for the table
        df = df.sort_values(by='date', ascending=False)
        
        rows = ""
        wins = 0
        for _, row in df.iterrows():
            if row['outcome'] == 'tp': wins += 1
            
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
                <td class="bold {pnl_class}">${row['pnl']:.2f}</td>
                <td><span class='badge {outcome_class}'>{row['outcome'].upper()}</span></td>
            </tr>
            """
            
        t = len(df)
        wr = (wins / t * 100) if t > 0 else 0
        pnl = df['pnl'].sum()
        gp = df[df['pnl'] > 0]['pnl'].sum()
        gl = abs(df[df['pnl'] < 0]['pnl'].sum())
        pf = gp/gl if gl > 0 else 999
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Master Strategy Log (Past 1 Year)</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Outfit:wght@600;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #05070a; --surface: #111827; --primary: #3b82f6;
            --text: #f9fafb; --text-muted: #9ca3af; --success: #10b981; --danger: #ef4444;
            --border: #374151;
        }}
        body {{ font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); padding: 3rem 2rem; margin: 0; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        h1 {{ font-family: 'Outfit', sans-serif; font-size: 2.8rem; text-align: center; margin-bottom: 0.5rem; letter-spacing: -0.5px; }}
        .subtitle {{ color: var(--text-muted); font-size: 1.1rem; text-align: center; margin-bottom: 2rem; }}
        
        .filter-badge {{
            display: block; width: fit-content; margin: 0 auto 3rem;
            background: rgba(59, 130, 246, 0.1); color: var(--primary);
            border: 1px solid rgba(59, 130, 246, 0.3); padding: 0.5rem 1.5rem;
            border-radius: 20px; font-size: 0.95rem; font-weight: 600;
        }}
        
        .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.5rem; margin-bottom: 3rem; }}
        .stat-card {{ background: var(--surface); border: 1px solid var(--border); padding: 1.5rem; border-radius: 12px; text-align: center; }}
        .stat-label {{ color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.5rem; display: block; }}
        .stat-val {{ font-family: 'Outfit', sans-serif; font-size: 2.2rem; font-weight: 800; }}
        
        .table-container {{ background: var(--surface); border-radius: 12px; border: 1px solid var(--border); overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 1.2rem 1.5rem; text-align: left; border-bottom: 1px solid var(--border); }}
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
    <h1>The Master Strategy Playbook</h1>
    <div class="subtitle">13:00 UTC Breakout • 1:3 RR • Exact Stop-Loss Documentation</div>
    <div class="filter-badge">Filter Active: Past 1 Year • Risk ≤ $4.00</div>

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
                    <th>Entry</th>
                    <th>Stop Loss</th>
                    <th>Take Profit</th>
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
</html>
"""
        with open('master_strategy_log.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        print("Generated master_strategy_log.html")
        
    except Exception as e:
        print(f"Error: {e}")

generate_master_log()
