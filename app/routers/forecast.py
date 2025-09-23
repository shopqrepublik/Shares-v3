from fastapi import APIRouter, Query
from app.ml.forecast import predict_linear, predict_lstm

router = APIRouter()

@router.get("/{symbol}")
def forecast(symbol: str, model: str = Query("linear", enum=["linear","lstm"]), horizon_days: int = 252):
    symbol = symbol.upper()
    if model == "linear":
        return predict_linear(symbol, horizon_days)
    else:
        return predict_lstm(symbol, horizon_days)
