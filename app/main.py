import os
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Config ---
API_PASSWORD = os.getenv("API_PASSWORD", "SuperSecret123")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")


# --- Helper ---
def check_api_key(request: Request):
    api_key = request.headers.get("x-api-key")
    if api_key != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")


# --- Healthcheck (без ключа) ---
@app.get("/ping")
async def ping():
    """
    Healthcheck для Railway. 
    Доступен без x-api-key.
    """
    return {"message": "pong"}


# --- Alpaca: Account info ---
@app.get("/alpaca/test")
async def alpaca_test():
    """
    Проверка подключения к Alpaca. 
    Возвращает данные аккаунта.
    """
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    }
    url = f"{ALPACA_BASE_URL}/v2/account"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=30)

        try:
            data = resp.json()
        except Exception:
            data = {"raw_text": resp.text}

        return {
            "status_code": resp.status_code,
            "url": url,
            "headers_used": {
                "APCA-API-KEY-ID": (ALPACA_API_KEY[:4] + "****") if ALPACA_API_KEY else None,
                "APCA-API-SECRET-KEY": (ALPACA_SECRET_KEY[:4] + "****") if ALPACA_SECRET_KEY else None,
            },
            "data": data,
        }
    except Exception as e:
        return {"error": str(e)}


# --- Alpaca: Positions ---
@app.get("/alpaca/positions")
async def alpaca_positions():
    """
    Получение активных позиций из Alpaca.
    """
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    }
    url = f"{ALPACA_BASE_URL}/v2/positions"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=30)

        try:
            data = resp.json()
        except Exception:
            data = {"raw_text": resp.text}

        return {
            "status_code": resp.status_code,
            "url": url,
            "headers_used": {
                "APCA-API-KEY-ID": (ALPACA_API_KEY[:4] + "****") if ALPACA_API_KEY else None,
                "APCA-API-SECRET-KEY": (ALPACA_SECRET_KEY[:4] + "****") if ALPACA_SECRET_KEY else None,
            },
            "data": data,
        }
    except Exception as e:
        return {"error": str(e)}


# --- Пример защищённого эндпоинта ---
@app.get("/secure")
async def secure_example(request: Request):
    """
    Пример защищённого эндпоинта.
    Требует заголовок x-api-key.
    """
    check_api_key(request)
    return {"status": "ok", "message": "This is a protected endpoint"}
