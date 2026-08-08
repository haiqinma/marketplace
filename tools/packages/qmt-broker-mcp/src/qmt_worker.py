#!/usr/bin/env python3

import json
import os
import sys
import time
import traceback


TRADER = None
ACCOUNT = None
XTCONSTANT = None


def env_bool(name, fallback):
    value = os.environ.get(name)
    if value is None or value == "":
        return fallback
    return value.lower() in ("1", "true", "yes", "on")


def normalize_symbol(symbol):
    value = str(symbol).strip().upper()
    if "." in value:
        return value
    if value.startswith("6"):
        return f"{value}.SH"
    if value.startswith(("0", "3")):
        return f"{value}.SZ"
    if value.startswith(("4", "8")):
        return f"{value}.BJ"
    return value


def get_attr(obj, names, default=None):
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return default


def object_to_dict(obj):
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return obj

    result = {}
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if callable(value):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[name] = value
    return result


def mask_account_id(value):
    if not value:
        return None
    text = str(value)
    if len(text) <= 4:
        return "****"
    return f"{text[:2]}****{text[-2:]}"


def connect_qmt():
    global TRADER, ACCOUNT, XTCONSTANT
    if TRADER is not None and ACCOUNT is not None:
        return

    qmt_path = os.environ.get("QMT_USERDATA_PATH")
    account_id = os.environ.get("QMT_ACCOUNT_ID")
    account_type = os.environ.get("QMT_ACCOUNT_TYPE", "STOCK")

    if not qmt_path:
        raise RuntimeError("QMT_USERDATA_PATH is required.")
    if not account_id:
        raise RuntimeError("QMT_ACCOUNT_ID is required.")

    try:
        from xtquant.xttrader import XtQuantTrader
        from xtquant.xttype import StockAccount
        from xtquant import xtconstant
    except Exception as exc:
        raise RuntimeError(
            "Failed to import xtquant. Install and configure MiniQMT/xtquant in the Python runtime used by QMT_PYTHON."
        ) from exc

    session_id = int(os.environ.get("QMT_SESSION_ID") or int(time.time()))
    trader = XtQuantTrader(qmt_path, session_id)
    account = StockAccount(account_id, account_type)

    trader.start()
    connect_result = trader.connect()
    if connect_result != 0:
        raise RuntimeError(f"QMT connect failed with code {connect_result}.")

    subscribe_result = trader.subscribe(account)
    if subscribe_result != 0:
        raise RuntimeError(f"QMT subscribe failed with code {subscribe_result}.")

    TRADER = trader
    ACCOUNT = account
    XTCONSTANT = xtconstant


def broker_status(params=None):
    params = params or {}
    qmt_path = os.environ.get("QMT_USERDATA_PATH")
    account_id = os.environ.get("QMT_ACCOUNT_ID")
    live_trading_enabled = env_bool("QMT_ENABLE_LIVE_TRADING", False)
    require_confirmation = env_bool("QMT_REQUIRE_CONFIRMATION", True)
    status = {
        "connectorType": "live",
        "provider": "qmt",
        "tradingMode": "live" if live_trading_enabled else "dry_run_only",
        "configured": bool(qmt_path and account_id),
        "connected": None,
        "liveTradingEnabled": live_trading_enabled,
        "requireConfirmation": require_confirmation,
        "account": {
            "accountId": mask_account_id(account_id),
            "accountType": os.environ.get("QMT_ACCOUNT_TYPE", "STOCK"),
            "qmtUserdataPathConfigured": bool(qmt_path),
            "pythonCommand": os.environ.get("QMT_PYTHON", "python3"),
        },
        "capabilities": [
            "broker_status",
            "dry_run_order",
            "place_order",
            "cancel_order",
            "query_orders",
            "query_positions",
            "query_cash",
        ],
        "safety": {
            "realOrders": live_trading_enabled,
            "requiresExplicitConfirmation": require_confirmation,
            "note": "Real QMT orders require QMT_ENABLE_LIVE_TRADING=true and confirmed=true when confirmation is enabled.",
        },
    }

    if params.get("checkConnection"):
        try:
            connect_qmt()
            status["connected"] = True
        except Exception as exc:
            status["connected"] = False
            status["reason"] = str(exc)

    return status


