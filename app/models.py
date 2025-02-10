import uuid
from sqlalchemy import Column, String, Boolean, Integer, JSON, ForeignKey, DateTime, DECIMAL
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, Session
from .enums import *
from sqlalchemy.sql import func

Base = declarative_base()

class Bot(Base):
    __tablename__ = "bots"

    trading_cycles = relationship("TradingCycle", back_populates="bot", lazy="dynamic")

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    api_key = Column(String(100), nullable=False)
    api_secret = Column(String(100), nullable=False)
    exchange = Column(String(20), nullable=False)
    symbol = Column(String(20), nullable=False)
    amount = Column(DECIMAL(precision=20, scale=8), nullable=False)
    grid_length = Column(DECIMAL(precision=10, scale=2), nullable=False)
    first_order_offset = Column(DECIMAL(precision=10, scale=2), nullable=False)
    num_orders = Column(Integer, nullable=False)
    next_order_volume = Column(DECIMAL(precision=10, scale=2), nullable=False)
    profit_percentage = Column(DECIMAL(precision=10, scale=2), nullable=False)
    price_change_percentage = Column(DECIMAL(precision=10, scale=2), nullable=False)
    upper_price_limit = Column(DECIMAL(precision=20, scale=8), nullable=False)
    is_active = Column(Boolean, default=True)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class TradingCycle(Base):
    __tablename__ = "trading_cycles"

    bot = relationship("Bot", back_populates="trading_cycles")
    orders = relationship("Order", back_populates="cycle", lazy="dynamic")
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bot_id = Column(UUID(as_uuid=True), ForeignKey('bots.id'), nullable=True)
    exchange = Column(String(20), nullable=False)
    symbol = Column(String(20), nullable=False)
    amount = Column(DECIMAL(precision=20, scale=8), nullable=False)
    grid_length = Column(DECIMAL(precision=10, scale=2), nullable=False)
    first_order_offset = Column(DECIMAL(precision=10, scale=2), nullable=False)
    num_orders = Column(Integer, nullable=False)
    next_order_volume = Column(DECIMAL(precision=10, scale=2), nullable=False)
    price = Column(DECIMAL(precision=20, scale=8), nullable=False)
    profit_percentage = Column(DECIMAL(precision=10, scale=2), nullable=False)
    status = Column(String(20), nullable=False)
    price_change_percentage = Column(DECIMAL(precision=10, scale=2), nullable=False)
    quantity = Column(DECIMAL(precision=20, scale=8), server_default='0')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def profit(self):
        if self.status == CycleStatusType.COMPLETED:
            session = Session.object_session(self)

            buy_orders = self.orders.filter(
                Order.side == SideType.BUY,
                Order.status.in_([OrderStatusType.FILLED, OrderStatusType.PARTIALLY_FILLED])
            ).all()

            sell_orders = self.orders.filter(
                Order.side == SideType.SELL
            ).all()

            total_buy_amount = sum(order.quantity_filled * order.price for order in buy_orders)
            total_sell_amount = sum(order.quantity_filled * order.price for order in sell_orders)

            if sum(order.quantity_filled for order in sell_orders) != self.quantity:
                return "quantity mismatch"
            else:
                return round((total_sell_amount - total_buy_amount), 2)
        else:
            return 0

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
    price = Column(DECIMAL(precision=20, scale=8), nullable=False)
    amount = Column(DECIMAL(precision=20, scale=8), nullable=False)
    quantity = Column(DECIMAL(precision=20, scale=8), nullable=False)
    quantity_filled = Column(DECIMAL(precision=20, scale=8), server_default='0')
    status = Column(String(20), nullable=False)
    number = Column(Integer, nullable=False)
    exchange_order_id = Column(Integer, nullable=False)
    exchange_order_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
