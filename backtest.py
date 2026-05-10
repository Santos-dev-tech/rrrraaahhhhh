"""
XAUUSD 5-Min Breakout Backtester
Tests anchor times: 12:55, 13:00, 13:30 UTC
Strategy: Break of anchor candle H/L within 2 candles, 1:3 RR
Filters: No Mondays, NFP week = Tuesday only
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import sys

# ── CONFIG ──────────────────────────────────────────────────────────
SYMBOL = "XAUUSDm"  # Exness micro symbol, change to "XAUUSD" if needed
ANCHOR_TIMES = ["12:55", "13:00", "13:30"]
YEARS_BACK = 5
SL_BUFFER = 0.50  # $ buffer below/above break candle for SL
RR_RATIO = 3.0    # Risk:Reward = 1:3
EOD_CLOSE_HOUR = 21  # Close open trades at 21:00 UTC
RISK_PER_TRADE = 30  # Fixed $30 risk per trade
POINT_VALUE = 100  # $100 per $1 move per lot for XAUUSD


def get_nfp_weeks(start_year, end_year):
    """Get all NFP weeks (week containing first Friday of each month)."""
    nfp_weeks = set()
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            first_day = datetime(year, month, 1)
            # Find first Friday
            days_until_friday = (4 - first_day.weekday()) % 7
            first_friday = first_day + timedelta(days=days_until_friday)
            # Get the Monday of that week
            monday = first_friday - timedelta(days=first_friday.weekday())
            for d in range(5):  # Mon-Fri
                nfp_weeks.add((monday + timedelta(days=d)).date())
    return nfp_weeks


def is_valid_trading_day(dt, nfp_weeks):
    """Check if this day is valid for trading."""
    day = dt.weekday()
    date = dt.date()
    if day == 0:  # Monday - never trade
        return False
    if date in nfp_weeks:
        return day == 1  # NFP week: only Tuesday
    return True


def run_backtest(df, anchor_time_str, nfp_weeks):
    """Run backtest for a single anchor time."""
    hour, minute = map(int, anchor_time_str.split(":"))
    trades = []
    
    # Group by date
    df['date'] = df['time'].dt.date
    dates = df['date'].unique()
    
    for date in dates:
        day_data = df[df['date'] == date].copy()
        if day_data.empty:
            continue
        
        sample_dt = day_data.iloc[0]['time']
        if not is_valid_trading_day(sample_dt, nfp_weeks):
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
        
        # Get next 2 candles
        remaining = day_data.iloc[anchor_idx + 1:]
        if len(remaining) < 2:
            continue
        
        next_two = remaining.iloc[:2]
        
        # Check for break within 2 candles
        direction = None
        break_candle = None
        
        for _, candle in next_two.iterrows():
            broke_high = candle['high'] > anchor_high
            broke_low = candle['low'] < anchor_low
            
            if broke_high and broke_low:
                # Both broken - use candle direction
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
        
        # Calculate entry, SL, TP
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
        
        # Walk forward to find outcome
        break_idx = day_data.index.get_loc(break_candle.name)
        forward = day_data.iloc[break_idx + 1:]
        
        # Also check next day if needed (get all data after break)
        forward_all = df[df.index > break_candle.name]
        
        outcome = 'open'
        exit_price = None
        exit_time = None
        
        for _, fcandle in forward_all.iterrows():
            # EOD close check
            if fcandle['time'].hour >= EOD_CLOSE_HOUR and fcandle['time'].date() == date:
                outcome = 'eod_close'
                exit_price = fcandle['close']
                exit_time = fcandle['time']
                break
            
            if direction == 'long':
                if fcandle['low'] <= sl:
                    outcome = 'sl'
                    exit_price = sl
                    exit_time = fcandle['time']
                    break
                if fcandle['high'] >= tp:
                    outcome = 'tp'
                    exit_price = tp
                    exit_time = fcandle['time']
                    break
            else:
                if fcandle['high'] >= sl:
                    outcome = 'sl'
                    exit_price = sl
                    exit_time = fcandle['time']
                    break
                if fcandle['low'] <= tp:
                    outcome = 'tp'
                    exit_price = tp
                    exit_time = fcandle['time']
                    break
        
        if outcome == 'open':
            continue
        
        # Calculate P&L with fixed $30 risk sizing
        lot_size = RISK_PER_TRADE / (risk * POINT_VALUE)
        if direction == 'long':
            pnl = (exit_price - entry) * POINT_VALUE * lot_size
        else:
            pnl = (entry - exit_price) * POINT_VALUE * lot_size
        
        trades.append({
            'date': str(date),
            'day': sample_dt.strftime('%A'),
            'anchor_time': anchor_time_str,
            'direction': direction,
            'entry': round(entry, 2),
            'sl': round(sl, 2),
            'tp': round(tp, 2),
            'exit_price': round(exit_price, 2),
            'risk_dollars': RISK_PER_TRADE,
            'pnl': round(pnl, 2),
            'rr_achieved': round(pnl / RISK_PER_TRADE, 2) if RISK_PER_TRADE > 0 else 0,
            'outcome': outcome,
            'exit_time': str(exit_time),
        })
    
    return trades


def calc_stats(trades):
    """Calculate performance statistics."""
    if not trades:
        return {'total_trades': 0}
    
    df = pd.DataFrame(trades)
    wins = df[df['outcome'] == 'tp']
    losses = df[df['outcome'] == 'sl']
    eod = df[df['outcome'] == 'eod_close']
    
    total_pnl = df['pnl'].sum()
    win_rate = len(wins) / len(df) * 100
    
    # Max drawdown
    cumulative = df['pnl'].cumsum()
    peak = cumulative.cummax()
    drawdown = peak - cumulative
    max_dd = drawdown.max()
    
    # Profit factor
    gross_profit = wins['pnl'].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses['pnl'].sum()) if len(losses) > 0 else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Consecutive wins/losses
    outcomes = df['outcome'].tolist()
    max_consec_win = max_consec_loss = consec_win = consec_loss = 0
    for o in outcomes:
        if o == 'tp':
            consec_win += 1
            consec_loss = 0
        elif o == 'sl':
            consec_loss += 1
            consec_win = 0
        else:
            consec_win = consec_loss = 0
        max_consec_win = max(max_consec_win, consec_win)
        max_consec_loss = max(max_consec_loss, consec_loss)
    
    # Monthly breakdown
    df['month'] = pd.to_datetime(df['date']).dt.to_period('M')
    monthly = df.groupby('month')['pnl'].sum()
    profitable_months = (monthly > 0).sum()
    
    return {
        'total_trades': len(df),
        'wins': len(wins),
        'losses': len(losses),
        'eod_closes': len(eod),
        'win_rate': round(win_rate, 1),
        'total_pnl': round(total_pnl, 2),
        'avg_win': round(wins['pnl'].mean(), 2) if len(wins) > 0 else 0,
        'avg_loss': round(losses['pnl'].mean(), 2) if len(losses) > 0 else 0,
        'profit_factor': round(profit_factor, 2),
        'max_drawdown': round(max_dd, 2),
        'max_consec_wins': max_consec_win,
        'max_consec_losses': max_consec_loss,
        'avg_risk': round(df['risk_dollars'].mean(), 2),
        'profitable_months': int(profitable_months),
        'total_months': len(monthly),
        'best_month': round(monthly.max(), 2),
        'worst_month': round(monthly.min(), 2),
    }


def generate_html_report(all_results):
    """Generate HTML report comparing all anchor times."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>XAUUSD Breakout Backtest Report</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#e0e0e0;font-family:'Segoe UI',sans-serif;padding:20px}
