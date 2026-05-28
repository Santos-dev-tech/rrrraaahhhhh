"""
Test trade execution on both accounts.
- Blue Guardian (439530): MT5 API direct -- open 0.01, wait 5s, close
- MavenTrade (10295233): GUI automation -- press F9, then Esc
"""
import json
import subprocess
import sys
import os
import io

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ACCOUNTS = [
    {
        "name": "Blue Guardian",
        "login": 439530,
        "password": "",
        "server": "BlueGuardian-Server",
        "terminal_path": r"C:\Program Files\Blue Guardian MT5 Terminal\terminal64.exe",
        "executor": "executor.py",
        "timeout": 130,
    },
    {
        "name": "MavenTrade",
        "login": 10295233,
        "password": "",
        "server": "MavenTrade",
        "terminal_path": r"C:\Program Files\MetaTrader 5\terminal64.exe",
        "executor": "gui_executor.py",
        "timeout": 130,
    },
]

def test_account(acct):
    print(f"\n{'='*60}")
    print(f"  TESTING: {acct['name']} (#{acct['login']})")
    print(f"  Executor: {acct['executor']}")
    print(f"{'='*60}")

    payload = {
        "terminal_path": acct["terminal_path"],
        "login": acct["login"],
        "password": acct["password"],
        "server": acct["server"],
        "is_test": True,
    }

    script_path = os.path.join(BASE_DIR, acct["executor"])
    if not os.path.exists(script_path):
        print(f"  [FAIL] Executor script not found: {script_path}")
        return False

    try:
        proc = subprocess.run(
            ["py", script_path],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=acct["timeout"],
            cwd=BASE_DIR,
        )

        stdout = proc.stdout.strip() if proc.stdout else ""
        stderr = proc.stderr.strip() if proc.stderr else ""

        if stderr:
            print(f"  [!]  stderr: {stderr[:300]}")

        if stdout:
            try:
                result = json.loads(stdout)
                print(f"  [>] Result: {json.dumps(result, indent=2)}")

                if "error" in result:
                    print(f"  [FAIL] FAILED: {result['error']}")
                    return False
                elif result.get("status") == "Success":
                    print(f"  [OK] PASSED  -  {result.get('message', 'Trade executed')}")
                    if "pnl_approx" in result:
                        print(f"     Open: {result.get('open_price')} → Close: {result.get('close_price')} | PnL: {result['pnl_approx']}")
                    return True
                else:
                    print(f"  [!]  Unknown status: {result}")
                    return False
            except json.JSONDecodeError:
                print(f"  [FAIL] Invalid JSON output: {stdout[:200]}")
                return False
        else:
            print(f"  [FAIL] No output from executor")
            return False

    except subprocess.TimeoutExpired:
        print(f"  [FAIL] TIMEOUT after {acct['timeout']}s")
        return False
    except Exception as e:
        print(f"  [FAIL] EXCEPTION: {e}")
        return False


if __name__ == "__main__":
    print("[*] XAUUSD AutoPilot  -  Test Trade on Both Accounts")
    print(f"   Working dir: {BASE_DIR}")
    
    results = {}
    for acct in ACCOUNTS:
        results[acct["name"]] = test_account(acct)

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    for name, passed in results.items():
        status = "[OK] PASS" if passed else "[FAIL] FAIL"
        print(f"  {name}: {status}")
    
    all_passed = all(results.values())
    print(f"\n  Overall: {'[OK] ALL GOOD' if all_passed else '[FAIL] ISSUES DETECTED'}")
    sys.exit(0 if all_passed else 1)
