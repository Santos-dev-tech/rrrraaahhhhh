import pandas as pd

df = pd.read_csv('trades_1255.csv')
df['date'] = pd.to_datetime(df['date'])
df['month'] = df['date'].dt.to_period('M')

print("MONTH     TR  WIN   WR%       P&L")
print("-" * 40)
for month, grp in df.groupby('month'):
    t = len(grp)
    w = len(grp[grp['outcome'] == 'tp'])
    wr = w / t * 100
    pnl = grp['pnl'].sum()
    flag = ' << BAD' if wr < 33 else ''
    print(f"{str(month)}  {t:>3}  {w:>3}  {wr:>5.1f}%  ${pnl:>8.0f}{flag}")

total_wr = len(df[df['outcome'] == 'tp']) / len(df) * 100
print("-" * 40)
print(f"TOTAL    {len(df):>3}   --  {total_wr:>5.1f}%  ${df['pnl'].sum():>8.0f}")
