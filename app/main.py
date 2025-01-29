from fastapi import FastAPI, WebSocket, Request, Query, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from binance.spot import Spot
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import asyncio
import logging
import json
import os
from typing import List, Optional
from uuid import UUID, uuid4
from .models import Base, Bot, TradingCycle, Order, ExchangeKey
from .schemas import (
    BotCreate, BotResponse,
    TradingCycleCreate, TradingCycleResponse,
    OrderCreate, OrderResponse,
    ExchangeKeyCreate, ExchangeKeyResponse
)
from .enums import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Get the absolute path to the templates directory
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)

# Binance client configuration
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
BINANCE_TESTNET = os.getenv("BINANCE_TESTNET") == '1'

# Initialize Binance client
client = Spot(
    api_key=BINANCE_API_KEY,
    api_secret=BINANCE_API_SECRET,
    base_url='https://testnet.binance.vision' if BINANCE_TESTNET else 'https://api.binance.com'
)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get('/balance')
async def balance(assets: Optional[List[str]] = Query(None)):
    try:
        client.account()
        account_info = client.account(omitZeroBalances='true')
        balances = account_info["balances"]
        if assets:
            balances = [x for x in balances if x["asset"] in set(assets)]
        return balances
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/order")
async def place_order(request: Request):
    data = await request.json()
    pair = data.get("pair", "BTCUSDT")
    price = data.get("price", "25000")
    quantity = data.get("quantity", "0.001")

    try:
        order = client.new_order(
            symbol=pair,
            side='BUY',
            type='LIMIT',
            timeInForce='GTC',
            quantity=quantity,
            price=price
        )
        return order
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")

    while True:
        try:
            btc_usdt = client.ticker_price(symbol="BTCUSDT")
            eth_usdt = client.ticker_price(symbol="ETHUSDT")
            prices = {
                "BTCUSDT": btc_usdt["price"],
                "ETHUSDT": eth_usdt["price"]
            }
            await websocket.send_text(json.dumps(prices))
            await asyncio.sleep(1)  # Send price updates every second
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            break
