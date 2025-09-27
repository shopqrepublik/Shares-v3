import pandas as pd
import requests
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_sp500_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    html = requests.get(url, headers=headers).text
    table = pd.read_html(html)[0]  # первая таблица на странице
    return table["Symbol"].tolist()

def fetch_nasdaq100_tickers():
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    html = requests.get(url, headers=headers).text
    tables = pd.read_html(html)
    table = tables[3]  # на странице несколько таблиц, нужная обычно 3-я
    return table["Ticker"].tolist()

def save_tickers():
    sp500 = fetch_sp500_tickers()
    nasdaq100 = fetch_nasdaq100_tickers()

    with open(os.path.join(DATA_DIR, "sp500.json"), "w") as f:
        json.dump(sp500, f)

    with open(os.path.join(DATA_DIR, "nasdaq100.json"), "w") as f:
        json.dump(nasdaq100, f)

    return {"sp500": len(sp500), "nasdaq100": len(nasdaq100)}

if __name__ == "__main__":
    result = save_tickers()
    print("✅ Tickers updated:", result)