def get_cash_amount(asset):
    return float(
        get_attr(
            asset,
            [
                "cash",
                "available_cash",
                "m_dAvailable",
                "enable_balance",
                "available",
                "fetch_balance",
            ],
            0,
        )
        or 0
    )


def get_total_asset(asset):
    return float(
        get_attr(
            asset,
            [
                "total_asset",
                "m_dBalance",
                "balance",
                "asset_balance",
                "nav_asset",
            ],
            get_cash_amount(asset),
        )
        or 0
    )


def get_position_quantity(position):
    return float(get_attr(position, ["volume", "quantity", "current_amount"], 0) or 0)


def get_position_available(position):
    return float(
        get_attr(
            position,
            ["can_use_volume", "available_volume", "enable_amount", "available"],
            get_position_quantity(position),
        )
        or 0
    )


def query_cash(_params=None):
    connect_qmt()
    asset = TRADER.query_stock_asset(ACCOUNT)
    return {
        "cash": get_cash_amount(asset),
        "available": get_cash_amount(asset),
        "totalAsset": get_total_asset(asset),
        "raw": object_to_dict(asset),
    }


def query_positions(params=None):
    connect_qmt()
    params = params or {}
    symbol = normalize_symbol(params["symbol"]) if params.get("symbol") else None
    raw_positions = TRADER.query_stock_positions(ACCOUNT) or []
    positions = []

    for position in raw_positions:
        stock_code = normalize_symbol(get_attr(position, ["stock_code", "symbol", "code"], ""))
        if symbol and stock_code != symbol:
            continue
        quantity = get_position_quantity(position)
        if quantity == 0:
            continue
        positions.append(
            {
                "symbol": stock_code,
                "quantity": quantity,
                "available": get_position_available(position),
                "costPrice": get_attr(position, ["open_price", "cost_price", "avg_price"], None),
                "raw": object_to_dict(position),
            }
        )

    return {"positions": positions}


def resolve_order_price(params):
    order_type = params["orderType"]
    if order_type == "limit":
        price = params.get("limitPrice")
        if not price or float(price) <= 0:
            raise RuntimeError("limitPrice is required for limit orders.")
        return float(price)

    price = params.get("referencePrice")
    if price and float(price) > 0:
        return float(price)
    return None


def dry_run_order(params):
    connect_qmt()
    symbol = normalize_symbol(params["symbol"])
    side = params["side"]
    quantity = float(params["quantity"])
    if quantity <= 0:
        return {"accepted": False, "reason": "quantity must be greater than 0.", "symbol": symbol}

    price = resolve_order_price(params)
    cash = query_cash()
    positions = query_positions({"symbol": symbol})["positions"]
    available_position = positions[0]["available"] if positions else 0

    estimated_cash_impact = None
    if price is not None:
        gross = round(price * quantity, 4)
        estimated_cash_impact = -gross if side == "buy" else gross
        if side == "buy" and cash["available"] + estimated_cash_impact < 0:
            return {
                "accepted": False,
                "reason": "insufficient available cash.",
                "symbol": symbol,
                "estimatedCashImpact": estimated_cash_impact,
                "estimatedPositionImpact": quantity,
                "availableCash": cash["available"],
            }

    if side == "sell" and available_position < quantity:
        return {
            "accepted": False,
            "reason": "insufficient sellable position.",
            "symbol": symbol,
            "estimatedCashImpact": estimated_cash_impact,
            "estimatedPositionImpact": -quantity,
            "availablePosition": available_position,
        }

    return {
        "accepted": True,
        "symbol": symbol,
        "estimatedCashImpact": estimated_cash_impact,
        "estimatedPositionImpact": quantity if side == "buy" else -quantity,
        "availableCash": cash["available"],
        "availablePosition": available_position,
    }


