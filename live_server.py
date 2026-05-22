from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone
import threading
import time
import json
import csv
import os
import subprocess

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, 'accounts.json')
TRADE_LOG_FILE = os.path.join(BASE_DIR, 'trade_log.csv')

# --- Multi-Account State ---
accounts = []
state_lock = threading.Lock()
mt5_lock = threading.Lock()  # Only one thread talks to MT5 at a time
eod_closed_today = None  # Track if 21:00 close already ran today

# Default terminal for fetching live price data
TERMINAL_PATH = r"C:\Program Files\Blue Guardian MT5 Terminal\terminal64.exe"

def get_terminal_path(server_name):
    server_lower = server_name.lower()
    if "blueguardian" in server_lower:
        return r"C:\Program Files\Blue Guardian MT5 Terminal\terminal64.exe"
    elif "fundednext" in server_lower or "nlf" in server_lower:
        # Use EXNESS terminal as the dedicated terminal for FundedNext
        return r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
    else:
        # Use Vanilla terminal for MavenTrade
        return r"C:\Program Files\MetaTrader 5\terminal64.exe"


# Shared market data (same symbol, same candles for all accounts)
symbol = "XAUUSDm"
latest_price = {}
latest_candles = []
signals = {}  # key: "1300" or "1255", value: strategy result dict


# ==================== PERSISTENCE ====================

def save_accounts():
    """Save accounts to disk (passwords stored locally only — add to .gitignore)."""
    with state_lock:
        data = []
        for a in accounts:
            data.append({
                "login": a['login'], "password": a['password'], "server": a['server'],
                "strategy": a['strategy'], "auto_trade": a['auto_trade'],
                "name": a.get('name', ''), "balance": a.get('balance', 0),
                "equity": a.get('equity', 0), "leverage": a.get('leverage', 0),
                "risk_amount": a.get('risk_amount', 4.0),
            })
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[PERSIST] Save error: {e}")


def load_accounts():
    """Load saved accounts on startup."""
    if not os.path.exists(ACCOUNTS_FILE):
        return
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            data = json.load(f)
        with state_lock:
            for a in data:
                a.setdefault('last_trade_date', None)
                a.setdefault('last_trade_result', None)
                a.setdefault('risk_amount', 4.0)
                accounts.append(a)
        print(f"[PERSIST] Loaded {len(data)} accounts from disk")
    except Exception as e:
        print(f"[PERSIST] Load error: {e}")


# ==================== TRADE LOGGING ====================

def log_trade(login, strategy, direction, entry, sl, tp, volume, order_id, status, note=''):
    """Append trade to CSV log."""
    file_exists = os.path.exists(TRADE_LOG_FILE)
    try:
        with open(TRADE_LOG_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['timestamp', 'account', 'strategy', 'direction', 'entry', 'sl', 'tp', 'volume', 'order_id', 'status', 'note'])
            writer.writerow([
                datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                login, strategy, direction, f"{entry:.2f}", f"{sl:.2f}", f"{tp:.2f}",
                volume, order_id, status, note
            ])
    except Exception as e:
        print(f"[LOG] Write error: {e}")


# ==================== 21:00 UTC AUTO-CLOSE ====================

def close_positions_on_account(acct):
    """Login to account and close all open XAUUSD positions. Caller must hold mt5_lock."""
    closed = []
    try:
        t_path = get_terminal_path(acct['server'])
        if not mt5.initialize(path=t_path, timeout=120000):
            return closed
        if not mt5.login(acct['login'], password=acct['password'], server=acct['server']):
            return closed

        sym = "XAUUSD" if mt5.symbol_info("XAUUSD") else "XAUUSDm"
        positions = mt5.positions_get(symbol=sym)
        if not positions:
            return closed

        for pos in positions:
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(sym)
            price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
            result = mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": pos.volume,
                "type": close_type, "position": pos.ticket, "price": price,
                "deviation": 20, "magic": 130001, "comment": "AutoPilot EOD Close",
                "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
            })
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                pnl = pos.profit
                closed.append({"ticket": pos.ticket, "pnl": pnl})
                log_trade(acct['login'], acct['strategy'], 'CLOSE', price, 0, 0, pos.volume, result.order, 'EOD_CLOSE', f"P&L: {pnl:.2f}")
                print(f"[EOD CLOSE] #{acct['login']} closed ticket {pos.ticket} | P&L: {pnl:.2f}")
            else:
                print(f"[EOD CLOSE FAIL] #{acct['login']} ticket {pos.ticket}: {result.comment}")
    except Exception as e:
        print(f"[EOD CLOSE ERROR] #{acct['login']}: {e}")
    return closed


