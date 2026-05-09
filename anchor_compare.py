import pandas as pd
import numpy as np

# Load all three anchors
anchors = {
    '12:55': pd.read_csv('trades_1255.csv'),
    '13:00': pd.read_csv('trades_1300.csv'),
    '13:30': pd.read_csv('trades_1330.csv'),
}
for name, d in anchors.items():
    d['date'] = pd.to_datetime(d['date'])
    d['month'] = d['date'].dt.to_period('M')
    d['risk_size'] = abs(d['entry'] - d['sl'])
    d['win'] = d['outcome'] == 'tp'
    d['year'] = d['date'].dt.year

# ── 1. WHY DID 13:00 FLIP IN 2026? ──
print("=" * 65)
print("  WHY 13:00 OVERTOOK 12:55 IN 2026")
print("=" * 65)

print("\nAVG CANDLE SIZE BY YEAR:")
for name in ['12:55', '13:00']:
    d = anchors[name]
    for yr in [2025, 2026]:
        sub = d[d['year'] == yr]
        if len(sub) == 0: continue
        print(f"  {name} | {yr}: avg risk=${sub['risk_size'].mean():.2f}, median=${sub['risk_size'].median():.2f}, trades={len(sub)}")

print("\nCANDLE SIZE DISTRIBUTION 2026:")
for name in ['12:55', '13:00']:
    d = anchors[name]
    d26 = d[d['year'] == 2026]
    small = len(d26[d26['risk_size'] <= 3.5])
    med = len(d26[(d26['risk_size'] > 3.5) & (d26['risk_size'] <= 5.0)])
    big = len(d26[d26['risk_size'] > 5.0])
    print(f"  {name}: Small(<=3.5)={small}, Med(3.5-5)={med}, Big(>5)={big}  total={len(d26)}")

# ── 2. HEAD-TO-HEAD: SAME DAYS ──
print("\n\n" + "=" * 65)
print("  HEAD-TO-HEAD: SAME DAYS COMPARISON (2026)")
print("=" * 65)

d1 = anchors['12:55'][anchors['12:55']['year'] == 2026][['date', 'outcome', 'pnl', 'risk_size', 'direction']].copy()
d2 = anchors['13:00'][anchors['13:00']['year'] == 2026][['date', 'outcome', 'pnl', 'risk_size', 'direction']].copy()
d1.columns = ['date', 'out_1255', 'pnl_1255', 'risk_1255', 'dir_1255']
d2.columns = ['date', 'out_1300', 'pnl_1300', 'risk_1300', 'dir_1300']
merged = pd.merge(d1, d2, on='date', how='inner')

both_win = len(merged[(merged['out_1255'] == 'tp') & (merged['out_1300'] == 'tp')])
only_1255 = len(merged[(merged['out_1255'] == 'tp') & (merged['out_1300'] != 'tp')])
only_1300 = len(merged[(merged['out_1300'] == 'tp') & (merged['out_1255'] != 'tp')])
both_lose = len(merged[(merged['out_1255'] == 'sl') & (merged['out_1300'] == 'sl')])
diff_dir = len(merged[merged['dir_1255'] != merged['dir_1300']])

print(f"  Days both traded: {len(merged)}")
print(f"  Both win:    {both_win}")
print(f"  Only 12:55 wins: {only_1255}")
print(f"  Only 13:00 wins: {only_1300}")
print(f"  Both lose:   {both_lose}")
print(f"  Different direction: {diff_dir}/{len(merged)}")

print("\n  When they disagree on direction:")
disagree = merged[merged['dir_1255'] != merged['dir_1300']]
for _, r in disagree.iterrows():
    w1 = "W" if r['out_1255'] == 'tp' else "L"
    w2 = "W" if r['out_1300'] == 'tp' else "L"
    print(f"    {r['date'].strftime('%m-%d')} 12:55={r['dir_1255'][:1].upper()}/{w1}  13:00={r['dir_1300'][:1].upper()}/{w2}")

# ── 3. ROLLING 3-MONTH PERFORMANCE ──
print("\n\n" + "=" * 65)
print("  ROLLING 3-MONTH WINDOWS (which anchor is trending?)")
print("=" * 65)

all_months = sorted(set(
    list(anchors['12:55']['month'].unique()) + 
    list(anchors['13:00']['month'].unique())
))

print(f"\n{'Window':<20} {'12:55 P&L':>10} {'13:00 P&L':>10} {'Winner':>10}")
print("-" * 55)
for i in range(len(all_months) - 2):
    window = [all_months[i], all_months[i+1], all_months[i+2]]
    label = f"{window[0]}-{window[2]}"
    pnls = {}
    for name in ['12:55', '13:00']:
        d = anchors[name]
        sub = d[d['month'].isin(window)]
        pnls[name] = sub['pnl'].sum()
    winner = '12:55' if pnls['12:55'] > pnls['13:00'] else '13:00'
    arrow = '<<<' if winner == '13:00' else ''
    print(f"{label:<20} ${pnls['12:55']:>8.0f} ${pnls['13:00']:>8.0f} {winner:>10} {arrow}")

