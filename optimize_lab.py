"""
Strategy Optimization Lab — Testing every idea I can think of
Using 13:00 anchor CSV data (the recommended anchor)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np

df = pd.read_csv('trades_1300.csv')
df['date'] = pd.to_datetime(df['date'])
df['month'] = df['date'].dt.to_period('M')
df['dow'] = df['date'].dt.day_name()
df['risk_size'] = abs(df['entry'] - df['sl'])
df['win'] = df['outcome'] == 'tp'
df['year'] = df['date'].dt.year

def stats(sub, label=""):
    t = len(sub)
    if t == 0:
        return None
    w = sub['win'].sum(); wr = w/t*100
    pnl = sub['pnl'].sum()
    gp = sub[sub['pnl']>0]['pnl'].sum()
    gl = abs(sub[sub['pnl']<0]['pnl'].sum())
    pf = gp/gl if gl > 0 else 999
    mp = sub.groupby('month')['pnl'].sum()
    prof_m = (mp > 0).sum()
    # Max drawdown
    cum = sub['pnl'].cumsum()
    dd = (cum.cummax() - cum).max()
    return {'label': label, 'trades': t, 'wr': wr, 'pnl': pnl, 'pf': pf, 
            'pm': f"{prof_m}/{len(mp)}", 'dd': dd, 'per_trade': pnl/t}

def print_stats(s):
    if s is None:
        print("  (no trades)")
        return
    print(f"  {s['label']:<40} {s['trades']:>4}t  {s['wr']:>5.1f}%  ${s['pnl']:>7.0f}  PF={s['pf']:>5.2f}  DD=${s['dd']:>5.0f}  $/trade=${s['per_trade']:>5.1f}")

# ── BASELINE ──
print("=" * 100)
print("  OPTIMIZATION LAB — 13:00 UTC ANCHOR")
print("=" * 100)
print(f"\n{'':>42} {'TR':>4}   {'WR':>5}   {'P&L':>8}  {'PF':>8}  {'MaxDD':>8}  {'$/trade':>9}")
print("-" * 100)
print_stats(stats(df, "BASELINE (no filters)"))

# ── IDEA 1: Day filters ──
print("\n── IDEA 1: Day Filters ──")
for days, label in [
    (['Tuesday', 'Thursday'], "Tue+Thu only"),
    (['Tuesday', 'Wednesday', 'Thursday'], "Tue+Wed+Thu (skip Fri)"),
    (['Tuesday'], "Tuesday only"),
    (['Thursday'], "Thursday only"),
]:
    sub = df[df['dow'].isin(days)]
    print_stats(stats(sub, label))

# ── IDEA 2: Candle size filters ──
print("\n── IDEA 2: Candle Size Filters ──")
for mx in [3.0, 3.5, 4.0, 4.5, 5.0]:
    sub = df[df['risk_size'] <= mx]
    print_stats(stats(sub, f"Max risk <= ${mx:.1f}"))

# Min candle size
print("\n  Minimum candle size:")
for mn in [0.5, 1.0, 1.5, 2.0]:
    sub = df[df['risk_size'] >= mn]
    print_stats(stats(sub, f"Min risk >= ${mn:.1f}"))

# Band filter
print("\n  Band filter (min AND max):")
for mn, mx in [(1.0, 4.0), (1.0, 4.5), (1.0, 5.0), (1.5, 4.0), (1.5, 4.5), (0.5, 3.5)]:
    sub = df[(df['risk_size'] >= mn) & (df['risk_size'] <= mx)]
    print_stats(stats(sub, f"Risk ${mn:.1f}-${mx:.1f}"))

# ── IDEA 3: Direction filter ──
print("\n── IDEA 3: Direction Only ──")
for d in ['long', 'short']:
    sub = df[df['direction'] == d]
    print_stats(stats(sub, f"{d.upper()} only"))

# ── IDEA 4: Combine best filters ──
print("\n── IDEA 4: COMBINATIONS ──")

combos = [
    ("Tue+Thu + risk<=4.5", df[(df['dow'].isin(['Tuesday','Thursday'])) & (df['risk_size'] <= 4.5)]),
    ("Tue+Thu + risk<=4.0", df[(df['dow'].isin(['Tuesday','Thursday'])) & (df['risk_size'] <= 4.0)]),
    ("Tue+Thu + risk<=3.5", df[(df['dow'].isin(['Tuesday','Thursday'])) & (df['risk_size'] <= 3.5)]),
    ("Tue+Wed+Thu + risk<=4.5", df[(df['dow'].isin(['Tuesday','Wednesday','Thursday'])) & (df['risk_size'] <= 4.5)]),
    ("Tue+Wed+Thu + risk<=4.0", df[(df['dow'].isin(['Tuesday','Wednesday','Thursday'])) & (df['risk_size'] <= 4.0)]),
    ("Tue+Thu + risk $1.0-$4.5", df[(df['dow'].isin(['Tuesday','Thursday'])) & (df['risk_size'] >= 1.0) & (df['risk_size'] <= 4.5)]),
    ("Tue+Thu + risk $1.0-$4.0", df[(df['dow'].isin(['Tuesday','Thursday'])) & (df['risk_size'] >= 1.0) & (df['risk_size'] <= 4.0)]),
    ("Tue+Thu + risk $1.5-$4.5", df[(df['dow'].isin(['Tuesday','Thursday'])) & (df['risk_size'] >= 1.5) & (df['risk_size'] <= 4.5)]),
]
for label, sub in combos:
    print_stats(stats(sub, label))

# ── IDEA 5: Time-of-exit analysis (do quick exits = fake breakouts?) ──
print("\n── IDEA 5: Exit Speed Analysis ──")
df['exit_time_dt'] = pd.to_datetime(df['exit_time'])
df['entry_time_est'] = df['date'] + pd.Timedelta(hours=13, minutes=10)  # ~10 min after anchor
df['hold_minutes'] = (df['exit_time_dt'] - df['entry_time_est']).dt.total_seconds() / 60

for label, lo, hi in [
    ("Quick exit (<30min)", 0, 30),
    ("Medium (30-120min)", 30, 120),
    ("Long (120min+)", 120, 9999),
]:
    sub = df[(df['hold_minutes'] >= lo) & (df['hold_minutes'] < hi)]
    if len(sub) > 0:
        wr = sub['win'].mean() * 100
        pnl = sub['pnl'].sum()
        print(f"  {label:<30} {len(sub):>4}t  {wr:>5.1f}%  ${pnl:>7.0f}  (wins mostly {'SL' if wr < 40 else 'TP'})")

# ── IDEA 6: Consecutive loss recovery ──
print("\n── IDEA 6: After a Loss, Should You Still Trade Next Day? ──")
prev_outcome = df['outcome'].shift(1)
after_loss = df[prev_outcome == 'sl']
after_win = df[prev_outcome == 'tp']
print_stats(stats(after_loss, "Trade after a LOSS"))
print_stats(stats(after_win, "Trade after a WIN"))

# 2+ consecutive losses
streak = 0
streaks = []
for i, row in df.iterrows():
    if row['outcome'] == 'sl':
        streak += 1
    else:
        streak = 0
    streaks.append(streak)
df['loss_streak'] = streaks
after_2loss = df[df['loss_streak'].shift(1) >= 2]
after_3loss = df[df['loss_streak'].shift(1) >= 3]
print_stats(stats(after_2loss, "Trade after 2+ consecutive losses"))
print_stats(stats(after_3loss, "Trade after 3+ consecutive losses"))

# ── IDEA 7: Month-of-year seasonality ──
print("\n── IDEA 7: Seasonality (which calendar months to avoid) ──")
df['cal_month'] = df['date'].dt.month
for m in range(1, 13):
    sub = df[df['cal_month'] == m]
    if len(sub) > 0:
        wr = sub['win'].mean() * 100
        pnl = sub['pnl'].sum()
        mn = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m-1]
        flag = " << SKIP?" if pnl <= 0 else ""
        print(f"  {mn:<5} {len(sub):>3}t  {wr:>5.1f}%  ${pnl:>7.0f}{flag}")

# ── GRAND FINALE: Best combo ──
print("\n\n" + "=" * 100)
print("  TOP 5 SETUPS RANKED BY PROFIT FACTOR")
print("=" * 100)

all_setups = []
# Re-run all combos and collect
setups = {
    "BASELINE": df,
    "Risk <= $4.5": df[df['risk_size'] <= 4.5],
    "Risk <= $4.0": df[df['risk_size'] <= 4.0],
    "Risk <= $3.5": df[df['risk_size'] <= 3.5],
    "Tue+Thu": df[df['dow'].isin(['Tuesday','Thursday'])],
    "Skip Fri": df[df['dow'].isin(['Tuesday','Wednesday','Thursday'])],
    "Tue+Thu + risk<=4.5": df[(df['dow'].isin(['Tuesday','Thursday'])) & (df['risk_size'] <= 4.5)],
    "Tue+Thu + risk<=4.0": df[(df['dow'].isin(['Tuesday','Thursday'])) & (df['risk_size'] <= 4.0)],
    "Tue+Thu + risk<=3.5": df[(df['dow'].isin(['Tuesday','Thursday'])) & (df['risk_size'] <= 3.5)],
    "Skip Fri + risk<=4.5": df[(df['dow'].isin(['Tuesday','Wednesday','Thursday'])) & (df['risk_size'] <= 4.5)],
    "Skip Fri + risk<=4.0": df[(df['dow'].isin(['Tuesday','Wednesday','Thursday'])) & (df['risk_size'] <= 4.0)],
    "Risk $1.0-$4.0": df[(df['risk_size'] >= 1.0) & (df['risk_size'] <= 4.0)],
    "Tue+Thu + risk $1-$4": df[(df['dow'].isin(['Tuesday','Thursday'])) & (df['risk_size'] >= 1.0) & (df['risk_size'] <= 4.0)],
}

results = []
for label, sub in setups.items():
    s = stats(sub, label)
    if s and s['trades'] >= 20:  # minimum sample
        results.append(s)

results.sort(key=lambda x: x['pf'], reverse=True)
print(f"\n{'':>42} {'TR':>4}   {'WR':>5}   {'P&L':>8}  {'PF':>8}  {'MaxDD':>8}  {'$/trade':>9}")
print("-" * 100)
for s in results[:8]:
    print_stats(s)
