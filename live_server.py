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

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, 'accounts.json')
TRADE_LOG_FILE = os.path.join(BASE_DIR, 'trade_log.csv')

# --- Multi-Account State ---
accounts = []
state_lock = threading.Lock()
eod_closed_today = None  # Track if 21:00 close already ran today

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
    """Login to account and close all open XAUUSD positions."""
    closed = []
    try:
        if not mt5.initialize():
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
    
    direction = entry_price = sl = tp = risk = None
    SL_BUFFER = 0.50
    
    for _, candle in remaining.iterrows():
        bh = candle['high'] > anchor_high
        bl = candle['low'] < anchor_low
        if bh and bl:
            direction = 'Long' if candle['close'] >= candle['open'] else 'Short'
            entry_price = float(candle['close']); break
        elif bh:
            direction = 'Long'; entry_price = float(candle['close']); break
        elif bl:
            direction = 'Short'; entry_price = float(candle['close']); break
    
    if direction:
        if direction == 'Long':
            sl = anchor_low - SL_BUFFER; risk = entry_price - sl; tp = entry_price + (risk * 3)
        else:
            sl = anchor_high + SL_BUFFER; risk = sl - entry_price; tp = entry_price - (risk * 3)
        return {
            "status": "Breakout Triggered!", "anchor_high": anchor_high, "anchor_low": anchor_low,
            "direction": direction, "entry_price": entry_price, "sl": float(sl), "tp": float(tp), "risk": float(risk),
            "anchor_time": int(anchor['time'].timestamp())
        }
    
    return {
        "status": "Anchor Formed. Watching for Breakout...",
        "anchor_time": int(anchor['time'].timestamp()),
        "anchor_high": anchor_high, "anchor_low": anchor_low
    }


def execute_on_account(acct, direction, sl, tp, max_retries=3):
    """Login to a specific account and execute a trade. Retries on AutoTrading disabled."""
    for attempt in range(1, max_retries + 1):
        try:
            mt5.shutdown()
            time.sleep(0.5)
            if not mt5.initialize():
                if attempt < max_retries:
                    print(f"[RETRY {attempt}/{max_retries}] MT5 init failed, retrying...")
                    time.sleep(2)
                    continue
                return {"error": "MT5 init failed after retries"}
            if not mt5.login(acct['login'], password=acct['password'], server=acct['server']):
                return {"error": f"Login failed: {mt5.last_error()}"}
            
            sym = "XAUUSD" if mt5.symbol_info("XAUUSD") else "XAUUSDm"
            mt5.symbol_select(sym, True)
            si = mt5.symbol_info(sym)
            tick = mt5.symbol_info_tick(sym)
            
            order_type = mt5.ORDER_TYPE_BUY if direction == 'Long' else mt5.ORDER_TYPE_SELL
            price = tick.ask if direction == 'Long' else tick.bid
            cs = si.trade_contract_size
            rpl = (price - sl) * cs if direction == 'Long' else (sl - price) * cs
            if rpl <= 0: return {"error": "Invalid SL"}
            
            vol = round((4.0 / rpl) / si.volume_step) * si.volume_step
            if vol < si.volume_min: vol = si.volume_min
            
            result = mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": float(vol),
                "type": order_type, "price": float(price), "sl": float(sl), "tp": float(tp),
                "deviation": 20, "magic": 130001, "comment": "AutoPilot Breakout",
                "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
            })
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                # Retry if AutoTrading is disabled — user might enable it
                if 'AutoTrading' in (result.comment or '') and attempt < max_retries:
                    print(f"[RETRY {attempt}/{max_retries}] AutoTrading disabled, waiting 10s for user to enable...")
                    time.sleep(10)
                    continue
                return {"error": f"Order failed: {result.comment}"}
            return {"status": "Success", "order": result.order, "volume": vol, "price": price, "direction": direction}
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
                continue
            return {"error": str(e)}
    return {"error": "Max retries exhausted"}


def poll_loop():
    """Main loop: poll market data, compute signals, auto-execute."""
    global symbol, latest_price, latest_candles, signals
    print("Starting multi-account polling loop...")
    
    while True:
        try:
            market_open = is_market_open()
            
            # Connect to any available MT5 terminal for market data
            if mt5.initialize():
                sym = "XAUUSD" if mt5.symbol_info("XAUUSD") else "XAUUSDm"
                symbol = sym
                mt5.symbol_select(sym, True)
                
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
                        
                        # Compute signals for both anchor times
                        sig_1300 = compute_strategy(df, 13, 0)
                        sig_1255 = compute_strategy(df, 12, 55)
                        
                        with state_lock:
                            signals["1300"] = sig_1300
                            signals["1255"] = sig_1255
                        
                        # Auto-execute on triggered accounts
                        today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                        now_utc_exec = datetime.now(timezone.utc)
                        
                        # MONDAY FILTER: Skip execution on Mondays (weekday 0)
                        if now_utc_exec.weekday() == 0:
                            pass  # Don't execute — Mondays excluded per backtest results
                        else:
                          with state_lock:
                              accts_snapshot = list(accounts)
                          
                          for acct in accts_snapshot:
                              strat_key = acct['strategy']
                              sig = sig_1300 if strat_key == '1300' else sig_1255
                              
                              if acct.get('last_trade_date') == today_str:
                                  continue  # Already traded today
                              
                              if sig.get('status') == 'Breakout Triggered!' and acct.get('auto_trade'):
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
                                            accounts[idx]['last_trade_result'] = result
                                            log_trade(acct['login'], strat_key, sig['direction'], sig.get('entry_price', 0), sig['sl'], sig['tp'], 0, 0, 'FAILED', result.get('error', ''))
                                            print(f"[AUTO-TRADE FAIL] #{acct['login']}: {result.get('error')}")
                                
                                # Re-init MT5 for next cycle
                                mt5.initialize()
                    
                    # --- 21:00 UTC Auto-Close ---
                    global eod_closed_today
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
                            mt5.initialize()  # Re-init for next account
            
            elif not market_open:
                with state_lock:
                    signals["1300"] = {"status": "Market Closed — Opens Sunday 22:00 UTC"}
                    signals["1255"] = {"status": "Market Closed — Opens Sunday 22:00 UTC"}
        
        except Exception as e:
            print(f"Poll error: {e}")
        
        time.sleep(2)


# ==================== ROUTES ====================

@app.route('/')
def index():
    return send_file('live_dashboard.html')

@app.route('/dashboard.css')
def serve_css():
    return send_file('dashboard.css', mimetype='text/css')

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
    
    if not login_id or not password:
        return jsonify({"error": "Login and password required"}), 400
    
    with state_lock:
        if any(a['login'] == int(login_id) for a in accounts):
            return jsonify({"error": "Account already added"}), 400
    
    # Verify credentials
    if not mt5.initialize():
        return jsonify({"error": "MT5 terminal not available"}), 500
    
    if not mt5.login(int(login_id), password=password, server=server):
        err = mt5.last_error()
        return jsonify({"error": f"Auth failed: {err}"}), 401
    
    info = mt5.account_info()
    acct = {
        "login": int(login_id), "password": password, "server": server,
        "strategy": strategy, "auto_trade": bool(auto_trade),
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


if __name__ == '__main__':
    load_accounts()
    flask_thread = threading.Thread(target=lambda: app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()
    poll_loop()
