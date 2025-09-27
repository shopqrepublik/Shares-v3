import os
import json
import requests
import pandas as pd
from io import StringIO

DATA_DIR = "app/data"

def fetch_sp500_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": "Mozilla/5.0"}
    html = requests.get(url, headers=headers).text
    table = pd.read_html(StringIO(html))[0]
    return table["Symbol"].dropna().tolist()

def fetch_nasdaq100_tickers():
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    headers = {"User-Agent": "Mozilla/5.0"}
    html = requests.get(url, headers=headers).text
    tables = pd.read_html(StringIO(html))

    # ищем таблицу, где есть колонка с тикерами
    for table in tables:
        for col in table.columns:
            if col in ["Ticker", "Symbol"]:
                return table[col].dropna().tolist()

    raise ValueError("Не найдена колонка Ticker или Symbol в таблицах NASDAQ-100")

def save_tickers():
    os.makedirs(DATA_DIR, exist_ok=True)

    sp500 = fetch_sp500_tickers()
    nasdaq100 = fetch_nasdaq100_tickers()

    with open(os.path.join(DATA_DIR, "sp500.json"), "w") as f:
        json.dump(sp500, f)

    with open(os.path.join(DATA_DIR, "nasdaq100.json"), "w") as f:
        json.dump(nasdaq100, f)

    print(f"✅ Обновлено: {len(sp500)} S&P500 и {len(nasdaq100)} NASDAQ100")
    print("Примеры:")
    print("S&P500 →", sp500[:5])
    print("NASDAQ100 →", nasdaq100[:5])

if __name__ == "__main__":
    save_tickers()
