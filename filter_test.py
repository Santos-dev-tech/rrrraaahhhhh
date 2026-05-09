import pandas as pd

# ── 1. CANDLE SIZE FILTER TEST (12:55 anchor) ──
df = pd.read_csv('trades_1255.csv')
df['date'] = pd.to_datetime(df['date'])
df['risk_size'] = abs(df['entry'] - df['sl'])
df['win'] = df['outcome'] == 'tp'

print("=" * 60)
print("  1. CANDLE SIZE FILTER TEST (12:55 UTC)")
print("=" * 60)

thresholds = [3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 999]
print(f"{'Max Risk':<10} {'Trades':>6} {'Skipped':>8} {'WR%':>6} {'P&L':>9} {'PF':>6}")
print("-" * 50)
for th in thresholds:
    filtered = df[df['risk_size'] <= th] if th < 999 else df
    t = len(filtered)
    skipped = len(df) - t
    w = filtered['win'].sum()
    wr = w / t * 100 if t else 0
    pnl = filtered['pnl'].sum()
    gp = filtered[filtered['pnl'] > 0]['pnl'].sum()
    gl = abs(filtered[filtered['pnl'] < 0]['pnl'].sum())
    pf = gp / gl if gl > 0 else 999
    label = "NO FILTER" if th == 999 else f"<=${th:.1f}"
    print(f"{label:<10} {t:>6} {skipped:>8} {wr:>5.1f}% ${pnl:>7.0f} {pf:>5.2f}")

# Monthly breakdown with $4.50 filter
print("\n\nMONTHLY with $4.50 filter vs NO filter (12:55):")
print(f"{'Month':<10} {'Orig WR':>8} {'Orig P&L':>9} {'Filt WR':>8} {'Filt P&L':>9} {'Skipped':>8}")
print("-" * 60)
df['month'] = df['date'].dt.to_period('M')
for month, grp in df.groupby('month'):
    t1 = len(grp); w1 = grp['win'].sum(); wr1 = w1/t1*100
    pnl1 = grp['pnl'].sum()
    filt = grp[grp['risk_size'] <= 4.5]
    t2 = len(filt); w2 = filt['win'].sum(); wr2 = w2/t2*100 if t2 else 0
    pnl2 = filt['pnl'].sum()
    skip = t1 - t2
    better = " ++" if pnl2 > pnl1 else (" ==" if pnl2 == pnl1 else "")
    print(f"{str(month):<10} {wr1:>6.1f}% ${pnl1:>7.0f} {wr2:>6.1f}% ${pnl2:>7.0f} {skip:>8}{better}")

# ── 2. ALL ANCHORS IN 2026 ──
print("\n\n" + "=" * 60)
print("  2. WHICH ANCHOR IS BEST IN 2026?")
print("=" * 60)

anchors = {'12:55': 'trades_1255.csv', '13:00': 'trades_1300.csv', '13:30': 'trades_1330.csv'}
print(f"\n{'Anchor':<8} {'Trades':>6} {'Wins':>5} {'WR%':>6} {'P&L':>9} {'PF':>6}")
print("-" * 45)
for name, file in anchors.items():
    d = pd.read_csv(file)
    d['date'] = pd.to_datetime(d['date'])
    d2026 = d[d['date'].dt.year == 2026]
    t = len(d2026); w = len(d2026[d2026['outcome'] == 'tp'])
    wr = w/t*100 if t else 0; pnl = d2026['pnl'].sum()
    gp = d2026[d2026['pnl'] > 0]['pnl'].sum()
    gl = abs(d2026[d2026['pnl'] < 0]['pnl'].sum())
    pf = gp / gl if gl > 0 else 999
    print(f"{name:<8} {t:>6} {w:>5} {wr:>5.1f}% ${pnl:>7.0f} {pf:>5.2f}")

# 2026 monthly per anchor
print(f"\n2026 MONTHLY PER ANCHOR:")
print(f"{'Month':<10} {'12:55':>12} {'13:00':>12} {'13:30':>12}")
print("-" * 50)
for m in ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05']:
    row = f"{m:<10}"
    for name, file in anchors.items():
        d = pd.read_csv(file)
        d['date'] = pd.to_datetime(d['date'])
        d['month'] = d['date'].dt.to_period('M')
        mg = d[d['month'].astype(str) == m]
        if len(mg) == 0:
            row += f"{'--':>12}"
        else:
            wr = mg[mg['outcome']=='tp'].shape[0] / len(mg) * 100
            pnl = mg['pnl'].sum()
            row += f" {wr:.0f}%/${pnl:.0f}".rjust(12)
        
    print(row)

# ── 3. 2026 WITH CANDLE FILTER PER ANCHOR ──
print(f"\n2026 WITH $4.50 FILTER PER ANCHOR:")
print(f"{'Anchor':<8} {'Trades':>6} {'Wins':>5} {'WR%':>6} {'P&L':>9} {'PF':>6}")
print("-" * 45)
for name, file in anchors.items():
    d = pd.read_csv(file)
    d['date'] = pd.to_datetime(d['date'])
    d['risk_size'] = abs(d['entry'] - d['sl'])
    d2026 = d[(d['date'].dt.year == 2026) & (d['risk_size'] <= 4.5)]
    t = len(d2026); w = len(d2026[d2026['outcome'] == 'tp'])
    wr = w/t*100 if t else 0; pnl = d2026['pnl'].sum()
    gp = d2026[d2026['pnl'] > 0]['pnl'].sum()
    gl = abs(d2026[d2026['pnl'] < 0]['pnl'].sum())
    pf = gp / gl if gl > 0 else 999
    print(f"{name:<8} {t:>6} {w:>5} {wr:>5.1f}% ${pnl:>7.0f} {pf:>5.2f}")
