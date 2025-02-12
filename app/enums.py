from enum import Enum

class ExchangeType(str, Enum):
    BINANCE = "BINANCE"

class SymbolType(str, Enum):
    BTC_USDT = "BTCUSDT"
    ETH_USDT = "ETHUSDT"
    PEPE_USDT = "PEPEUSDT"
    # Add other trading pairs as needed

class BotStatusType(str, Enum):
    RUNNING = "RUNNING"
    LAST_CYCLE = "LAST_CYCLE"
    STOPPED = "STOPPED"

class CycleStatusType(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class SideType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class TimeInForceType(str, Enum):
    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill

class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"

class OrderStatusType(str, Enum):
    NEW = "NEW"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED" 
