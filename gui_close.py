import sys
import time
import json
import os
try:
    import pyautogui
    import pygetwindow as gw
except ImportError:
    print(json.dumps({"error": "Dependencies not installed. Run: pip install pyautogui pygetwindow"}))
    sys.exit(1)

def close_all(server_name):
    window_title = "MetaTrader 5"
    if "maven" in server_name.lower():
        window_title = "MavenTrade"
    elif "blueguardian" in server_name.lower():
        window_title = "Blue Guardian"

    # Find the terminal window
    windows = gw.getWindowsWithTitle(window_title)
    if not windows:
        windows = gw.getWindowsWithTitle("MetaTrader 5")
    
    if not windows:
        # Fallback to searching all titles
        all_wins = gw.getAllTitles()
        for t in all_wins:
            if window_title.lower() in t.lower() or "metatrader 5" in t.lower():
                windows = gw.getWindowsWithTitle(t)
                break

    if not windows:
        return {"error": "MT5 window not found for closing."}

    mt5_win = windows[0]
    try:
        mt5_win.activate()
        time.sleep(1)
    except Exception as e:
        if "Error code from Windows" not in str(e):
            return {"error": f"Failed to activate window: {e}"}

    # Ensure Terminal is open (Ctrl+T toggles it, but we can't be sure if it's open or closed)
    # Usually it's open. We will just look for the close_button.png on screen.
    
    img_path = os.path.join(os.path.dirname(__file__), 'close_button.png')
    if not os.path.exists(img_path):
        return {"error": f"Missing image template: {img_path}. Please screenshot the 'x' button and save it as close_button.png."}

    closed_count = 0
    max_attempts = 10
    
    # Repeatedly find and click all 'x' buttons until none are left
    for _ in range(max_attempts):
        try:
            # Locate all instances of the close button on screen with 80% confidence
            # Requires opencv-python installed for confidence parameter
            pos = pyautogui.locateCenterOnScreen(img_path, confidence=0.8)
            if pos:
                pyautogui.click(pos)
                time.sleep(1)
                closed_count += 1
            else:
                break # No more close buttons found
        except pyautogui.ImageNotFoundException:
            break
        except Exception as e:
            if "confidence" in str(e).lower():
                return {"error": "Please install opencv-python for image recognition: pip install opencv-python"}
            return {"error": f"Image recognition error: {e}"}
            
    return {"status": "Success", "message": f"Clicked close button {closed_count} times."}

if __name__ == '__main__':
    server = sys.argv[1] if len(sys.argv) > 1 else ""
    res = close_all(server)
    print(json.dumps(res))
