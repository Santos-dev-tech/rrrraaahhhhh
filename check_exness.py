import MetaTrader5 as mt5

t_path = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
if mt5.initialize(path=t_path, timeout=60000):
    info = mt5.account_info()
    if info:
        print(f"Logged in as: {info.login}")
        print(f"Server: {info.server}")
        print(f"Balance: {info.balance}")
    else:
        print("No active account or failed to get info.")
    mt5.shutdown()
else:
    print("Init failed.")
