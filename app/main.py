import asyncio
import json
import logging
import os
from decimal import Decimal
from typing import List, Optional

from binance.spot import Spot
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing_extensions import Doc, IntVar

from .database import engine, get_db
from .models import Base, Bot
from .routes import bot
from .services.bot_manager import BotManager
from .services.trading_service import TradingService
from .services.bot_events_handler import BotEventsHandler

# Create tables
Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.DEBUG)

app = FastAPI()
bot_manager = BotManager(TradingService, BotEventsHandler)

ENV = os.getenv("ENV", "development")

# Get the absolute path to the templates directory
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Include bot routes
#app.include_router(bot.router, prefix="/api/v1") # XXX

# Initialize Binance client
client = Spot(
    api_key=os.getenv("BINANCE_API_KEY"),
    api_secret=os.getenv("BINANCE_API_SECRET"),
    base_url="https://testnet.binance.vision"
    if os.getenv("BINANCE_TESTNET")
    else "https://api.binance.com",
)
logging.info(f"Using {client.base_url} for Binance API")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Log the validation error details
    logging.error(f"Validation error on request: {request.url.path}")
    logging.error(f"Validation error details: {exc.errors()}")

    # Return a custom response (optional)
    # return HTMLResponse(
    #     status_code=422,
    #     content=exc.errors(),
    # )

@app.on_event("startup")
async def startup_event():
    db = next(get_db())
    bots = db.query(Bot).filter(Bot.is_active).all()

    # Initialize trading service and websocket manager for each bot
    await bot_manager.install_bots(bots)

@app.on_event("shutdown")
async def shutdown_event():
    await bot_manager.release_all()


@app.get("/")
async def home():
    return RedirectResponse(url="/bots", status_code=302)


@app.get("/bots", response_class=HTMLResponse)
async def list_bots(request: Request, db: Session = Depends(get_db)):
    bots = db.query(Bot).all()
    return templates.TemplateResponse("bots.html", {"request": request, "bots": bots})


@app.get("/bots/{bot_id}", response_class=HTMLResponse)
async def bot_detail(request: Request, bot_id: str, db: Session = Depends(get_db)):
    bot_obj = db.query(Bot).filter(Bot.id == bot_id).first()
    current_cycle = TradingService(bot=bot_obj, db=db).cycle
    if not bot_obj:
        raise HTTPException(status_code=404, detail="Bot not found")

    return templates.TemplateResponse("bot_details.html", {"request": request, "bot": bot_obj,
                                                           "current_cycle": current_cycle })

@app.get("/bots/{bot_id}/dashboard", response_class=HTMLResponse)
async def bot_dashboard(request: Request, bot_id: str, db: Session = Depends(get_db)):
    bot_obj = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot_obj:
        raise HTTPException(status_code=404, detail="Bot not found")

    return templates.TemplateResponse("bot_dashboard.html", {"request": request, "bot": bot_obj })

@app.put("/bots/{bot_id}")
async def update_bot(
    bot_id: str,
    name: str = Form(...),
    is_active: str = Form(...),
    symbol: str = Form(...),
    amount: Decimal = Form(...),
    grid_length: Decimal = Form(...),
    first_order_offset: Decimal = Form(...),
    profit_percentage: Decimal = Form(...),
    price_change_percentage: Decimal = Form(...),
    num_orders: int = Form(...),
    db: Session = Depends(get_db)
):
    bot_obj = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot_obj:
        raise HTTPException(status_code=404, detail="Bot not found")

    try:
        bot_obj.name = name
        #bot_obj.is_active = is_active # XXX
        bot_obj.symbol = symbol
        bot_obj.amount = amount
        bot_obj.grid_length = grid_length
        bot_obj.first_order_offset = first_order_offset
        bot_obj.num_orders = num_orders
        bot_obj.profit_percentage = profit_percentage
        bot_obj.price_change_percentage = price_change_percentage
        bot_obj.upper_price_limit = 0 # XXX

        db.commit()
        return "Bot updated."
    except Exception as e:
        logging.error(f"Error placing order: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/bots/")
async def create_bot(
    name: str = Form(...),
    api_key: str = Form(...),
    api_secret: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        new_bot = Bot(
            name=name,
            api_key=api_key,
            api_secret=api_secret,
            is_active=False,
            status='STOPPED',
            exchange="binance",
            symbol="BTCUSDT",              # default trading pair
            amount=Decimal("100"),         # default amount (e.g., investment capital)
            grid_length=Decimal("10"),     # (%)
            num_orders=5,
            first_order_offset=Decimal("1"),  # (%)
            next_order_volume=Decimal("20"),  # (%)
            profit_percentage=Decimal("5"),     # (%)
            price_change_percentage=Decimal("1"),  # (%)
            upper_price_limit=Decimal("0"),        # XXX
        )
        db.add(new_bot)
        db.commit()

        return RedirectResponse(url="/bots", status_code=302)
    except Exception as e:
        logging.error(f"Error placing order: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/balance")
async def balance(assets: Optional[List[str]] = Query(None)):
    try:
        client.account()
        account_info = client.account(omitZeroBalances="true")
        balances = account_info["balances"]
        if assets:
            balances = [x for x in balances if x["asset"] in set(assets)]
        return balances
    except Exception as e:
        logging.error(f"Error getting balance: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("WebSocket connection established")

    while True:
        try:
            btc_usdt = client.ticker_price(symbol="BTCUSDT")
            eth_usdt = client.ticker_price(symbol="ETHUSDT")
            prices = {"BTCUSDT": btc_usdt["price"], "ETHUSDT": eth_usdt["price"]}
            await websocket.send_text(json.dumps(prices))
            await asyncio.sleep(0.5)  # Send price updates every 0.5 sec
        except Exception as e:
            logging.error(f"WebSocket error: {e}")
            break
