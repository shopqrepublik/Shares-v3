from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple
import os
import math
import time

import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.models import Position

ETF_WHITELIST = {"SPY","VOO","QQQ","VGT","AGG","IXUS"}

def _get_bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None: 
        return default
    return str(v).lower() in {"1","true","yes","y","on"}

@dataclass
class RailConfig:
    max_weight_stock: float = float(os.getenv("MAX_WEIGHT_STOCK", 0.10))
    max_weight_etf: float = float(os.getenv("MAX_WEIGHT_ETF", 0.20))
    max_microcap_weight: float = float(os.getenv("MAX_WEIGHT_MICROCAP_TOTAL", 0.20))
    min_price: float = float(os.getenv("MIN_PRICE", 1.0))
    min_avg_dollar_vol: float = float(os.getenv("MIN_ADV_USD", 1_000_000))
    cash_buffer: float = float(os.getenv("CASH_BUFFER", 0.05))
    market_hours_only: bool = _get_bool_env("MARKET_HOURS_ONLY", True)
    allow_shorts: bool = _get_bool_env("ALLOW_SHORTS", False)
    max_order_usd: float = float(os.getenv("MAX_ORDER_USD", 5000))
    max_position_usd: float = float(os.getenv("MAX_POSITION_USD", 20000))

def is_etf(ticker: str) -> bool:
    return ticker.upper() in ETF_WHITELIST

def is_microcap(ticker: str) -> bool:
    try:
        fi = yf.Ticker(ticker).fast_info
        mc = getattr(fi, "market_cap", None)
        if mc is None:
            return False
        return mc < 300_000_000  # <$300M
    except Exception:
        return False

def last_price(ticker: str) -> float:
    hist = yf.Ticker(ticker).history(period="5d")
    if hist.empty:
        raise ValueError(f"No price for {ticker}")
    return float(hist["Close"].iloc[-1])

def avg_dollar_volume(ticker: str, days: int = 20) -> float:
    hist = yf.Ticker(ticker).history(period="2mo")
    if hist.empty:
        return 0.0
    df = hist.tail(days)
    if df.empty or "Volume" not in df.columns:
        return 0.0
    return float((df["Close"] * df["Volume"]).mean())

def check_market_open(trading: TradingClient) -> Tuple[bool, str]:
    try:
        clock = trading.get_clock()
        if clock.is_open:
            return True, "market open"
        return False, "market closed"
    except Exception as e:
        return False, f"clock error: {e}"

def validate_allocation(allocations: List[Dict], budget: float, cfg: RailConfig) -> Tuple[bool, Dict]:
    errors, warnings = [], []
    weights_sum = sum(float(a["target_weight"]) for a in allocations)
    microcap_weight = 0.0

    for a in allocations:
        t = a["ticker"].upper()
        w = float(a["target_weight"])

        try:
            p = last_price(t)
        except Exception as e:
            errors.append(f"{t}: price error ({e})")
            continue

        if p < cfg.min_price:
            errors.append(f"{t}: price {p:.2f} < min {cfg.min_price}")
        adv = avg_dollar_volume(t)
        if adv < cfg.min_avg_dollar_vol:
            warnings.append(f"{t}: low ADV ${adv:,.0f} (< ${cfg.min_avg_dollar_vol:,.0f})")

        if is_etf(t):
            if w > cfg.max_weight_etf:
                errors.append(f"{t}: weight {w:.2%} > ETF cap {cfg.max_weight_etf:.0%}")
        else:
            if w > cfg.max_weight_stock:
                errors.append(f"{t}: weight {w:.2%} > stock cap {cfg.max_weight_stock:.0%}")

        if is_microcap(t):
            microcap_weight += w

    if microcap_weight > cfg.max_microcap_weight:
        errors.append(f"micro-cap exposure {microcap_weight:.2%} > {cfg.max_microcap_weight:.0%} limit")
    if not math.isclose(weights_sum, 1.0, rel_tol=1e-3, abs_tol=1e-3):
        warnings.append(f"weights sum is {weights_sum:.3f} (will renormalize).")

    ok = len(errors) == 0
    return ok, {"errors": errors, "warnings": warnings, "weights_sum": weights_sum, "microcap_weight": microcap_weight}

