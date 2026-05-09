import MetaTrader5 as mt5
import pandas as pd

mt5.initialize()
mt5.symbol_select('XAUUSD', True)

for c in [10, 100, 1000, 5000, 10000, 50000]:
    r = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M5, 0, c)
    if r is not None:
        df = pd.DataFrame(r)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        print(f"{c}: {len(r)} candles | {df['time'].min()} to {df['time'].max()}")
    else:
        print(f"{c}: NONE - {mt5.last_error()}")

mt5.shutdown()