def is_market_open():
    now = datetime.now(timezone.utc)
    wd = now.weekday()
    h = now.hour
    if wd == 5: return False
    if wd == 6 and h < 22: return False
    if wd == 4 and h >= 22: return False
    return True


def compute_strategy(df, anchor_hour, anchor_minute):
    """Compute breakout signal for a given anchor time."""
    today = df.iloc[-1]['time'].date()
    today_df = df[df['time'].dt.date == today]
    
    anchor_mask = (today_df['time'].dt.hour == anchor_hour) & (today_df['time'].dt.minute == anchor_minute)
    anchor_candles = today_df[anchor_mask]
    
    if anchor_candles.empty:
        if not is_market_open():
            return {"status": "Market Closed — Opens Sunday 22:00 UTC"}
        return {"status": f"Waiting for {anchor_hour}:{anchor_minute:02d} UTC Anchor Candle"}
    
    anchor = anchor_candles.iloc[0]
    anchor_idx = today_df.index.get_loc(anchor.name)
    anchor_high = float(anchor['high'])
    anchor_low = float(anchor['low'])
    remaining = today_df.iloc[anchor_idx + 1:]
    
    direction = entry_price = sl = tp = risk = trigger_time = None
    SL_BUFFER = 0.50
    
    for _, candle in remaining.iterrows():
        bh = candle['high'] > anchor_high
        bl = candle['low'] < anchor_low
        if bh and bl:
            direction = 'Long' if candle['close'] >= candle['open'] else 'Short'
            entry_price = float(candle['close'])
            trigger_time = candle['time']
            break
        elif bh:
            direction = 'Long'
            entry_price = float(candle['close'])
            trigger_time = candle['time']
            break
        elif bl:
            direction = 'Short'
            entry_price = float(candle['close'])
            trigger_time = candle['time']
            break
    
    if direction:
        if direction == 'Long':
            sl = anchor_low - SL_BUFFER; risk = entry_price - sl; tp = entry_price + (risk * 3)
        else:
            sl = anchor_high + SL_BUFFER; risk = sl - entry_price; tp = entry_price - (risk * 3)
        return {
            "status": "Breakout Triggered!", "anchor_high": anchor_high, "anchor_low": anchor_low,
            "direction": direction, "entry_price": entry_price, "sl": float(sl), "tp": float(tp), "risk": float(risk),
            "anchor_time": int(anchor['time'].timestamp()),
            "trigger_time": int(trigger_time.timestamp())
        }
    
    return {
        "status": "Anchor Formed. Watching for Breakout...",
        "anchor_time": int(anchor['time'].timestamp()),
        "anchor_high": anchor_high, "anchor_low": anchor_low
    }


def execute_on_account(acct, direction, sl, tp, max_retries=3):
    """Launch executor script to execute a trade in an isolated process."""
    t_path = get_terminal_path(acct['server'])
    
    payload = {
        "terminal_path": t_path,
        "login": acct['login'],
        "password": acct['password'],
        "server": acct['server'],
        "direction": direction,
        "sl": sl,
        "tp": tp,
        "risk_amount": float(acct.get('risk_amount', 4.0)),
        "is_test": False
    }
    
    import subprocess
    import json as sys_json
    
    for attempt in range(1, max_retries + 1):
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
                        err_msg = res["error"]
                        if 'AutoTrading' in err_msg and attempt < max_retries:
                            print(f"[RETRY {attempt}/{max_retries}] AutoTrading disabled, waiting 10s...")
                            time.sleep(10)
                            continue
                        elif 'MT5 init failed' in err_msg and attempt < max_retries:
                            print(f"[RETRY {attempt}/{max_retries}] Init failed, waiting 2s...")
                            time.sleep(2)
                            continue
                        return res
                    return res
                except:
                    pass
            if attempt < max_retries:
                time.sleep(2)
                continue
            return {"error": f"Executor failed: {proc.stderr}"}
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
                continue
            return {"error": str(e)}
    return {"error": "Max retries exhausted"}


