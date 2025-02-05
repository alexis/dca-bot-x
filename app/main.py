from fastapi import FastAPI, WebSocket, Request, Query, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from binance.spot import Spot
import asyncio
import logging
import json
import os
from typing import List, Optional
from uuid import UUID
from .models import Base, Bot
from .database import engine, get_db
from .routes import bot
from .services.trading_service import TradingService
from .services.websocket_manager import BotWebsocketManager

# Create tables
Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.INFO)

app = FastAPI()

ENV = os.getenv('ENV', 'development')

# Get the absolute path to the templates directory
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Include bot routes
app.include_router(bot.router, prefix="/api/v1")

# Initialize Binance client
client = Spot(
  api_key=os.getenv("BINANCE_API_KEY"),
  api_secret=os.getenv("BINANCE_API_SECRET"),
  base_url='https://testnet.binance.vision' if os.getenv("BINANCE_TESTNET") else 'https://api.binance.com'
)
logging.info(f"Using {client.base_url} for Binance API")

ws_manager = None

@app.on_event("startup")
async def startup_event():
    global ws_manager

    # Initialize trading service and websocket manager
    db = next(get_db())
    bot = db.query(Bot).first()
    trading_service = TradingService(client=client, db=db)
    trading_service.launch(bot)
    listen_key = client.new_listen_key()["listenKey"]

    ws_manager = BotWebsocketManager(trading_service=trading_service, db=db, listen_key=listen_key)
    await ws_manager.start()

@app.on_event("shutdown")
async def shutdown_event():
    if ws_manager:
        await ws_manager.ws_client.close_connection()

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
        logging.error(f"Error getting balance: {e}")
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
        logging.error(f"Error placing order: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("WebSocket connection established")

    while True:
        try:
            btc_usdt = client.ticker_price(symbol="BTCUSDT")
            eth_usdt = client.ticker_price(symbol="ETHUSDT")
            prices = {
                "BTCUSDT": btc_usdt["price"],
                "ETHUSDT": eth_usdt["price"]
            }
            await websocket.send_text(json.dumps(prices))
            await asyncio.sleep(0.5)  # Send price updates every 0.5 sec
        except Exception as e:
            logging.error(f"WebSocket error: {e}")
            break
