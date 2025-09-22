from __future__ import annotations
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# 1) Загрузка цен — сначала yfinance, затем безопасный фолбэк
def _try_import_yf():
    try:
        import yfinance as yf  # type: ignore
        return yf
    except Exception:
        return None

def fetch_last_close(ticker: str) -> Optional[float]:
    """
    Пытаемся взять последнее закрытие через yfinance за 5 дней.
    Если не удалось — возвращаем None (сервис всё равно отдаст ответ).
    """
    yf = _try_import_yf()
    if yf is None:
        return None
    try:
        data = yf.Ticker(ticker).history(period="5d", auto_adjust=False)
        if not data.empty:
            return float(round(data["Close"].iloc[-1], 2))
    except Exception:
        pass
    return None

def fetch_many_last_close(tickers: List[str]) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for t in tickers:
        out[t] = fetch_last_close(t)
    return out

# 2) Бенчмарк SPY — простой helper
def fetch_spy_last_close() -> Optional[float]:
    return fetch_last_close("SPY")
