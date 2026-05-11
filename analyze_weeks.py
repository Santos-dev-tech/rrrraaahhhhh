import pandas as pd
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import final_comparison as fc

SYMBOL = "XAUUSDm"

mt5.initialize()
rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 100000)
mt5.shutdown()

df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')

nfp_weeks = fc.get_nfp_weeks(df['time'].min().year, df['time'].max().year)
cpi_weeks = fc.get_cpi_weeks(fc.CPI_DATES)

trades_1255 = fc.run_backtest(df.copy(), nfp_weeks, set(fc.CPI_DATES), cpi_weeks, 12, 55)

def get_week_of_month(date_obj):
    day = date_obj.day
    if day <= 7: return "Week 1 (Days 1-7)"
    elif day <= 14: return "Week 2 (Days 8-14)"
    elif day <= 21: return "Week 3 (Days 15-21)"
    elif day <= 28: return "Week 4 (Days 22-28)"
    else: return "Week 5 (Days 29-31)"

stats = {
    "Week 1 (Days 1-7)": {"pnl": 0, "count": 0},
    "Week 2 (Days 8-14)": {"pnl": 0, "count": 0},
    "Week 3 (Days 15-21)": {"pnl": 0, "count": 0},
    "Week 4 (Days 22-28)": {"pnl": 0, "count": 0},
    "Week 5 (Days 29-31)": {"pnl": 0, "count": 0},
}

for t in trades_1255:
    date = t['date']
    week_lbl = get_week_of_month(date)
    stats[week_lbl]['pnl'] += t['pnl']
    stats[week_lbl]['count'] += 1

print("--- 12:55 Strategy Profitability by Week of Month ---")
for k, v in stats.items():
    avg = v['pnl'] / v['count'] if v['count'] > 0 else 0
    print(f"{k:<20} : Total PnL = ${v['pnl']:8.2f} | Trades = {v['count']:<3} | Avg PnL/Trade = ${avg:6.2f}")
