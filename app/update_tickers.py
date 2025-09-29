import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

# Папка с CSV (для fallback)
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Получаем URL БД из переменной окружения
DB_URL = os.getenv("DATABASE_URL")

def get_pg_connection():
    """
    Подключение к Postgres через psycopg2
    """
    return psycopg2.connect(DB_URL)


def update_tickers_from_sources():
    """
    Загружаем тикеры из Википедии (SP500, NASDAQ100).
    Если не удаётся — fallback на локальные CSV.
    Обновляем таблицу tickers в БД.
    """

    sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    nasdaq100_url = "https://en.wikipedia.org/wiki/NASDAQ-100"

    try:
        # 1️⃣ Пытаемся загрузить с Википедии
        sp500 = pd.read_html(sp500_url)[0]["Symbol"].tolist()
        nasdaq100 = pd.read_html(nasdaq100_url)[3]["Ticker"].tolist()
        print(f"[TICKERS] Успешно загружено с Википедии: SP500={len(sp500)}, NASDAQ100={len(nasdaq100)}")
    except Exception as e:
        # 2️⃣ Если не получилось — берём из CSV
        print(f"[TICKERS] Ошибка при загрузке с Википедии: {e}")
        sp500 = pd.read_csv(os.path.join(DATA_DIR, "tickers_sp500.csv"))["Symbol"].tolist()
        nasdaq100 = pd.read_csv(os.path.join(DATA_DIR, "tickers_nasdaq100.csv"))["Symbol"].tolist()
        print(f"[TICKERS] Загружено из CSV: SP500={len(sp500)}, NASDAQ100={len(nasdaq100)}")

    # Формируем список для записи в БД
    now = datetime.utcnow()
    all_tickers = []
    for sym in sp500:
        all_tickers.append(("SP500", sym, now))
    for sym in nasdaq100:
        all_tickers.append(("NASDAQ100", sym, now))

    # Записываем в БД
    conn = get_pg_connection()
    cur = conn.cursor()

    # Чистим старые записи
    cur.execute("DELETE FROM tickers WHERE index_name IN ('SP500','NASDAQ100') OR index_name IS NULL;")

    # Вставляем новые
    execute_values(
        cur,
        "INSERT INTO tickers (index_name, symbol, updated_at) VALUES %s",
        all_tickers,
        page_size=500
    )

    conn.commit()
    cur.close()
    conn.close()

    print(f"[TICKERS] ✅ Обновление завершено: всего {len(all_tickers)}, SP500={len(sp500)}, NASDAQ100={len(nasdaq100)}")

    return {
        "status": "ok",
        "total": len(all_tickers),
        "sp500_count": len(sp500),
        "nasdaq100_count": len(nasdaq100)
    }