def poll_loop():
    """Main loop: poll market data, compute signals, auto-execute."""
    global symbol, latest_price, latest_candles, signals, eod_closed_today
    print("Starting multi-account polling loop...")
    
    while True:
        try:
            market_open = is_market_open()
            today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            
            with mt5_lock:
                if not mt5.initialize(path=TERMINAL_PATH, timeout=120000):
                    if not market_open:
                        with state_lock:
                            signals["1300"] = {"status": "Market Closed — Opens Sunday 22:00 UTC"}
                            signals["1255"] = {"status": "Market Closed — Opens Sunday 22:00 UTC"}
                    time.sleep(2)
                    continue
                
                sym = "XAUUSD" if mt5.symbol_info("XAUUSD") else "XAUUSDm"
                symbol = sym
                mt5.symbol_select(sym, True)
                
                # --- Price data ---
                tick = mt5.symbol_info_tick(sym)
                if tick:
                    with state_lock:
                        latest_price = {"time": tick.time, "bid": tick.bid, "ask": tick.ask, "spread": round((tick.ask - tick.bid) * 100, 1)}
                
                if not market_open:
                    with state_lock:
                        signals["1300"] = {"status": "Market Closed — Opens Sunday 22:00 UTC"}
                        signals["1255"] = {"status": "Market Closed — Opens Sunday 22:00 UTC"}
                else:
                    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 1000)
                    if rates is not None and len(rates) > 0:
                        fmt = [{"time": int(r['time']), "open": float(r['open']), "high": float(r['high']), "low": float(r['low']), "close": float(r['close'])} for r in rates]
                        with state_lock:
                            latest_candles = fmt
                        
                        df = pd.DataFrame(rates)
                        df['time'] = pd.to_datetime(df['time'], unit='s')
                        
                        sig_1300 = compute_strategy(df, 13, 0)
                        sig_1255 = compute_strategy(df, 12, 55)
                        
                        with state_lock:
                            signals["1300"] = sig_1300
                            signals["1255"] = sig_1255
                        
                        # Auto-execute (skip Mondays)
                        now_utc_exec = datetime.now(timezone.utc)
                        if now_utc_exec.weekday() != 0:
                            with state_lock:
                                accts_snapshot = list(accounts)
                            
                            for acct in accts_snapshot:
                                strat_key = acct['strategy']
                                sig = sig_1300 if strat_key == '1300' else sig_1255
                                
                                if acct.get('last_trade_date') == today_str:
                                    continue
                                
                                if sig.get('status') == 'Breakout Triggered!' and acct.get('auto_trade'):
                                    # Staleness Check (must be within 10 minutes of breakout candle timestamp)
                                    latest_chart_time = df.iloc[-1]['time']
                                    sig_time = pd.to_datetime(sig.get('trigger_time'), unit='s')
                                    time_diff_mins = (latest_chart_time - sig_time).total_seconds() / 60.0
                                    
                                    if time_diff_mins > 10.0:
                                        # Stale breakout trigger. Mark as processed for today so we don't retry or spam.
                                        with state_lock:
                                            idx = next((i for i, a in enumerate(accounts) if a['login'] == acct['login']), None)
                                            if idx is not None:
                                                accounts[idx]['last_trade_date'] = today_str
                                                accounts[idx]['last_trade_result'] = {"error": f"Breakout stale by {time_diff_mins:.1f} mins (limit 10 mins)"}
                                        print(f"[AUTO-TRADE] #{acct['login']}: Skipped stale {strat_key} breakout (stale by {time_diff_mins:.1f} mins)")
                                        continue

                                    result = execute_on_account(acct, sig['direction'], sig['sl'], sig['tp'])
                                    with state_lock:
                                        idx = next((i for i, a in enumerate(accounts) if a['login'] == acct['login']), None)
                                        if idx is not None:
                                            if result.get('status') == 'Success':
                                                accounts[idx]['last_trade_date'] = today_str
                                                accounts[idx]['last_trade_result'] = result
                                                log_trade(acct['login'], strat_key, sig['direction'], result['price'], sig['sl'], sig['tp'], result['volume'], result['order'], 'SUCCESS')
                                                print(f"[AUTO-TRADE] #{acct['login']} {sig['direction']} @ {result['price']:.2f}, Vol: {result['volume']}")
                                            else:
                                                accounts[idx]['last_trade_date'] = today_str  # Mark as attempted for today to stop spamming
                                                accounts[idx]['last_trade_result'] = result
                                                log_trade(acct['login'], strat_key, sig['direction'], sig.get('entry_price', 0), sig['sl'], sig['tp'], 0, 0, 'FAILED', result.get('error', ''))
                                                print(f"[AUTO-TRADE FAIL] #{acct['login']}: {result.get('error')}")
                                    mt5.initialize(path=TERMINAL_PATH, timeout=120000)  # Re-init after account switch
                        
                        # --- 21:00 UTC Auto-Close ---
                        now_utc = datetime.now(timezone.utc)
                        if now_utc.hour >= 21 and eod_closed_today != today_str:
                            eod_closed_today = today_str
                            print(f"[EOD] 21:00 UTC — Closing all open positions...")
                            with state_lock:
                                close_snapshot = list(accounts)
                            for acct in close_snapshot:
                                closed = close_positions_on_account(acct)
                                if closed:
                                    print(f"[EOD] #{acct['login']} closed {len(closed)} position(s)")
                                mt5.initialize(path=TERMINAL_PATH, timeout=120000)  # Re-init after account switch
        
        except Exception as e:
            print(f"Poll error: {e}")
        
        time.sleep(2)


