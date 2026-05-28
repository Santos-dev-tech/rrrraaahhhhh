import sys
import json
import time

def execute_trade(req):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"error": "Playwright is not installed. Please run: pip install playwright && playwright install"}

    login = req.get('login')
    password = req.get('password')
    direction = req.get('direction', 'Long')
    sl = req.get('sl', 0)
    tp = req.get('tp', 0)
    risk_amt = req.get('risk_amount', 4.0)
    is_test = req.get('is_test', False)

    # We can't perfectly compute lots without exact MatchTrader tick data, we assume XAUUSD contract size 100
    if not is_test and sl > 0:
        entry_guess = req.get('entry_price', 0) # passed from live_server if possible
        if entry_guess == 0:
            # Cannot compute precisely
            lot_size = "0.01"
        else:
            sl_dist = abs(entry_guess - float(sl)) * 100
            lot_size = str(round((float(risk_amt) / sl_dist), 2)) if sl_dist > 0 else "0.01"
    else:
        lot_size = "0.01"

    if float(lot_size) < 0.01: lot_size = "0.01"

    try:
        with sync_playwright() as p:
            # We open browser visibly (headless=False) so the user can see and manually intervene if needed
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            page.goto("https://platform.nextlevelfunded.com")
            
            # Attempt to login using standard heuristics (this may need adjustment based on exact DOM)
            try:
                page.wait_for_selector('input[type="email"], input[type="text"]', timeout=10000)
                page.fill('input[type="email"], input[type="text"]', str(login))
                page.fill('input[type="password"]', str(password))
                page.click('button[type="submit"]')
                page.wait_for_timeout(5000) # Wait for platform to load
            except Exception as e:
                pass # Could already be logged in or selectors didn't match

            # At this point, the platform is open.
            # Automating the exact trade without knowing the DOM is impossible,
            # so we alert the user visually.
            
            # Try to inject a bright overlay to tell the user to trade!
            alert_script = f"""
            let div = document.createElement('div');
            div.style.position = 'fixed';
            div.style.top = '0';
            div.style.left = '0';
            div.style.width = '100vw';
            div.style.height = '100px';
            div.style.backgroundColor = '{'#10b981' if direction == 'Long' else '#ef4444'}';
            div.style.color = '#fff';
            div.style.fontSize = '24px';
            div.style.fontWeight = 'bold';
            div.style.zIndex = '999999';
            div.style.display = 'flex';
            div.style.alignItems = 'center';
            div.style.justifyContent = 'center';
            div.innerHTML = '🚨 BREAKOUT TRIGGERED! {direction} XAUUSD | LOTS: {lot_size} | SL: {sl} | TP: {tp}';
            document.body.appendChild(div);
            """
            try:
                page.evaluate(alert_script)
            except:
                pass

            if is_test:
                time.sleep(10)
                browser.close()
                return {"status": "Success", "message": "Playwright launched successfully for test"}

            # Leave it open for 5 minutes for the user to execute the trade manually if automation fails
            time.sleep(300)
            browser.close()
            return {"status": "Success", "message": "Browser opened for manual MatchTrader execution", "ticket": 0, "volume": lot_size, "price": 0}

    except Exception as e:
        return {"error": f"Playwright Error: {str(e)}"}

if __name__ == '__main__':
    try:
        req = json.loads(sys.stdin.read())
        res = execute_trade(req)
        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