# ── 4. RECENT MOMENTUM (last 6 months) ──
print("\n\n" + "=" * 65)
print("  LAST 6 MONTHS (Nov 2025 - May 2026)")
print("=" * 65)
recent_months = all_months[-7:]  # roughly last 6-7
for name in ['12:55', '13:00', '13:30']:
    d = anchors[name]
    sub = d[d['month'].isin(recent_months)]
    t = len(sub); w = sub['win'].sum(); wr = w/t*100 if t else 0
    pnl = sub['pnl'].sum()
    gp = sub[sub['pnl'] > 0]['pnl'].sum()
    gl = abs(sub[sub['pnl'] < 0]['pnl'].sum())
    pf = gp / gl if gl > 0 else 999
    print(f"  {name}: {t}t, {wr:.1f}% WR, ${pnl:.0f} P&L, {pf:.2f} PF")

# With filter
print("\n  WITH $4.50 FILTER:")
for name in ['12:55', '13:00', '13:30']:
    d = anchors[name]
    sub = d[(d['month'].isin(recent_months)) & (d['risk_size'] <= 4.5)]
    t = len(sub); w = sub['win'].sum(); wr = w/t*100 if t else 0
    pnl = sub['pnl'].sum()
    gp = sub[sub['pnl'] > 0]['pnl'].sum()
    gl = abs(sub[sub['pnl'] < 0]['pnl'].sum())
    pf = gp / gl if gl > 0 else 999
    print(f"  {name}: {t}t, {wr:.1f}% WR, ${pnl:.0f} P&L, {pf:.2f} PF")

# ── 5. CONSISTENCY: how many months profitable? ──
print("\n\n" + "=" * 65)
print("  CONSISTENCY: PROFITABLE MONTHS")
print("=" * 65)
for name in ['12:55', '13:00']:
    d = anchors[name]
    monthly_pnl = d.groupby('month')['pnl'].sum()
    prof = (monthly_pnl > 0).sum()
    total = len(monthly_pnl)
    neg_months = monthly_pnl[monthly_pnl <= 0]
    print(f"\n  {name}: {prof}/{total} months profitable ({prof/total*100:.0f}%)")
    print(f"  Losing months: {', '.join([str(m) for m in neg_months.index])}")
    print(f"  Worst month: {neg_months.idxmin()} (${neg_months.min():.0f})" if len(neg_months) else "  No losing months")

# ── 6. FINAL VERDICT STATS ──
print("\n\n" + "=" * 65)
print("  FINAL COMPARISON TABLE")
print("=" * 65)
print(f"\n{'Metric':<25} {'12:55':>12} {'13:00':>12}")
print("-" * 50)

metrics = []
for name in ['12:55', '13:00']:
    d = anchors[name]
    t = len(d); w = d['win'].sum(); pnl = d['pnl'].sum()
    gp = d[d['pnl']>0]['pnl'].sum(); gl = abs(d[d['pnl']<0]['pnl'].sum())
    
    d26 = d[d['year'] == 2026]
    t26 = len(d26); w26 = d26['win'].sum(); pnl26 = d26['pnl'].sum()
    
    mp = d.groupby('month')['pnl'].sum()
    prof_m = (mp > 0).sum()
    
    metrics.append({
        'all_wr': w/t*100, 'all_pnl': pnl, 'all_pf': gp/gl if gl else 999,
        '2026_wr': w26/t26*100 if t26 else 0, '2026_pnl': pnl26,
        'prof_months': f"{prof_m}/{len(mp)}",
        'worst': mp.min(),
    })

rows = [
    ('All-time WR', f"{metrics[0]['all_wr']:.1f}%", f"{metrics[1]['all_wr']:.1f}%"),
    ('All-time P&L', f"${metrics[0]['all_pnl']:.0f}", f"${metrics[1]['all_pnl']:.0f}"),
    ('All-time PF', f"{metrics[0]['all_pf']:.2f}", f"{metrics[1]['all_pf']:.2f}"),
    ('2026 WR', f"{metrics[0]['2026_wr']:.1f}%", f"{metrics[1]['2026_wr']:.1f}%"),
    ('2026 P&L', f"${metrics[0]['2026_pnl']:.0f}", f"${metrics[1]['2026_pnl']:.0f}"),
    ('Profitable months', metrics[0]['prof_months'], metrics[1]['prof_months']),
    ('Worst month', f"${metrics[0]['worst']:.0f}", f"${metrics[1]['worst']:.0f}"),
]
for label, v1, v2 in rows:
    print(f"{label:<25} {v1:>12} {v2:>12}")
