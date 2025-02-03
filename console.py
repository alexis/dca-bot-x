#!/usr/bin/env python3
import os
import sys
from IPython import embed
from app.database import get_db,engine
from app.models import Bot, TradingCycle, Order
from app.services.trading_service import TradingService
from app.enums import *
from decimal import Decimal

# Create a database session
db = next(get_db())

# Create an IPython shell context
context = {
    'db': db,
    'Bot': Bot,
    'TradingCycle': TradingCycle,
    'Order': Order,
    'TradingService': TradingService,
    'Decimal': Decimal,
    'ExchangeType': ExchangeType,
    'SymbolType': SymbolType,
    'BotStatusType': BotStatusType,
    'OrderStatusType': OrderStatusType,
    'SideType': SideType,
    'TimeInForceType': TimeInForceType,
    'OrderType': OrderType,
    'CycleStatusType': CycleStatusType,
}

print("Welcome to DCA Bot Shell!")
print("Available objects:", ", ".join(context.keys()))
print("\nExample usage:")
print("bot = db.query(Bot).first()")
print("cycle = db.query(TradingCycle).first()")
print("orders = db.query(Order).all()")

embed(colors="neutral", user_ns=context)