# ==================== ROUTES ====================

@app.after_request
def add_cache_control(response):
    if request.path.startswith('/api/'):
        response.cache_control.no_cache = True
        response.cache_control.no_store = True
        response.cache_control.must_revalidate = True
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

@app.route('/')
def index():
    return send_file('live_dashboard.html')

@app.route('/dashboard.css')
def dashboard_css():
    return send_file('dashboard.css', mimetype='text/css')

@app.route('/godmode.css')
def godmode_css():
    return send_file('godmode.css', mimetype='text/css')

@app.route('/dashboard.js')
def serve_js():
    return send_file('dashboard.js', mimetype='application/javascript')

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    with state_lock:
        safe = []
        for a in accounts:
            safe.append({
                "login": a['login'], "server": a['server'], "strategy": a['strategy'],
                "auto_trade": a['auto_trade'], "name": a.get('name', ''),
                "balance": a.get('balance', 0), "equity": a.get('equity', 0),
                "last_trade_date": a.get('last_trade_date'), "last_trade_result": a.get('last_trade_result'),
                "risk_amount": a.get('risk_amount', 4.0),
            })
        return jsonify(safe)

@app.route('/api/accounts/add', methods=['POST'])
def add_account():
    data = request.json
    login_id = data.get('login')
    password = data.get('password')
    server = data.get('server', 'Exness-MT5Trial')
    strategy = data.get('strategy', '1300')
    auto_trade = data.get('auto_trade', True)
    risk_amount = float(data.get('risk_amount', 4.0))
    
    if not login_id or not password:
        return jsonify({"error": "Login and password required"}), 400
    
    with state_lock:
        if any(a['login'] == int(login_id) for a in accounts):
            return jsonify({"error": "Account already added"}), 400
    
    # Verify credentials
    with mt5_lock:
        t_path = get_terminal_path(server)
        if not mt5.initialize(path=t_path, timeout=120000):
            return jsonify({"error": "MT5 terminal not available"}), 500
        
        if not mt5.login(int(login_id), password=password, server=server):
            err = mt5.last_error()
            return jsonify({"error": f"Auth failed: {err}"}), 401
        
        info = mt5.account_info()
        acct = {
            "login": int(login_id), "password": password, "server": server,
            "strategy": strategy, "auto_trade": bool(auto_trade),
            "risk_amount": risk_amount,
            "name": info.name if info else "", "balance": info.balance if info else 0,
            "equity": info.equity if info else 0, "leverage": info.leverage if info else 0,
            "last_trade_date": None, "last_trade_result": None,
        }
    
    with state_lock:
        accounts.append(acct)
    save_accounts()
    
    print(f"[ACCOUNT ADDED] #{login_id} on {server} | Strategy: {strategy} | Auto: {auto_trade}")
    return jsonify({"status": "Added", "name": acct['name'], "balance": acct['balance'], "login": acct['login']})

@app.route('/api/accounts/remove', methods=['POST'])
def remove_account():
    login_id = request.json.get('login')
    with state_lock:
        accounts[:] = [a for a in accounts if a['login'] != int(login_id)]
    save_accounts()
    return jsonify({"status": "Removed"})

