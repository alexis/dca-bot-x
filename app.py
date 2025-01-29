from fastapi import FastAPI, WebSocket, Request, HTTPException, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from binance.client import Client
import asyncio
import logging
import json
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
BINANCE_TESTNET = os.getenv("BINANCE_TESTNET") == '1'

client = Client(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=BINANCE_TESTNET)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.route('/balance')
async def balance(request: Request):
    balance = [x for x in client.get_asset_balance() if x['asset'] in ['USDT', 'ETH', 'BTC']]
    return JSONResponse(content=balance)

@app.post("/order")
async def place_order(request: Request):
    data = await request.json()
    pair = data.get("pair", "BTCUSDT")
    price = data.get("price", "25000")
    quantity = data.get("quantity", "0.001")

    try:
        order = client.create_order(
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
            ticker = client.get_symbol_ticker(symbol="BTCUSDT")
            price = ticker["price"]
            await websocket.send_text(json.dumps({"price": price}))
            await asyncio.sleep(1)  # Send price updates every second
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            break
