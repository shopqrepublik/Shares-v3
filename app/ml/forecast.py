from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LinearRegression
import os

USE_TORCH = os.getenv("USE_TORCH","1") == "1"
if USE_TORCH:
    import torch
    import torch.nn as nn

def _load_prices(symbol: str, years: int = 5):
    end = datetime.utcnow().date()
    start = end - timedelta(days=365*years)
    s = yf.download(symbol, start=start, end=end, progress=False)["Adj Close"].dropna()
    return s

def predict_linear(symbol: str, horizon_days: int = 252):
    s = _load_prices(symbol)
    y = s.values.reshape(-1,1)
    X = np.arange(len(y)).reshape(-1,1)
    model = LinearRegression().fit(X, y)
    future_X = np.arange(len(y), len(y)+horizon_days).reshape(-1,1)
    y_hat = model.predict(future_X).flatten()
    return {"method":"linear_regression","last_price": float(y[-1][0]), "forecast": y_hat.tolist()}

class SimpleLSTM(nn.Module):
    def __init__(self, input_size=1, hidden_size=16):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)
    def forward(self, x):
        out,_ = self.lstm(x)
        return self.fc(out[:,-1,:])

def predict_lstm(symbol: str, horizon_days: int = 252, lookback: int = 30, epochs: int = 10):
    if not USE_TORCH:
        return {"method":"lstm","disabled":True}
    s = _load_prices(symbol)
    arr = s.values.astype(np.float32)
    X, y = [], []
    for i in range(len(arr)-lookback):
        X.append(arr[i:i+lookback])
        y.append(arr[i+lookback])
    X = torch.tensor(np.array(X)).unsqueeze(-1)  # (N, lookback, 1)
    y = torch.tensor(np.array(y)).unsqueeze(-1)  # (N, 1)

    model = SimpleLSTM()
    loss_fn = nn.MSELoss()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)

    model.train()
    for _ in range(epochs):
        opt.zero_grad()
        pred = model(X)
        loss = loss_fn(pred, y)
        loss.backward()
        opt.step()

    # наивное авто-продление: последний «окно» + autoregressive one-step
    model.eval()
    last = torch.tensor(arr[-lookback:], dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
    preds = []
    for _ in range(horizon_days):
        with torch.no_grad():
            nxt = model(last).item()
        preds.append(nxt)
        last = torch.cat([last[:,1:,:], torch.tensor([[[nxt]]])], dim=1)

    return {"method":"lstm","last_price": float(arr[-1]), "forecast": preds}
