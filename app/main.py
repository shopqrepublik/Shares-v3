import logging, sys
from fastapi import FastAPI

# ---------------- LOGGING ----------------
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.debug("🚀 main.py started loading")

# ---------------- APP ----------------
app = FastAPI(title="AI Portfolio Bot", version="0.1")

# ---------------- ROUTES ----------------

@app.get("/ping", tags=["health"])
def ping():
    return {"message": "pong"}

@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",           # фиксируем "ok" для Railway
        "service": "ai-portfolio-bot",
        "db_ready": False,        # пока базы нет
        "db_error": None
    }

@app.get("/", tags=["health"])
def root():
    return {"ok": True, "service": "ai-portfolio-bot"}
