import uuid
from datetime import datetime, UTC
from sqlalchemy import Column, Float, String, Boolean, Integer, JSON, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
from .enums import *

Base = declarative_base()

class Bot(Base):
    __tablename__ = "bots"

    trading_cycles = relationship("TradingCycle", back_populates="bot")

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    api_key = Column(String(100), nullable=False)
    api_secret = Column(String(100), nullable=False)
    exchange = Column(String(20), nullable=False)
    symbol = Column(String(20), nullable=False)
    amount = Column(Float, nullable=False)
    grid_length = Column(Float, nullable=False)
    first_order_offset = Column(Float, nullable=False)
    num_orders = Column(Integer, nullable=False)
    partial_num_orders = Column(Integer, nullable=False)
    next_order_volume = Column(Float, nullable=False)
    profit_percentage = Column(Float, nullable=False)
    price_change_percentage = Column(Float, nullable=False)
    upper_price_limit = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.now(UTC))
    updated_at = Column(DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC))

class TradingCycle(Base):
    __tablename__ = "trading_cycles"

    bot = relationship("Bot", back_populates="trading_cycles")
    orders = relationship("Order", back_populates="cycle")
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bot_id = Column(UUID(as_uuid=True), ForeignKey('bots.id'), nullable=True)
    exchange = Column(String(20), nullable=False)
    symbol = Column(String(20), nullable=False)
    amount = Column(Float, nullable=False)
    grid_length = Column(Float, nullable=False)
    first_order_offset = Column(Float, nullable=False)
    num_orders = Column(Integer, nullable=False)
    partial_num_orders = Column(Integer, nullable=False)
    next_order_volume = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    profit_percentage = Column(Float, nullable=False)
    status = Column(String(20), nullable=False)
    price_change_percentage = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.now(UTC))
    updated_at = Column(DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC))

class Order(Base):
    __tablename__ = "orders"

    cycle = relationship("TradingCycle", back_populates="orders")

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey('trading_cycles.id'), nullable=False)
    exchange = Column(String(20), nullable=False)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    time_in_force = Column(String(10), nullable=False)
    type = Column(String(20), nullable=False)
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    status = Column(String(20), nullable=False)
    number = Column(Integer, nullable=False)
    exchange_order_id = Column(String(100), nullable=False)
    exchange_order_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now(UTC))
    updated_at = Column(DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC))
