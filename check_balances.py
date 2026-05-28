import MetaTrader5 as mt5
import json
import os

accounts_file = r'c:\Users\ADMIN\OneDrive\Documents\GitHub\rrrraaahhhhh\accounts.json'
with open(accounts_file, 'r') as f:
    accounts = json.load(f)

def get_terminal_path(server_name):
    server_lower = server_name.lower()
    if "blueguardian" in server_lower:
        return r"C:\Program Files\Blue Guardian MT5 Terminal\terminal64.exe"
    elif "fundednext" in server_lower or "nlf" in server_lower or "next level" in server_lower or "nextlevel" in server_lower:
        return r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
    else:
        return r"C:\Program Files\MetaTrader 5\terminal64.exe"

print("Checking balances...")
for acct in accounts:
    t_path = get_terminal_path(acct['server'])
    print(f"\nTerminal: {t_path}")
    print(f"Account: {acct['login']} ({acct['name']})")
    
    if not mt5.initialize(path=t_path, timeout=60000):
        print(f"  Init failed: {mt5.last_error()}")
        continue
    
    # Login if we have a password
    if acct.get('password'):
        print(f"  Attempting login for {acct['login']} with password...")
        if not mt5.login(acct['login'], password=acct['password'], server=acct['server']):
            print(f"  Login failed: {mt5.last_error()}")
            mt5.shutdown()
            continue
    else:
        print("  Skipping login (no password in config, relying on terminal state)...")
    
    info = mt5.account_info()
    if info:
        print(f"  Login successful! Actual Login ID: {info.login}")
        print(f"  Balance: {info.balance}")
        print(f"  Equity: {info.equity}")
    else:
        print(f"  Failed to get account info: {mt5.last_error()}")
    mt5.shutdown()
