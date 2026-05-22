import subprocess
import time
import pyautogui

def add_broker():
    print("Launching Blue Guardian MT5...")
    # Launch MT5
    process = subprocess.Popen([r"C:\Program Files\Blue Guardian MT5 Terminal\terminal64.exe"])
    
    print("Waiting 10 seconds for MT5 to open...")
    time.sleep(10)
    
    print("Opening 'Open an Account' dialog...")
    # Press Alt+F, then A
    pyautogui.hotkey('alt', 'f')
    time.sleep(0.5)
    pyautogui.press('a')
    time.sleep(2)
    
    print("Searching for Exness...")
    # Type Exness and press Enter
    pyautogui.write('Exness')
    time.sleep(0.5)
    pyautogui.press('enter')
    
    print("Waiting 10 seconds for search results...")
    time.sleep(10)
    
    print("Selecting first result and pressing Next...")
    # Press Down to select the first result, then Alt+N (Next) or Enter
    pyautogui.press('down')
    time.sleep(0.5)
    pyautogui.hotkey('alt', 'n')
    time.sleep(2)
    
    print("Closing MT5...")
    # Close MT5 to save config
    process.terminate()
    print("Done!")

if __name__ == "__main__":
    add_broker()