h1{text-align:center;font-size:28px;background:linear-gradient(135deg,#f0b90b,#f5d442);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:5px}
.subtitle{text-align:center;color:#888;margin-bottom:30px;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:20px;margin-bottom:30px}
.card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:20px}
.card h2{font-size:18px;color:#f0b90b;margin-bottom:15px;display:flex;align-items:center;gap:8px}
.winner{border-color:#f0b90b;box-shadow:0 0 20px rgba(240,185,11,0.15)}
.badge{background:#f0b90b;color:#000;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:700}
.stat-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)}
.stat-row:last-child{border:none}
.stat-label{color:#888;font-size:13px}
.stat-value{font-weight:600;font-size:14px}
.positive{color:#00c853}
.negative{color:#ff1744}
.neutral{color:#ffc107}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:10px}
th{background:rgba(240,185,11,0.1);color:#f0b90b;padding:8px;text-align:left;position:sticky;top:0}
td{padding:6px 8px;border-bottom:1px solid rgba(255,255,255,0.04)}
tr:hover{background:rgba(255,255,255,0.03)}
.tp{color:#00c853}.sl{color:#ff1744}.eod{color:#ffc107}
.trades-section{max-height:500px;overflow-y:auto;margin-top:20px}
.summary-bar{display:flex;justify-content:center;gap:40px;margin:20px 0;padding:15px;background:rgba(240,185,11,0.05);border-radius:12px}
.summary-item{text-align:center}
.summary-item .val{font-size:24px;font-weight:700}
.summary-item .lbl{font-size:12px;color:#888}
</style>
</head>
<body>
<h1>⚡ XAUUSD Breakout Backtest</h1>
<p class="subtitle">5-Min TF | 1:3 RR | No Mondays | NFP Week = Tue Only | SL Buffer: $""" + str(SL_BUFFER) + """</p>
"""
    
    # Find best anchor time by total PnL
    best_anchor = max(all_results.keys(), key=lambda k: all_results[k]['stats'].get('total_pnl', 0))
    
    # Data range info
    html += f'<p class="subtitle">Data range: {all_results[list(all_results.keys())[0]].get("data_range", "N/A")}</p>'
    
    # Summary comparison bar
    html += '<div class="summary-bar">'
    for anchor, data in all_results.items():
        s = data['stats']
        pnl_class = 'positive' if s.get('total_pnl', 0) > 0 else 'negative'
        winner = ' 🏆' if anchor == best_anchor else ''
        html += f'''<div class="summary-item">
            <div class="val {pnl_class}">${s.get('total_pnl', 0):,.0f}</div>
            <div class="lbl">{anchor} UTC{winner}</div>
        </div>'''
    html += '</div>'
    
    # Cards for each anchor time
    html += '<div class="grid">'
    for anchor, data in all_results.items():
        s = data['stats']
        is_winner = anchor == best_anchor
        card_class = 'card winner' if is_winner else 'card'
        badge = '<span class="badge">BEST</span>' if is_winner else ''
        
        if s['total_trades'] == 0:
            html += f'<div class="{card_class}"><h2>{anchor} UTC {badge}</h2><p>No trades found</p></div>'
            continue
        
        pnl_class = 'positive' if s['total_pnl'] > 0 else 'negative'
        wr_class = 'positive' if s['win_rate'] > 40 else 'negative'
        pf_class = 'positive' if s['profit_factor'] > 1 else 'negative'
        
        html += f'''<div class="{card_class}">
        <h2>{anchor} UTC {badge}</h2>
        <div class="stat-row"><span class="stat-label">Total Trades</span><span class="stat-value">{s['total_trades']}</span></div>
        <div class="stat-row"><span class="stat-label">Wins / Losses / EOD</span><span class="stat-value">{s['wins']} / {s['losses']} / {s['eod_closes']}</span></div>
        <div class="stat-row"><span class="stat-label">Win Rate</span><span class="stat-value {wr_class}">{s['win_rate']}%</span></div>
        <div class="stat-row"><span class="stat-label">Total P&L (1 lot)</span><span class="stat-value {pnl_class}">${s['total_pnl']:,.2f}</span></div>
        <div class="stat-row"><span class="stat-label">Avg Win / Avg Loss</span><span class="stat-value">${s['avg_win']:,.2f} / ${s['avg_loss']:,.2f}</span></div>
        <div class="stat-row"><span class="stat-label">Profit Factor</span><span class="stat-value {pf_class}">{s['profit_factor']}</span></div>
        <div class="stat-row"><span class="stat-label">Max Drawdown</span><span class="stat-value negative">${s['max_drawdown']:,.2f}</span></div>
        <div class="stat-row"><span class="stat-label">Max Consec Wins / Losses</span><span class="stat-value">{s['max_consec_wins']} / {s['max_consec_losses']}</span></div>
        <div class="stat-row"><span class="stat-label">Avg Risk per Trade</span><span class="stat-value">${s['avg_risk']:,.2f}</span></div>
        <div class="stat-row"><span class="stat-label">Profitable Months</span><span class="stat-value">{s['profitable_months']} / {s['total_months']}</span></div>
        <div class="stat-row"><span class="stat-label">Best / Worst Month</span><span class="stat-value">${s['best_month']:,.2f} / ${s['worst_month']:,.2f}</span></div>
        </div>'''
    html += '</div>'
    
    # Trade logs for each anchor
    for anchor, data in all_results.items():
        trades = data['trades']
        if not trades:
            continue
        html += f'''<div class="card" style="margin-bottom:20px">
        <h2>📋 Trade Log — {anchor} UTC ({len(trades)} trades)</h2>
        <div class="trades-section"><table>
        <tr><th>Date</th><th>Day</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>Exit</th><th>P&L</th><th>Result</th></tr>'''
        for t in trades:
            res_class = 'tp' if t['outcome'] == 'tp' else ('sl' if t['outcome'] == 'sl' else 'eod')
            res_label = t['outcome'].upper()
            pnl_class = 'positive' if t['pnl'] > 0 else 'negative'
            html += f'''<tr>
            <td>{t['date']}</td><td>{t['day'][:3]}</td><td>{t['direction'].upper()}</td>
            <td>{t['entry']}</td><td>{t['sl']}</td><td>{t['tp']}</td><td>{t['exit_price']}</td>
            <td class="{pnl_class}">${t['pnl']:,.2f}</td><td class="{res_class}">{res_label}</td></tr>'''
        html += '</table></div></div>'
    
    html += '</body></html>'
    return html


def main():
    print("=" * 60)
    print("  XAUUSD Breakout Backtester — AUTO PILOT")
    print("=" * 60)
    
    # Initialize MT5
    # Initialize MT5
    if not mt5.initialize():
        print(f"\n❌ MT5 failed to initialize: {mt5.last_error()}")
        print("\nMake sure MetaTrader 5 is installed and running.")
        print("If using Exness, download MT5 from: https://www.exness.com/mt5/")
        sys.exit(1)
    
    print(f"✅ MT5 connected: {mt5.terminal_info().name}")
    print(f"   Account: {mt5.account_info().login}")
    print(f"   Server: {mt5.account_info().server}")
    
    # Check symbol
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        # Try alternative names
        alternatives = ["XAUUSD", "XAUUSDm", "XAUUSD.", "GOLD", "GOLDm"]
        found = False
        for alt in alternatives:
            if mt5.symbol_info(alt) is not None:
                print(f"   Symbol '{SYMBOL}' not found, using '{alt}'")
                globals()['SYMBOL'] = alt  # won't work, use local
                found = True
                symbol_name = alt
                break
        if not found:
            print(f"❌ Symbol not found. Available gold symbols:")
            symbols = mt5.symbols_get()
            for s in symbols:
                if 'XAU' in s.name.upper() or 'GOLD' in s.name.upper():
                    print(f"   - {s.name}")
            mt5.shutdown()
            sys.exit(1)
    else:
        symbol_name = SYMBOL
    
    # Enable symbol
    mt5.symbol_select(symbol_name, True)
    
    # Download 5-min data — max available from MT5 chart
    MAX_CANDLES = 100000
    print(f"\n[>] Downloading M5 data for {symbol_name} (up to {MAX_CANDLES:,} candles)...")
    
    rates = mt5.copy_rates_from_pos(symbol_name, mt5.TIMEFRAME_M5, 0, MAX_CANDLES)
    
    if rates is None or len(rates) == 0:
        print(f"[X] No data received: {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    actual_start = df['time'].min()
    actual_end = df['time'].max()
    actual_days = (actual_end - actual_start).days
    
    print(f"✅ Got {len(df):,} candles")
    print(f"   Actual range: {actual_start.date()} → {actual_end.date()} ({actual_days} days)")
    
    # Pre-compute NFP weeks
    nfp_weeks = get_nfp_weeks(actual_start.year, actual_end.year)
    
    # Run backtests
    all_results = {}
    data_range = f"{actual_start.date()} to {actual_end.date()}"
    
    for anchor_time in ANCHOR_TIMES:
        print(f"\n⏳ Backtesting anchor: {anchor_time} UTC...")
        trades = run_backtest(df.copy(), anchor_time, nfp_weeks)
        stats = calc_stats(trades)
        all_results[anchor_time] = {
            'trades': trades,
            'stats': stats,
            'data_range': data_range,
        }
        print(f"   → {stats['total_trades']} trades | "
              f"WR: {stats.get('win_rate', 0)}% | "
              f"P&L: ${stats.get('total_pnl', 0):,.2f} | "
              f"PF: {stats.get('profit_factor', 0)}")
    
    # Generate report
    report_path = os.path.join(os.path.dirname(__file__), "backtest_report.html")
    html = generate_html_report(all_results)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    # Also save raw trades as CSV for each anchor
    for anchor, data in all_results.items():
        if data['trades']:
            csv_path = os.path.join(os.path.dirname(__file__), f"trades_{anchor.replace(':', '')}.csv")
            pd.DataFrame(data['trades']).to_csv(csv_path, index=False)
    
    print(f"\n{'=' * 60}")
    print(f"✅ Report saved: {report_path}")
    print(f"✅ Trade CSVs saved for manual verification")
    print(f"{'=' * 60}")
    
    # Print winner
    best = max(all_results.keys(), key=lambda k: all_results[k]['stats'].get('total_pnl', 0))
    print(f"\n🏆 BEST ANCHOR TIME: {best} UTC")
    print(f"   Total P&L: ${all_results[best]['stats']['total_pnl']:,.2f}")
    print(f"   Win Rate: {all_results[best]['stats']['win_rate']}%")
    print(f"   Profit Factor: {all_results[best]['stats']['profit_factor']}")
    
    mt5.shutdown()


if __name__ == "__main__":
    main()
