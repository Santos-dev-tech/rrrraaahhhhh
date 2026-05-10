import MetaTrader5 as mt5
import time
from datetime import datetime

def main():
    print("Initializing MT5 connection...")
    if not mt5.initialize():
        print(f"Failed to initialize MT5. Error: {mt5.last_error()}")
        return

    # Determine correct symbol
    symbol = "XAUUSDm"
    if mt5.symbol_info("XAUUSD") is not None:
        symbol = "XAUUSD"
        
    print(f"Target symbol: {symbol}")
    
    # Select symbol
    if not mt5.symbol_select(symbol, True):
        print(f"Failed to select {symbol}. Error: {mt5.last_error()}")
        mt5.shutdown()
        return

    print("Fetching live tick data...")
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        tick_time = datetime.fromtimestamp(tick.time).strftime("%Y-%m-%d %H:%M:%S")
        print(f"Live {symbol} Data @ {tick_time} -> Bid: {tick.bid:.2f} | Ask: {tick.ask:.2f} | Spread: {(tick.ask - tick.bid)*100:.1f} points")
    else:
        print(f"Failed to get tick data. Error: {mt5.last_error()}")
        
    mt5.shutdown()

if __name__ == "__main__":
    main()