def place_order(params):
    if not env_bool("QMT_ENABLE_LIVE_TRADING", False):
        raise RuntimeError("QMT_ENABLE_LIVE_TRADING=true is required for real order submission.")
    if env_bool("QMT_REQUIRE_CONFIRMATION", True) and params.get("confirmed") is not True:
        raise RuntimeError("confirmed=true is required for place_order.")

    connect_qmt()
    dry_run = dry_run_order(params)
    if not dry_run.get("accepted"):
        return {**dry_run, "status": "rejected"}

    symbol = normalize_symbol(params["symbol"])
    side = params["side"]
    quantity = int(params["quantity"])
    order_type = XTCONSTANT.STOCK_BUY if side == "buy" else XTCONSTANT.STOCK_SELL
    if params["orderType"] == "limit":
        price_type = XTCONSTANT.FIX_PRICE
        price = float(params["limitPrice"])
    else:
        price_type = XTCONSTANT.LATEST_PRICE
        price = 0

    order_id = TRADER.order_stock(
        ACCOUNT,
        symbol,
        order_type,
        quantity,
        price_type,
        price,
        params.get("strategyName", "chat-strategy-trading"),
        params.get("orderRemark") or params.get("clientOrderId") or "chat",
    )

    return {
        "orderId": str(order_id),
        "status": "open" if int(order_id) > 0 else "rejected",
        "submittedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
    }


def cancel_order(params):
    connect_qmt()
    order_id = int(params["orderId"])
    result = TRADER.cancel_order_stock(ACCOUNT, order_id)
    return {
        "orderId": str(order_id),
        "status": "canceled" if result == 0 else "unknown",
        "rawResult": result,
    }


def normalize_order_status(raw_status):
    value = str(raw_status).lower()
    if value in ("filled", "已成", "56"):
        return "filled"
    if value in ("canceled", "已撤", "57"):
        return "canceled"
    if value in ("rejected", "废单", "失败"):
        return "rejected"
    if value in ("open", "未报", "已报", "部成", "50", "51", "52", "55"):
        return "open"
    return "unknown"


def query_orders(params=None):
    connect_qmt()
    params = params or {}
    symbol = normalize_symbol(params["symbol"]) if params.get("symbol") else None
    status = params.get("status")
    raw_orders = TRADER.query_stock_orders(ACCOUNT) or []
    orders = []

    for order in raw_orders:
        stock_code = normalize_symbol(get_attr(order, ["stock_code", "symbol", "code"], ""))
        normalized_status = normalize_order_status(
            get_attr(order, ["order_status", "status", "entrust_status"], "unknown")
        )
        if symbol and stock_code != symbol:
            continue
        if status and normalized_status != status:
            continue
        orders.append(
            {
                "orderId": str(get_attr(order, ["order_id", "entrust_no", "order_sysid"], "")),
                "symbol": stock_code,
                "status": normalized_status,
                "quantity": get_attr(order, ["order_volume", "volume", "entrust_amount"], None),
                "price": get_attr(order, ["price", "order_price", "entrust_price"], None),
                "raw": object_to_dict(order),
            }
        )

    return {"orders": orders}


METHODS = {
    "broker_status": broker_status,
    "dry_run_order": dry_run_order,
    "place_order": place_order,
    "cancel_order": cancel_order,
    "query_orders": query_orders,
    "query_positions": query_positions,
    "query_cash": query_cash,
}


def respond(message_id, result=None, error=None):
    payload = {"id": message_id}
    if error:
        payload["error"] = error
    else:
        payload["result"] = result
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            method = message.get("method")
            params = message.get("params") or {}
            if method not in METHODS:
                raise RuntimeError(f"Unknown method: {method}")
            result = METHODS[method](params)
            respond(message.get("id"), result=result)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            respond(message.get("id") if "message" in locals() else None, error=str(exc))


if __name__ == "__main__":
    main()
