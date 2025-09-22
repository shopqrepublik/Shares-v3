# AI Portfolio Bot (MVP)

Educational bot that builds and tracks an investment portfolio using Alpaca (paper trading) and OpenAI.

## Features
- User onboarding (budget, risk profile)
- Portfolio generation (ETF/core, optional micro-caps)
- Daily/weekly reporting vs benchmark (SPY)
- Educational insights from LLM (not financial advice!)

## Setup
1. Clone repo and create `.env` from `.env.example` with your keys.
2. Install deps: `pip install -r requirements.txt`
3. Run: `uvicorn app.main:app --reload`
4. Open docs: `http://127.0.0.1:8000/docs`

## Disclaimer
This project is for **educational purposes only**. Not investment advice.
