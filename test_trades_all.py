import json
import os
import subprocess
import json as sys_json
import time

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

print("Initiating test trades on all accounts...\n")

for acct in accounts:
    if "nextlevelfunded" in acct['server'].lower():
        print(f"=== Skipping Account: {acct['login']} (Next Level Funded) ===")
        print("  [SKIPPED]: Server name is a URL. Needs proper MT5 Server Name.\n")
        continue

    print(f"=== Testing Account: {acct['login']} ({acct.get('name', 'Unknown')}) ===")
    t_path = get_terminal_path(acct['server'])
    
    payload = {
        "terminal_path": t_path,
        "login": acct['login'],
        "password": acct.get('password', ''),
        "server": acct['server'],
        "is_test": True
    }
    
    try:
        proc = subprocess.run(
            ["py", "executor.py"],
            input=sys_json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=130
        )
        if proc.stdout:
            try:
                res = sys_json.loads(proc.stdout.strip())
                if "error" in res:
                    print(f"  [FAILED]: {res['error']}")
                else:
                    print(f"  [SUCCESS]: {res.get('message', 'Trade executed!')}")
                    print(f"     Open Price: {res.get('open_price')} | Close Price: {res.get('close_price')}")
                    print(f"     PnL: ${res.get('pnl_approx')}")
            except Exception as e:
                print(f"  [Parse Error]: {e}\n  Raw Output: {proc.stdout}")
        else:
            print(f"  [Execution Failed]: {proc.stderr}")
    except Exception as e:
        print(f"  [Script Error]: {str(e)}")
    print("")
    time.sleep(2)