def get_current_positions_value(trading: TradingClient) -> Dict[str, float]:
    """Returns {ticker: market_value_usd} of current positions."""
    pos = trading.get_all_positions()
    res = {}
    for p in pos:
        res[p.symbol.upper()] = float(p.market_value)
    return res

def rebalance_plan(trading: TradingClient, allocations: List[Dict], budget: float, cfg: RailConfig) -> Tuple[List[Dict], List[Dict]]:
    """
    Returns (sells, buys) lists. Each item: {ticker, qty, est_value}
    Uses current positions from Alpaca, target weights on (budget * (1-cash_buffer)).
    Caps per-order and per-position.
    """
    # normalize weights
    wsum = sum(float(a["target_weight"]) for a in allocations)
    norm = [{ "ticker": a["ticker"].upper(), "target_weight": float(a["target_weight"])/wsum } for a in allocations if wsum > 0]

    invest_budget = budget * (1 - cfg.cash_buffer)
    current = get_current_positions_value(trading)  # USD by ticker
    # estimate last prices for all tickers (for qty rounding)
    prices = {a["ticker"]: last_price(a["ticker"]) for a in norm}

    # desired values
    desired = {a["ticker"]: invest_budget * a["target_weight"] for a in norm}

    sells, buys = [], []
    # Plan sells for tickers that exceed desired value or not in target (desired 0)
    universe = set(list(current.keys()) + [a["ticker"] for a in norm])
    for t in universe:
        cur = current.get(t, 0.0)
        des = desired.get(t, 0.0)
        price = prices.get(t) or (last_price(t) if des>0 else None)
        if cur > des + 1:  # sell excess
            over = cur - des
            sell_value = min(over, cfg.max_order_usd)
            if price and sell_value > price:
                qty = int(sell_value // price)
                if qty > 0:
                    sells.append({"ticker": t, "qty": qty, "est_value": round(qty*price,2)})
        elif des > cur + 1:  # buy deficit
            need = des - cur
            buy_value = min(need, cfg.max_order_usd)
            price = price or last_price(t)
            # enforce max position cap: current + buy_value <= cap
            cap = cfg.max_position_usd
            allowed = max(0.0, cap - cur)
            buy_value = min(buy_value, allowed)
            if buy_value > price:
                qty = int(buy_value // price)
                if qty > 0:
                    buys.append({"ticker": t, "qty": qty, "est_value": round(qty*price,2)})
    return sells, buys

def submit_orders(trading: TradingClient, orders: List[Dict], side: str) -> List[Dict]:
    placed = []
    for o in orders:
        req = MarketOrderRequest(
            symbol=o["ticker"],
            qty=o["qty"],
            side=OrderSide.SELL if side.upper()=="SELL" else OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        order = trading.submit_order(req)
        placed.append({"ticker": o["ticker"], "qty": o["qty"], "order_id": order.id, "side": side.upper()})
        time.sleep(0.2)
    return placed

def rebalance_with_guardrails(trading: TradingClient, allocations: List[Dict], budget: float, submit: bool, cfg: RailConfig = RailConfig()) -> Dict:
    ok, report = validate_allocation(allocations, budget, cfg)
    sells, buys = rebalance_plan(trading, allocations, budget, cfg)
    result = {
        "ok": ok,
        "errors": report["errors"],
        "warnings": report["warnings"],
        "preview": {"sell": sells, "buy": buys},
    }
    if not ok:
        result["note"] = "Validation failed. Orders not submitted."
        return result

    if cfg.market_hours_only:
        open_, msg = check_market_open(trading)
        if not open_:
            result["note"] = f"Guardrails: {msg}. Orders not submitted."
            return result

    if submit:
        placed_sell = submit_orders(trading, sells, "SELL") if sells else []
        placed_buy = submit_orders(trading, buys, "BUY") if buys else []
        result["placed"] = {"sell": placed_sell, "buy": placed_buy}
        result["note"] = "Orders submitted to Alpaca."
    else:
        result["note"] = "Validation passed. Set submit=true to place orders."
    return result
