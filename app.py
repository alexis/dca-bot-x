from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from binance.spot import Spot
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import asyncio
import logging
import json
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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

# Example model
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'

# Create tables
Base.metadata.create_all(bind=engine)

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
async def balance():
    try:
        account_info = client.account()
        balances = [x for x in account_info['balances'] if float(x['free']) > 0 or float(x['locked']) > 0]
        return JSONResponse(content=balances)
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
            ticker = client.ticker_price(symbol="BTCUSDT")
            price = ticker["price"]
            await websocket.send_text(json.dumps({"price": price}))
            await asyncio.sleep(1)  # Send price updates every second
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            break

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
