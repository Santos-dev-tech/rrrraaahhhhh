import sys
import json
import time

def execute_trade(req):
    try:
        import pyautogui
        import pygetwindow as gw
    except ImportError:
        return {"error": "Dependencies not installed. Run: pip install pyautogui pygetwindow"}
    import subprocess
    import os

    direction = req.get('direction', 'Long')
    sl = req.get('sl', 0)
    tp = req.get('tp', 0)
    server = req.get('server', '').lower()
    is_test = req.get('is_test', False)
    risk_amt = req.get('risk_amount', 4.0)

    # Calculate lot size
    if not is_test and sl > 0:
        entry_guess = req.get('entry_price', 0)
        if entry_guess == 0:
            lot_size = "0.01"
        else:
            sl_dist = abs(entry_guess - float(sl)) * 100
            lot_size = str(round((float(risk_amt) / sl_dist), 2)) if sl_dist > 0 else "0.01"
    else:
        lot_size = "0.01"
    
    if float(lot_size) < 0.01: lot_size = "0.01"

    # We guess the window title based on the server
    window_title = "MetaTrader 5"
    if "maven" in server:
        window_title = "MavenTrade"
    elif "blueguardian" in server:
        window_title = "Blue Guardian"
        
    try:
        # Find window
        windows = gw.getWindowsWithTitle(window_title)
        if not windows:
            # Fallback to any MT5
            windows = gw.getWindowsWithTitle("MetaTrader 5")
            if not windows:
                t_path = req.get('terminal_path')
                if t_path and os.path.exists(t_path):
                    subprocess.Popen([t_path])
                    time.sleep(10) # Wait for terminal to open
                    # Search again using partial match
                    all_wins = gw.getAllTitles()
                    for t in all_wins:
                        if window_title.lower() in t.lower() or "metatrader 5" in t.lower():
                            windows = gw.getWindowsWithTitle(t)
                            break
                
                if not windows:
                    return {"error": "Could not find or launch MT5 window to automate."}
        
        mt5_win = windows[0]
        try:
            mt5_win.activate()
            time.sleep(0.5)
        except Exception as e:
            if "Error code from Windows" in str(e):
                pass # Ignore weird pygetwindow error when activating
            else:
                raise e

        # F9 Opens the New Order window in MT5
        pyautogui.press('f9')
        time.sleep(1.5)

        if is_test:
            # Just close the window for test
            pyautogui.press('esc')
            return {"status": "Success", "message": "GUI Executor test completed (F9 pressed)."}

        # Tab navigation from Symbol -> Type -> Volume -> SL -> TP
        pyautogui.press('tab') # to Type
        time.sleep(0.1)
        pyautogui.press('tab') # to Volume
        time.sleep(0.1)
        pyautogui.typewrite(str(lot_size))
        time.sleep(0.1)
        pyautogui.press('tab') # to SL
        time.sleep(0.1)
        pyautogui.typewrite(str(sl))
        time.sleep(0.1)
        pyautogui.press('tab') # to TP
        time.sleep(0.1)
        pyautogui.typewrite(str(tp))
        time.sleep(0.1)

        # Execute
        if direction.lower() == 'long':
            pyautogui.hotkey('alt', 'b') # Buy by Market
        else:
            pyautogui.hotkey('alt', 's') # Sell by Market
            
        time.sleep(1.5)
        pyautogui.press('esc') # Close any leftover window/dialog

        return {"status": "Success", "message": "GUI trade executed successfully.", "ticket": 0, "volume": lot_size, "price": 0}

    except Exception as e:
        return {"error": f"GUI Error: {str(e)}"}

if __name__ == '__main__':
    try:
        req = json.loads(sys.stdin.read())
        res = execute_trade(req)
        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
