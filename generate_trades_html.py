import pandas as pd
from datetime import timedelta

def generate_table_rows(csv_file, cutoff_date):
    try:
        df = pd.read_csv(csv_file)
        df['date'] = pd.to_datetime(df['date'])
        
        # Filter for exact past 1 year
        df = df[df['date'] >= cutoff_date]
        
        # Filter: Skip trades where anchor risk > $4.00
        df['risk_size'] = abs(df['entry'] - df['sl'])
        df = df[df['risk_size'] <= 4.0]
        
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
                <td style="font-family: monospace;">{row['sl']:.2f}</td>
                <td style="font-family: monospace;">{row['tp']:.2f}</td>
                <td class="bold {pnl_class}">${row['pnl']:.2f}</td>
                <td><span class='badge {outcome_class}'>{row['outcome'].upper()}</span></td>
            </tr>
            """
            
        total_trades = len(df)
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        total_pnl = df['pnl'].sum()
        
        return rows, total_trades, total_pnl, win_rate
    except Exception as e:
        return f"<tr><td colspan='7'>Error loading {csv_file}: {e}</td></tr>", 0, 0, 0

# First pass to find the absolute max date across both to determine "exactly 1 year" accurately
df1 = pd.read_csv('trades_1300.csv')
df2 = pd.read_csv('trades_1255.csv')
df1['date'] = pd.to_datetime(df1['date'])
df2['date'] = pd.to_datetime(df2['date'])
max_date = max(df1['date'].max(), df2['date'].max())
cutoff_date = max_date - pd.DateOffset(years=1)

rows_1300, count_1300, pnl_1300, wr_1300 = generate_table_rows('trades_1300.csv', cutoff_date)
rows_1255, count_1255, pnl_1255, wr_1255 = generate_table_rows('trades_1255.csv', cutoff_date)

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Filtered Trade Logs (Past 1 Year)</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Outfit:wght@600;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #05070a;
            --surface: #111827;
            --surface-hover: #1f2937;
            --primary: #3b82f6;
            --text: #f9fafb;
            --text-muted: #9ca3af;
            --success: #10b981;
            --danger: #ef4444;
            --border: #374151;
        }}
        body {{
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 3rem 2rem;
            line-height: 1.5;
        }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        
        .header {{ text-align: center; margin-bottom: 3rem; }}
        h1 {{ font-family: 'Outfit', sans-serif; font-size: 2.5rem; margin-bottom: 0.5rem; letter-spacing: -0.5px; }}
        .subtitle {{ color: var(--text-muted); font-size: 1.1rem; }}
        
        .filter-badge {{
            display: inline-block;
            background: rgba(59, 130, 246, 0.1);
            color: var(--primary);
            border: 1px solid rgba(59, 130, 246, 0.3);
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 600;
            margin-top: 1rem;
        }}
        
        .tabs {{ display: flex; justify-content: center; gap: 1rem; margin-bottom: 2rem; }}
        .tab-btn {{
            background: var(--surface);
            color: var(--text-muted);
            border: 1px solid var(--border);
            padding: 0.75rem 2rem;
            border-radius: 30px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 600;
            transition: all 0.3s ease;
        }}
        .tab-btn.active {{
            background: rgba(59, 130, 246, 0.1);
            border-color: var(--primary);
            color: var(--primary);
            box-shadow: 0 0 15px rgba(59, 130, 246, 0.2);
        }}
        .tab-btn:hover:not(.active) {{ background: var(--surface-hover); color: var(--text); }}
        
        .tab-content {{ display: none; animation: fadeIn 0.4s ease; }}
        .tab-content.active {{ display: block; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}
        
        .stat-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 1.5rem;
            border-radius: 12px;
            text-align: center;
        }}
        .stat-label {{ color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.5rem; display: block; }}
        .stat-val {{ font-family: 'Outfit', sans-serif; font-size: 2.2rem; font-weight: 800; }}
        
        .table-container {{
            background: var(--surface);
            border-radius: 12px;
            border: 1px solid var(--border);
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 1.2rem 1.5rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            color: var(--text-muted);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            background: rgba(0,0,0,0.2);
            font-weight: 600;
        }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover td {{ background: rgba(255,255,255,0.02); }}
        
        .badge {{
            padding: 0.35rem 0.75rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.5px;
        }}
        .badge.success {{ background: rgba(16, 185, 129, 0.1); color: var(--success); }}
        .badge.danger {{ background: rgba(239, 68, 68, 0.1); color: var(--danger); }}
        .bold {{ font-weight: 600; }}
        .success {{ color: var(--success); }}
        .danger {{ color: var(--danger); }}
    </style>
</head>
<body>

<div class="container">
    <div class="header">
        <h1>Raw Trade Logs (1:3 RR)</h1>
        <div class="subtitle">Filtered exactly for the past 1 Year ({cutoff_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')})</div>
        <div class="filter-badge">Filter Active: Risk ≤ $4.00</div>
    </div>

    <div class="tabs">
        <button class="tab-btn active" onclick="showTab('tab-1300')">13:00 UTC Anchor</button>
        <button class="tab-btn" onclick="showTab('tab-1255')">12:55 UTC Anchor</button>
    </div>

    <!-- 13:00 TAB -->
    <div id="tab-1300" class="tab-content active">
        <div class="summary-grid">
            <div class="stat-card">
                <span class="stat-label">Win Rate</span>
                <span class="stat-val" style="color: {'var(--success)' if wr_1300 >= 40 else 'var(--text)'};">{wr_1300:.1f}%</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Net P&L</span>
                <span class="stat-val success">${pnl_1300:,.0f}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Total Trades</span>
                <span class="stat-val">{count_1300}</span>
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
                    {rows_1300}
                </tbody>
            </table>
        </div>
    </div>

    <!-- 12:55 TAB -->
    <div id="tab-1255" class="tab-content">
        <div class="summary-grid">
            <div class="stat-card">
                <span class="stat-label">Win Rate</span>
                <span class="stat-val" style="color: {'var(--success)' if wr_1255 >= 40 else 'var(--text)'};">{wr_1255:.1f}%</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Net P&L</span>
                <span class="stat-val success">${pnl_1255:,.0f}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Total Trades</span>
                <span class="stat-val">{count_1255}</span>
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
                    {rows_1255}
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

with open('trades_1_year_log_filtered.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

print("Generated trades_1_year_log_filtered.html")
