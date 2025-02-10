import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import Mock
from decimal import Decimal
from uuid import uuid4
import os

from app.database import get_db
from app.services.trading_service import TradingService
from app.models import Base,Bot, TradingCycle, Order
from app.enums import ExchangeType, SymbolType, BotStatusType, CycleStatusType, SideType, OrderType, TimeInForceType, OrderStatusType

# Test database URL
DATABASE_URL = os.getenv('TEST_DATABASE_URL', "postgresql://postgres:postgres@test-db:5432/test_trading_db")

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session")
def db_engine():
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def mock_binance_client():
    client = Mock()
    # Mock ticker_price method
    client.ticker_price.return_value = {"price": "100000"}
    
    # Mock new_order method
    client.new_order.return_value = {
        "orderId": 123,
        "status": "NEW",
        "executedQty": "0",
        "cummulativeQuoteQty": "0"
    }
    
    # Mock cancel_order method
    client.cancel_order.return_value = {
        "orderId": 123,
        "status": "CANCELED",
        "executedQty": "0.01"
    }
    
    # Mock account method
    client.account.return_value = {
        "balances": [
            {
                "asset": "BTC",
                "free": "0.1",
                "locked": "0.0"
            }
        ]
    }
    
    # Mock new_listen_key method
    client.new_listen_key.return_value = {
        "listenKey": "test_listen_key"
    }
    
    return client

@pytest.fixture
def test_bot(db_session):
    bot = Bot(
        id=uuid4(),
        name="Test Bot",
        exchange=ExchangeType.BINANCE,
        symbol=SymbolType.BTC_USDT,
        amount=Decimal('1000'),
        grid_length=Decimal('10'),
        first_order_offset=Decimal('1'),
        num_orders=5,
        next_order_volume=Decimal('5'),
        profit_percentage=Decimal('1'),
        price_change_percentage=Decimal('1'),
        status=BotStatusType.ACTIVE,
        is_active=True,
        upper_price_limit=Decimal('30000'),
        api_key="test_api_key",
        api_secret="test_api_secret"
    )
    db_session.add(bot)
    db_session.flush()

    return bot

@pytest.fixture
def test_cycle(db_session, test_bot):
    cycle = TradingCycle(
        id=uuid4(),
        bot_id=test_bot.id,
        exchange=test_bot.exchange,
        symbol=test_bot.symbol,
        amount=test_bot.amount,
        status=CycleStatusType.ACTIVE,
        grid_length=test_bot.grid_length,
        first_order_offset=test_bot.first_order_offset,
        num_orders=test_bot.num_orders,
        next_order_volume=test_bot.next_order_volume,
        profit_percentage=test_bot.profit_percentage,
        price_change_percentage=test_bot.price_change_percentage,
        price=Decimal('100000')
    )
    db_session.add(cycle)
    db_session.flush()

    return cycle

@pytest.fixture
def test_order(db_session, test_cycle):
    order = Order(
        exchange=test_cycle.exchange,
        symbol=test_cycle.symbol,
        side=SideType.BUY,
        type=OrderType.LIMIT,
        time_in_force=TimeInForceType.GTC,
        price=Decimal('100000'),
        quantity=Decimal('0.02'),
        quantity_filled=Decimal('0'),
        amount=Decimal('480'),
        status=OrderStatusType.NEW,
        number=1,
        exchange_order_id="123",
        exchange_order_data={},
        cycle_id=test_cycle.id
    )
    db_session.add(order)
    db_session.commit()
    return order

@pytest.fixture
def trading_service(mock_binance_client, db_session, test_bot):
    service = TradingService(db=db_session, bot=test_bot)
    service.client = mock_binance_client  # Replace the real client with mock
    return service 
