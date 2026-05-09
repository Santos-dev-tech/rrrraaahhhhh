import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
from datetime import timedelta

def process_trades(csv_file, cutoff_date):
    try:
        df = pd.read_csv(csv_file)
        df['date'] = pd.to_datetime(df['date'])
        
        # Apply 1 Year Filter
        df = df[df['date'] >= cutoff_date]
        
        # Apply Risk <= $4.00 Filter
        df['risk_size'] = abs(df['entry'] - df['sl'])
        df = df[df['risk_size'] <= 4.0]
        
        # Sort chronologically descending
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
        
        return rows, wr, pnl, pf, t
    except Exception as e:
        print(f"Error processing {csv_file}: {e}")
        return "", 0, 0, 0, 0

def generate_master_log():
    # Load base CSVs to find global max date for exact 1-year cutoff
    df1 = pd.read_csv('trades_1300.csv')
    df2 = pd.read_csv('trades_1255.csv')
    df1['date'] = pd.to_datetime(df1['date'])
    df2['date'] = pd.to_datetime(df2['date'])
    max_date = max(df1['date'].max(), df2['date'].max())
    cutoff_date = max_date - pd.DateOffset(years=1)
    
    # Process both anchors
    rows_13, wr_13, pnl_13, pf_13, t_13 = process_trades('trades_1300.csv', cutoff_date)
    rows_12, wr_12, pnl_12, pf_12, t_12 = process_trades('trades_1255.csv', cutoff_date)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Master Strategy Log (Past 1 Year)</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Outfit:wght@600;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #05070a; --surface: #111827; --surface-hover: #1f2937; --primary: #3b82f6;
            --text: #f9fafb; --text-muted: #9ca3af; --success: #10b981; --danger: #ef4444;
            --border: #374151;
        }}
        body {{ font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); padding: 3rem 2rem; margin: 0; }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        h1 {{ font-family: 'Outfit', sans-serif; font-size: 2.8rem; text-align: center; margin-bottom: 0.5rem; letter-spacing: -0.5px; }}
        .subtitle {{ color: var(--text-muted); font-size: 1.1rem; text-align: center; margin-bottom: 2rem; }}
        
        .filter-badge {{
            display: block; width: fit-content; margin: 0 auto 3rem;
            background: rgba(59, 130, 246, 0.1); color: var(--primary);
            border: 1px solid rgba(59, 130, 246, 0.3); padding: 0.5rem 1.5rem;
            border-radius: 20px; font-size: 0.95rem; font-weight: 600;
        }}
        
        .tabs {{ display: flex; justify-content: center; gap: 1rem; margin-bottom: 2rem; }}
        .tab-btn {{
            background: var(--surface); color: var(--text-muted); border: 1px solid var(--border);
            padding: 0.75rem 2rem; border-radius: 30px; cursor: pointer; font-size: 1rem; font-weight: 600;
            transition: all 0.3s ease;
        }}
        .tab-btn.active {{
            background: rgba(59, 130, 246, 0.1); border-color: var(--primary); color: var(--primary);
            box-shadow: 0 0 15px rgba(59, 130, 246, 0.2);
        }}
        .tab-btn:hover:not(.active) {{ background: var(--surface-hover); color: var(--text); }}
        
        .tab-content {{ display: none; animation: fadeIn 0.4s ease; }}
        .tab-content.active {{ display: block; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        
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
    <div class="subtitle">1:3 RR • Exact Stop-Loss Documentation</div>
    <div class="filter-badge">Filters Active: Past 1 Year • Risk ≤ $4.00</div>

    <div class="tabs">
        <button class="tab-btn active" onclick="showTab('tab-1300')">13:00 UTC Anchor</button>
        <button class="tab-btn" onclick="showTab('tab-1255')">12:55 UTC Anchor</button>
    </div>

    <!-- 13:00 TAB -->
    <div id="tab-1300" class="tab-content active">
        <div class="summary-grid">
            <div class="stat-card">
                <span class="stat-label">Win Rate</span>
                <span class="stat-val" style="color: {'var(--success)' if wr_13 >= 40 else 'var(--text)'};">{wr_13:.1f}%</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Net P&L</span>
                <span class="stat-val success">${pnl_13:,.0f}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Profit Factor</span>
                <span class="stat-val">{pf_13:.2f}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Total Trades</span>
                <span class="stat-val">{t_13}</span>
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
                    {rows_13}
                </tbody>
            </table>
        </div>
    </div>

    <!-- 12:55 TAB -->
    <div id="tab-1255" class="tab-content">
        <div class="summary-grid">
            <div class="stat-card">
                <span class="stat-label">Win Rate</span>
                <span class="stat-val" style="color: {'var(--success)' if wr_12 >= 40 else 'var(--text)'};">{wr_12:.1f}%</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Net P&L</span>
                <span class="stat-val success">${pnl_12:,.0f}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Profit Factor</span>
                <span class="stat-val">{pf_12:.2f}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Total Trades</span>
                <span class="stat-val">{t_12}</span>
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
                    {rows_12}
                </tbody>
            </table>
        </div>
    </div>
</div>

<script>
    function showTab(tabId) {{
        document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
        
        document.getElementById(tabId).classList.add('active');
        event.currentTarget.classList.add('active');
    }}
</script>

</body>
</html>
"""
    with open('master_strategy_log.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    print("Generated master_strategy_log.html")

generate_master_log()
