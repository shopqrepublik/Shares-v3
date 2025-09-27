import pandas as pd
import json

def fetch_sp500_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    table = pd.read_html(url)[0]
    return table["Symbol"].tolist()

def fetch_nasdaq100_tickers():
    url = "https://en.wikipedia.org/wiki/NASDAQ-100"
    table = pd.read_html(url)[4]
    return table["Ticker"].tolist()

if __name__ == "__main__":
    sp500 = fetch_sp500_tickers()
    nasdaq100 = fetch_nasdaq100_tickers()

    with open("sp500.json", "w") as f:
        json.dump(sp500, f)

    with open("nasdaq100.json", "w") as f:
        json.dump(nasdaq100, f)

    print(f"✅ Обновлено: {len(sp500)} S&P500 и {len(nasdaq100)} NASDAQ100")
