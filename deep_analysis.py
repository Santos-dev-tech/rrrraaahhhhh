"""
Deep analysis: WHY does the 12:55 breakout strategy work, and WHY does it fail?
"""
import pandas as pd
import numpy as np

df = pd.read_csv('trades_1255.csv')
df['date'] = pd.to_datetime(df['date'])
df['month'] = df['date'].dt.to_period('M')
df['dow'] = df['date'].dt.day_name()
df['win'] = df['outcome'] == 'tp'
df['loss'] = df['outcome'] == 'sl'
df['risk_size'] = abs(df['entry'] - df['sl'])  # proxy for anchor candle volatility

print("=" * 65)
print("  DEEP ANALYSIS: WHY DOES 12:55 BREAKOUT WORK / FAIL?")
print("=" * 65)

# ── 1. DIRECTION ANALYSIS ──
print("\n\n1. DIRECTION BIAS (Long vs Short)")
print("-" * 50)
for d in ['long', 'short']:
    grp = df[df['direction'] == d]
    t = len(grp); w = grp['win'].sum(); wr = w/t*100 if t else 0
    pnl = grp['pnl'].sum()
    print(f"  {d.upper():<6}  {t:>3} trades  {wr:>5.1f}% WR  ${pnl:>8.0f} P&L")

# ── 2. DIRECTION x MONTH (which direction kills you?) ──
print("\n\n2. DIRECTION x MONTH (where do losses come from?)")
print("-" * 65)
print(f"{'MONTH':<10} {'L_TR':>4} {'L_WR':>6} {'L_PNL':>8}  {'S_TR':>4} {'S_WR':>6} {'S_PNL':>8}")
for month, grp in df.groupby('month'):
    for d in ['long', 'short']:
        sub = grp[grp['direction'] == d]
        t = len(sub); w = sub['win'].sum(); wr = w/t*100 if t else 0
        pnl = sub['pnl'].sum()
        if d == 'long':
            row = f"{str(month):<10} {t:>4} {wr:>5.1f}% ${pnl:>7.0f}"
        else:
            row += f"  {t:>4} {wr:>5.1f}% ${pnl:>7.0f}"
    bad = " << BAD" if grp['pnl'].sum() <= 0 else ""
    print(row + bad)

# ── 3. DAY OF WEEK ANALYSIS ──
print("\n\n3. DAY OF WEEK")
print("-" * 50)
day_order = ['Tuesday', 'Wednesday', 'Thursday', 'Friday']
for day in day_order:
    grp = df[df['dow'] == day]
    t = len(grp); w = grp['win'].sum(); wr = w/t*100 if t else 0
    pnl = grp['pnl'].sum()
    avg_risk = grp['risk_size'].mean()
    print(f"  {day:<10}  {t:>3}t  {wr:>5.1f}% WR  ${pnl:>7.0f}  avg_risk=${avg_risk:.2f}")

# ── 4. ANCHOR CANDLE SIZE (volatility proxy) vs WIN RATE ──
print("\n\n4. ANCHOR CANDLE SIZE vs WIN RATE (does big = bad?)")
print("-" * 50)
df['risk_q'] = pd.qcut(df['risk_size'], 4, labels=['Small', 'Medium', 'Large', 'XLarge'])
for q in ['Small', 'Medium', 'Large', 'XLarge']:
    grp = df[df['risk_q'] == q]
    t = len(grp); w = grp['win'].sum(); wr = w/t*100 if t else 0
    pnl = grp['pnl'].sum()
    rng = f"${grp['risk_size'].min():.2f}-${grp['risk_size'].max():.2f}"
    print(f"  {q:<8} ({rng:<16})  {t:>3}t  {wr:>5.1f}% WR  ${pnl:>7.0f}")

# ── 5. OUTCOME DISTRIBUTION: TP vs SL vs EOD ──
print("\n\n5. OUTCOME BREAKDOWN")
print("-" * 50)
for o in ['tp', 'sl', 'eod_close']:
    grp = df[df['outcome'] == o]
    pnl = grp['pnl'].sum()
    print(f"  {o:<10}  {len(grp):>3} ({len(grp)/len(df)*100:.1f}%)  ${pnl:>8.0f}")

