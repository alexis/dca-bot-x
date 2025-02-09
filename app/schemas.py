from pydantic import BaseModel, UUID4, Field
from datetime import datetime
from typing import Optional
from .enums import *

class BotBase(BaseModel):
    name: str = Field(..., max_length=100)
    exchange: ExchangeType
    symbol: SymbolType
    amount: float = Field(..., gt=0)
    grid_length: float = Field(..., gt=0)
    first_order_offset: float
    num_orders: int = Field(..., gt=0)
    next_order_volume: float
    profit_percentage: float
    price_change_percentage: float
    upper_price_limit: float
    status: BotStatusType
    is_active: bool = True
    user_id: UUID4
    exchange_key_id: UUID4

class BotCreate(BotBase):
    pass

class BotResponse(BotBase):
    id: UUID4
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TradingCycleBase(BaseModel):
    exchange: ExchangeType
    symbol: SymbolType
    amount: float = Field(..., gt=0)
    grid_length: float = Field(..., gt=0)
    first_order_offset: float
    num_orders: int = Field(..., gt=0)
    next_order_volume: float
    price: float = Field(..., gt=0)
    profit_percentage: float
    price_change_percentage: float
    status: CycleStatusType
    bot_id: Optional[UUID4]

class TradingCycleCreate(TradingCycleBase):
    pass

class TradingCycleResponse(TradingCycleBase):
    id: UUID4
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class OrderBase(BaseModel):
    exchange: ExchangeType
    symbol: SymbolType
    side: SideType
    time_in_force: TimeInForceType
    type: OrderType
    price: float = Field(..., gt=0)
    amount: float = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    status: OrderStatusType
    number: int
    exchange_order_id: str
    exchange_order_data: Optional[dict] = None
    cycle_id: UUID4

class OrderCreate(OrderBase):
    pass

class OrderResponse(OrderBase):
    id: UUID4
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
