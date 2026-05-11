import pandas as pd
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import final_comparison as fc

SYMBOL = "XAUUSDm"
CPI_DATES = fc.CPI_DATES

mt5.initialize()
rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 100000)
mt5.shutdown()

df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')

nfp_weeks = fc.get_nfp_weeks(df['time'].min().year, df['time'].max().year)
cpi_weeks = fc.get_cpi_weeks(CPI_DATES)

trades_1300 = fc.run_backtest(df.copy(), nfp_weeks, set(CPI_DATES), cpi_weeks, 13, 0)
trades_1255 = fc.run_backtest(df.copy(), nfp_weeks, set(CPI_DATES), cpi_weeks, 12, 55)

def analyze_trades(trades, strat_name):
    cpi_pnl, nfp_pnl, reg_pnl = 0, 0, 0
    cpi_count, nfp_count, reg_count = 0, 0, 0
    for t in trades:
        date = t['date']
        if date in cpi_weeks:
            cpi_pnl += t['pnl']
            cpi_count += 1
        elif date in nfp_weeks:
            nfp_pnl += t['pnl']
            nfp_count += 1
        else:
            reg_pnl += t['pnl']
            reg_count += 1

    print(f"--- {strat_name} Strategy ---")
    print(f"Total CPI Week PnL: ${cpi_pnl:.2f} (Trades: {cpi_count})")
    print(f"Total NFP Week PnL: ${nfp_pnl:.2f} (Trades: {nfp_count})")
    print(f"Total Reg Week PnL: ${reg_pnl:.2f} (Trades: {reg_count})")

analyze_trades(trades_1300, "13:00")
analyze_trades(trades_1255, "12:55")
