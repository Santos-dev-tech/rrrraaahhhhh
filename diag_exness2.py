import MetaTrader5 as mt5
from datetime import datetime, timedelta

if not mt5.initialize():
    print("initialize() failed")
    quit()

symbol_name = "XAUUSDm"
if mt5.symbol_info("XAUUSD") is not None:
    symbol_name = "XAUUSD"

mt5.symbol_select(symbol_name, True)

print(f"Testing max candles for {symbol_name} using dates...")

end_date = datetime.now()
start_date = end_date - timedelta(days=365*5) # 5 years

r = mt5.copy_rates_range(symbol_name, mt5.TIMEFRAME_M5, start_date, end_date)
if r is not None:
    print(f"Requested 5 years: Got {len(r):,} candles")
else:
    print(f"Requested 5 years: Failed. Error: {mt5.last_error()}")

mt5.shutdown()
