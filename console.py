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

# Create a database session
db = next(get_db())

# Initialize Binance client
client = Spot(
    api_key=os.getenv("BINANCE_API_KEY"),
    api_secret=os.getenv("BINANCE_API_SECRET"),
    base_url='https://testnet.binance.vision' if os.getenv("BINANCE_TESTNET") == '1' else 'https://api.binance.com'
)

# Create trading service
trading_service = TradingService(client=client, db=db)
bot = db.query(Bot).first()
cycle = db.query(TradingCycle).first()

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