# ── 6. EOD CLOSES: are they hurting or helping? ──
print("\n\n6. EOD CLOSE ANALYSIS (trades that didn't hit TP or SL)")
print("-" * 50)
eod = df[df['outcome'] == 'eod_close']
if len(eod) > 0:
    eod_pos = eod[eod['pnl'] > 0]
    eod_neg = eod[eod['pnl'] < 0]
    eod_zero = eod[eod['pnl'] == 0]
    print(f"  Total EOD closes: {len(eod)}")
    print(f"  Profitable: {len(eod_pos)} (avg ${eod_pos['pnl'].mean():.0f})" if len(eod_pos) else "  Profitable: 0")
    print(f"  Losing:     {len(eod_neg)} (avg ${eod_neg['pnl'].mean():.0f})" if len(eod_neg) else "  Losing: 0")
    print(f"  Net EOD P&L: ${eod['pnl'].sum():.0f}")

# ── 7. CONSECUTIVE LOSS STREAKS ──
print("\n\n7. LOSS STREAKS")
print("-" * 50)
streak = 0; max_streak = 0; streak_start = None; worst_start = None; worst_end = None
for i, row in df.iterrows():
    if row['outcome'] == 'sl':
        if streak == 0:
            streak_start = row['date']
        streak += 1
        if streak > max_streak:
            max_streak = streak
            worst_start = streak_start
            worst_end = row['date']
    else:
        streak = 0
print(f"  Max consecutive losses: {max_streak}")
print(f"  Worst streak: {worst_start.strftime('%Y-%m-%d')} to {worst_end.strftime('%Y-%m-%d')}")

# ── 8. BAD MONTHS: WHAT'S DIFFERENT? ──
print("\n\n8. BAD vs GOOD MONTHS COMPARISON")
print("-" * 50)
monthly = df.groupby('month').agg(
    trades=('pnl', 'count'),
    wr=('win', 'mean'),
    pnl=('pnl', 'sum'),
    avg_risk=('risk_size', 'mean'),
    long_pct=('direction', lambda x: (x == 'long').mean()),
    eod_pct=('outcome', lambda x: (x == 'eod_close').mean()),
).reset_index()

good = monthly[monthly['pnl'] > 200]
bad = monthly[monthly['pnl'] <= 0]

print(f"  {'Metric':<20} {'Good Months':>12} {'Bad Months':>12}")
print(f"  {'Avg WR':<20} {good['wr'].mean()*100:>11.1f}% {bad['wr'].mean()*100:>11.1f}%")
print(f"  {'Avg Risk (candle)':<20} ${good['avg_risk'].mean():>10.2f} ${bad['avg_risk'].mean():>10.2f}")
print(f"  {'Long %':<20} {good['long_pct'].mean()*100:>11.1f}% {bad['long_pct'].mean()*100:>11.1f}%")
print(f"  {'EOD Close %':<20} {good['eod_pct'].mean()*100:>11.1f}% {bad['eod_pct'].mean()*100:>11.1f}%")

# ── 9. LONG vs SHORT WIN RATE IN BAD MONTHS ──
print("\n\n9. BAD MONTHS DRILL-DOWN")
print("-" * 50)
bad_months = ['2025-03', '2025-09', '2026-04']
for m in bad_months:
    grp = df[df['month'].astype(str) == m]
    if len(grp) == 0:
        continue
    longs = grp[grp['direction'] == 'long']
    shorts = grp[grp['direction'] == 'short']
    l_wr = longs['win'].mean()*100 if len(longs) else 0
    s_wr = shorts['win'].mean()*100 if len(shorts) else 0
    print(f"  {m}: {len(longs)}L ({l_wr:.0f}% WR) / {len(shorts)}S ({s_wr:.0f}% WR) | Net ${grp['pnl'].sum():.0f}")
    # Show each trade outcome
    for _, t in grp.iterrows():
        icon = "W" if t['win'] else ("L" if t['loss'] else "E")
        print(f"    {t['date'].strftime('%m-%d')} {t['day'][:3]} {t['direction']:<5} {icon}  ${t['pnl']:>6.0f}  risk=${t['risk_size']:.2f}")
