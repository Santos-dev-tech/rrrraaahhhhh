"""Test trade execution on ALL accounts - open 0.01 lot, wait, close."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import json
import subprocess
import time
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, 'accounts.json')

def get_terminal_path(server_name):
    s = server_name.lower()
    if "blueguardian" in s:
        return r"C:\Program Files\Blue Guardian MT5 Terminal\terminal64.exe"
    elif "fundednext" in s or "nlf" in s or "nextlevel" in s:
        return r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
    else:
        return r"C:\Program Files\MetaTrader 5\terminal64.exe"

def get_executor(server_name):
    s = server_name.lower()
    if "nextlevelfunded" in s or "nlf" in s:
        return "matchtrader_executor.py"
    elif "maven" in s:
        return "gui_executor.py"
    return "executor.py"

def run_test(acct):
    name = acct.get('name', f"#{acct['login']}")
    executor = get_executor(acct['server'])
    t_path = get_terminal_path(acct['server'])
    timeout = 330 if executor != "executor.py" else 130

    payload = {
        "terminal_path": t_path,
        "login": acct['login'],
        "password": acct.get('password', ''),
        "server": acct['server'],
        "is_test": True
    }

    print(f"\n{'='*60}")
    print(f"  TESTING: {name}")
    print(f"  Login: {acct['login']} | Server: {acct['server']}")
    print(f"  Executor: {executor} | Timeout: {timeout}s")
    print(f"{'='*60}")

    try:
        proc = subprocess.run(
            ["py", executor],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=timeout,
            cwd=BASE_DIR
        )
        if proc.stdout:
            try:
                res = json.loads(proc.stdout.strip())
                if "error" in res:
                    print(f"  [FAIL]: {res['error']}")
                else:
                    print(f"  [OK]: {res.get('message', res.get('status', 'OK'))}")
                    if 'volume' in res: print(f"     Volume: {res['volume']}")
                    if 'open_price' in res: print(f"     Open: {res['open_price']}")
                    if 'close_price' in res: print(f"     Close: {res['close_price']}")
                    if 'pnl_approx' in res: print(f"     PnL: ${res['pnl_approx']}")
                return res
            except json.JSONDecodeError:
                print(f"  [FAIL] Bad output: {proc.stdout[:200]}")
        else:
            print(f"  [FAIL] No output. Stderr: {proc.stderr[:300]}")
        return {"error": proc.stderr[:300]}
    except subprocess.TimeoutExpired:
        print(f"  [FAIL] TIMEOUT after {timeout}s")
        return {"error": "timeout"}
    except Exception as e:
        print(f"  [FAIL] ERROR: {e}")
        return {"error": str(e)}


if __name__ == '__main__':
    with open(ACCOUNTS_FILE, 'r') as f:
        accounts = json.load(f)

    print(f"\n>> Testing {len(accounts)} accounts...\n")

    results = {}
    for acct in accounts:
        res = run_test(acct)
        results[acct['login']] = res
        time.sleep(2)

    print(f"\n\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for login, res in results.items():
        status = "[OK]" if res and res.get('status') == 'Success' else "[FAIL]"
        msg = res.get('message', res.get('error', 'Unknown'))
        print(f"  {status} #{login}: {msg}")
    print()