@app.route('/api/accounts/toggle_auto', methods=['POST'])
def toggle_account_auto():
    login_id = int(request.json.get('login'))
    with state_lock:
        for a in accounts:
            if a['login'] == login_id:
                a['auto_trade'] = not a['auto_trade']
                save_accounts()
                return jsonify({"auto_trade": a['auto_trade']})
    return jsonify({"error": "Not found"}), 404

@app.route('/api/price', methods=['GET'])
def get_price():
    with state_lock:
        if not latest_price:
            if not is_market_open():
                return jsonify({"market_closed": True})
            return jsonify({"error": "Waiting..."})
        return jsonify(latest_price)

@app.route('/api/candles', methods=['GET'])
def get_candles():
    with state_lock:
        if not latest_candles:
            return jsonify({"error": "No data", "market_closed": not is_market_open()})
        return jsonify(latest_candles)

@app.route('/api/strategy', methods=['GET'])
def get_strategy():
    strat_key = request.args.get('anchor', '1300')
    with state_lock:
        return jsonify(signals.get(strat_key, {"status": "Waiting..."}))

@app.route('/api/execute', methods=['POST'])
def manual_execute():
    login_id = int(request.json.get('login'))
    with state_lock:
        acct = next((a for a in accounts if a['login'] == login_id), None)
        if not acct: return jsonify({"error": "Account not found"}), 404
        sig = signals.get(acct['strategy'], {})
    
    if sig.get('status') != 'Breakout Triggered!':
        return jsonify({"error": "No breakout signal"}), 400
    
    with mt5_lock:
        result = execute_on_account(acct, sig['direction'], sig['sl'], sig['tp'])
    if result.get('status') == 'Success':
        with state_lock:
            for a in accounts:
                if a['login'] == login_id:
                    a['last_trade_date'] = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                    a['last_trade_result'] = result
        log_trade(login_id, acct['strategy'], sig['direction'], result['price'], sig['sl'], sig['tp'], result['volume'], result['order'], 'MANUAL')
    else:
        log_trade(login_id, acct['strategy'], sig['direction'], sig.get('entry_price', 0), sig['sl'], sig['tp'], 0, 0, 'MANUAL_FAIL', result.get('error', ''))
    return jsonify(result)

@app.route('/api/backtest_stats', methods=['GET'])
def get_backtest_stats():
    try:
        path = os.path.join(os.path.dirname(__file__), 'master_strategy_log.html')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return jsonify({"html": f.read()})
        return jsonify({"error": "Run generate_master_log.py first"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/test_trade', methods=['POST'])
def test_trade():
    """Open 0.01 lot, wait 5s, close. Proves MT5 execution works."""
    login_id = int(request.json.get('login'))
    with state_lock:
        acct = next((a for a in accounts if a['login'] == login_id), None)
    if not acct:
        return jsonify({"error": "Account not found"}), 404

    t_path = get_terminal_path(acct['server'])
    
    payload = {
        "terminal_path": t_path,
        "login": acct['login'],
        "password": acct['password'],
        "server": acct['server'],
        "is_test": True
    }
    
    import subprocess
    import json as sys_json
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
                return jsonify(res)
            except:
                return jsonify({"error": f"Invalid executor output: {proc.stdout}"})
        else:
            return jsonify({"error": f"Executor failed: {proc.stderr}"})
    except Exception as e:
        return jsonify({"error": str(e)})


def stats_loop():
    """Runs daily to update 1-year stats."""
    last_run_date = None
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            today_str = now_utc.strftime('%Y-%m-%d')
            
            # Run at 00:05 UTC every day
            if now_utc.hour == 0 and now_utc.minute >= 5 and last_run_date != today_str:
                print(f"[STATS] 1-year statistics preservation mode active (auto-update disabled to preserve 45% WR conditions).")
                last_run_date = today_str
        except Exception as e:
            print(f"[STATS] Error updating stats: {e}")
        
        time.sleep(60) # check every minute

if __name__ == '__main__':
    load_accounts()
    
    flask_thread = threading.Thread(target=lambda: app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()
    
    stats_thread = threading.Thread(target=stats_loop)
    stats_thread.daemon = True
    stats_thread.start()
    
    poll_loop()
