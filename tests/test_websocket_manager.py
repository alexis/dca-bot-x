import pytest
from unittest.mock import AsyncMock, Mock, patch
from app.services.websocket_manager import WebsocketManager
from app.models import Bot, TradingCycle, Order
from app.enums import OrderStatusType, SideType, TimeInForceType, OrderType, CycleStatusType, ExchangeType, SymbolType
from decimal import Decimal
import os

@pytest.fixture
def mock_ws_client():
    with patch('app.services.websocket_manager.SpotWebsocketStreamClient') as mock:
        client_instance = Mock()
        client_instance.ticker = Mock()
        mock.return_value = client_instance
        yield client_instance

@pytest.fixture
def mock_trading_service():
    service = Mock()
    service.update_take_profit_order = Mock()
    service.check_cycle_completion = Mock()
    service.cancel_cycle_orders = Mock()
    service.place_grid_orders = Mock(return_value=[])
    return service

@pytest.fixture
def websocket_manager(mock_trading_service, mock_ws_client, test_bot, db_session):
    manager = WebsocketManager(
        bot=test_bot,
        trading_service=mock_trading_service,
        db=db_session,
        listen_key="test_listen_key"
    )
    return manager

@pytest.mark.asyncio
async def test_start_websocket(websocket_manager, mock_ws_client):
    await websocket_manager.start()
    
    # Verify user data subscription was made with listen key
    mock_ws_client.user_data.assert_called_once_with(listen_key="test_listen_key")

@pytest.mark.asyncio
async def test_process_buy_order_filled(websocket_manager, mock_trading_service, test_bot, db_session):
    # Create a test cycle
    cycle = TradingCycle(
        exchange=test_bot.exchange,
        symbol=test_bot.symbol,
        amount=test_bot.amount,
        grid_length=test_bot.grid_length,
        first_order_offset=test_bot.first_order_offset,
        num_orders=test_bot.num_orders,
        partial_num_orders=0,
        next_order_volume=test_bot.next_order_volume,
        price=Decimal('25000'),
        profit_percentage=test_bot.profit_percentage,
        price_change_percentage=test_bot.price_change_percentage,
        status=CycleStatusType.ACTIVE,
        bot_id=test_bot.id
    )
    db_session.add(cycle)
    db_session.commit()
    
    # Create a test order
    order = Order(
        exchange=test_bot.exchange,
        symbol=test_bot.symbol,
        side=SideType.BUY,
        type=OrderType.LIMIT,
        time_in_force=TimeInForceType.GTC,
        price=Decimal('24000'),
        quantity=Decimal('0.02'),
        amount=Decimal('480'),
        status=OrderStatusType.NEW,
        number=1,
        exchange_order_id="123",
        cycle_id=cycle.id
    )
    db_session.add(order)
    db_session.commit()

    # Simulate order filled message
    msg = {
        "e": "executionReport",
        "i": 123,  # orderId
        "X": "FILLED",  # status
        "s": "BTCUSDT",  # symbol
        "S": "BUY",  # side
        "o": "LIMIT",  # orderType
        "q": "0.02",  # quantity
        "p": "24000",  # price
        "x": "TRADE"  # execution type
    }

    websocket_manager._process_order_update(msg)

    # Verify order was updated
    updated_order = db_session.query(Order).filter_by(exchange_order_id="123").first()
    assert updated_order.status == OrderStatusType.FILLED
    
    # Verify take profit order was updated
    mock_trading_service.update_take_profit_order.assert_called_once()

@pytest.mark.asyncio
async def test_process_sell_order_filled(websocket_manager, mock_trading_service, test_bot, db_session):
    # Create a test cycle
    cycle = TradingCycle(
        exchange=test_bot.exchange,
        symbol=test_bot.symbol,
        amount=test_bot.amount,
        grid_length=test_bot.grid_length,
        first_order_offset=test_bot.first_order_offset,
        num_orders=test_bot.num_orders,
        partial_num_orders=0,
        next_order_volume=test_bot.next_order_volume,
        price=Decimal('25000'),
        profit_percentage=test_bot.profit_percentage,
        price_change_percentage=test_bot.price_change_percentage,
        status=CycleStatusType.ACTIVE,
        bot_id=test_bot.id
    )
    db_session.add(cycle)
    db_session.commit()
    
    # Create a test order
    order = Order(
        exchange=test_bot.exchange,
        symbol=test_bot.symbol,
        side=SideType.SELL,
        type=OrderType.LIMIT,
        time_in_force=TimeInForceType.GTC,
        price=Decimal('25000'),
        quantity=Decimal('0.02'),
        amount=Decimal('500'),
        status=OrderStatusType.NEW,
        number=1,
        exchange_order_id="123",
        cycle_id=cycle.id
    )
    db_session.add(order)
    db_session.commit()

    # Simulate order filled message
    msg = {
        "e": "executionReport",
        "i": 123,  # orderId
        "X": "FILLED",  # status
        "s": "BTCUSDT",  # symbol
        "S": "SELL",  # side
        "o": "LIMIT",  # orderType
        "q": "0.02",  # quantity
        "p": "25000",  # price
        "x": "TRADE"  # execution type
    }

    websocket_manager._process_order_update(msg)

    # Verify order was updated
    updated_order = db_session.query(Order).filter_by(exchange_order_id="123").first()
    assert updated_order.status == OrderStatusType.FILLED
    
    # Verify cycle completion was checked
    mock_trading_service.check_cycle_completion.assert_called_once()

@pytest.mark.asyncio
async def test_handle_price_update(websocket_manager, mock_trading_service):
    # Simulate price update message
    msg = {
        "s": "BTCUSDT",
        "c": "25200"  # Current price
    }

    websocket_manager.handle_price_update(msg)
    mock_trading_service.check_grid_update.assert_called_once()
