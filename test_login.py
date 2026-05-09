import MetaTrader5 as mt5
import time

login = 256469415
password = "m5qK2LEC"
servers = [f"Exness-MT5Trial{i}" if i > 1 else "Exness-MT5Trial" for i in range(1, 16)]


success = False
for server in servers:
    print(f"Attempting to initialize and login to {server}...")
    if mt5.initialize(login=login, password=password, server=server):
        print(f"Success! Logged in to {server}")
        success = True
        break
    else:
        print(f"Failed for {server}, error code: {mt5.last_error()}")
        mt5.shutdown()
        time.sleep(1)

if not success:
    print("Failed to login to any server.")
else:
    mt5.shutdown()
