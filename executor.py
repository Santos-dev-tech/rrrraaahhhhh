import sys
import json
import time
import MetaTrader5 as mt5

def try_send(req_dict):
    """Send order with filling mode fallback."""
    result = mt5.order_send(req_dict)
    if result.retcode == mt5.TRADE_RETCODE_INVALID_FILL or result.comment == "Unsupported filling mode":
        req_dict["type_filling"] = mt5.ORDER_FILLING_FOK
        result = mt5.order_send(req_dict)
        if result.retcode == mt5.TRADE_RETCODE_INVALID_FILL or result.comment == "Unsupported filling mode":
            req_dict["type_filling"] = mt5.ORDER_FILLING_RETURN
            result = mt5.order_send(req_dict)
    return result

def main():
    try:
        req = json.loads(sys.stdin.read())
    except Exception as e:
        print(json.dumps({"error": f"Invalid input: {e}"}))
        sys.exit(1)

    t_path = req.get('terminal_path')
    login = req.get('login')
    password = req.get('password')
    server = req.get('server')
    is_test = req.get('is_test', False)

    if not mt5.initialize(path=t_path, timeout=60000):
        print(json.dumps({"error": "MT5 init failed"}))
        sys.exit(1)

    # Only login if credentials provided (needed for accounts where terminal isn't pre-logged-in)
    if login and password and server:
        if not mt5.login(login, password=password, server=server):
            err = mt5.last_error()
            mt5.shutdown()
            print(json.dumps({"error": f"Login failed: {err}"}))
            sys.exit(1)

    sym = "XAUUSD" if mt5.symbol_info("XAUUSD") else "XAUUSDm"
    if not mt5.symbol_select(sym, True):
        mt5.shutdown()
        print(json.dumps({"error": "Symbol select failed"}))
        sys.exit(1)

    si = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    cs = si.trade_contract_size  # 100 for XAUUSD/XAUUSDm

    if is_test:
        vol = 0.01
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        sl = tp = 0.0
        comment = "TEST TRADE"
    else:
        direction = req.get('direction')
        sl = float(req.get('sl'))
        tp = float(req.get('tp'))
        order_type = mt5.ORDER_TYPE_BUY if direction == 'Long' else mt5.ORDER_TYPE_SELL
        price = tick.ask if direction == 'Long' else tick.bid
        rpl = (price - sl) * cs if direction == 'Long' else (sl - price) * cs
        if rpl <= 0:
            mt5.shutdown()
            print(json.dumps({"error": "Invalid SL"}))
            sys.exit(1)
        risk_amt = float(req.get('risk_amount', 4.0))
        vol = round((risk_amt / rpl) / si.volume_step) * si.volume_step
        if vol < si.volume_min: vol = si.volume_min
        comment = "AutoPilot Breakout"

    result = try_send({
        "action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": float(vol),
        "type": order_type, "price": float(price), "sl": float(sl), "tp": float(tp),
        "deviation": 20, "magic": 999999 if is_test else 130001, "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
    })

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        mt5.shutdown()
        print(json.dumps({"error": f"Open failed: {result.comment}"}))
        sys.exit(1)

    output = {"status": "Success", "ticket": result.order, "volume": vol, "open_price": round(price, 2)}

    if is_test:
        time.sleep(5)
        tick2 = mt5.symbol_info_tick(sym)
        close_price = tick2.bid if order_type == mt5.ORDER_TYPE_BUY else tick2.ask

        res_close = try_send({
            "action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": float(vol),
            "type": mt5.ORDER_TYPE_SELL if order_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": result.order, "price": close_price,
            "deviation": 20, "magic": 999999, "comment": "TEST CLOSE",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
        })

        pnl = (close_price - price) * cs * vol
        output.update({
            "close_price": round(close_price, 2),
            "pnl_approx": round(pnl, 2),
            "message": "Test trade completed! MT5 execution is WORKING." if res_close.retcode == mt5.TRADE_RETCODE_DONE else "Open succeeded, close failed."
        })

    mt5.shutdown()
    print(json.dumps(output))

if __name__ == '__main__':
    main()
