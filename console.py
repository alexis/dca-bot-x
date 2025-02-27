#!/usr/bin/env python3
import os
import sys
from IPython import embed
from app.database import get_db,engine
from app.models import Bot, TradingCycle, Order
from app.services.trading_service import TradingService
from app.enums import *
from decimal import Decimal
from binance.spot import Spot
import logging

# Configure SQLAlchemy logging
# logging.basicConfig()
# logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Create a database session
db = next(get_db())

# Initialize Binance client
client = Spot(
    api_key=os.getenv("BINANCE_API_KEY"),
    api_secret=os.getenv("BINANCE_API_SECRET"),
    base_url='https://testnet.binance.vision' if os.getenv("BINANCE_TESTNET") == '1' else 'https://api.binance.com'
)

bots = db.query(Bot)
bot = bots.first()
trading_service = TradingService(db=db, bot=bot)
cycle = trading_service.cycle

# Create an IPython shell context
context = {
    'db': db,
    'Bot': Bot,
    'TradingCycle': TradingCycle,
    'Order': Order,
    'TradingService': TradingService,
    'trading_service': trading_service,
    'client': client,
    'Decimal': Decimal,
    'ExchangeType': ExchangeType,
    'SymbolType': SymbolType,
    'BotStatusType': BotStatusType,
    'OrderStatusType': OrderStatusType,
    'SideType': SideType,
    'TimeInForceType': TimeInForceType,
    'OrderType': OrderType,
    'CycleStatusType': CycleStatusType,
    'bots': list(bots),
    'bot': bot,
    'cycle': cycle,
}

print("Welcome to DCA Bot Shell!")
print("\nExample usage:")
print("bot = db.query(Bot).first()")
print("cycle = db.query(TradingCycle).first()")
print("orders = db.query(Order).all()")
print("price = client.ticker_price(symbol='BTCUSDT')")

embed(colors="neutral", user_ns=context)
