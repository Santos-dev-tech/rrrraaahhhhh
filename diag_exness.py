import MetaTrader5 as mt5
import pandas as pd

if not mt5.initialize():
    print("initialize() failed")
    quit()

symbol_name = "XAUUSDm"
if mt5.symbol_info("XAUUSD") is not None:
    symbol_name = "XAUUSD"

mt5.symbol_select(symbol_name, True)

print(f"Testing max candles for {symbol_name}...")
counts = [50000, 100000, 200000, 300000, 500000, 1000000, 5000000]

max_got = 0
for c in counts:
    r = mt5.copy_rates_from_pos(symbol_name, mt5.TIMEFRAME_M5, 0, c)
    if r is not None:
        print(f"Requested {c:,}: Got {len(r):,}")
        max_got = max(max_got, len(r))
    else:
        print(f"Requested {c:,}: Failed. Error: {mt5.last_error()}")

print(f"Absolute max available right now: {max_got:,}")
mt5.shutdown()
