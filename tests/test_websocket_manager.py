import pytest
from unittest.mock import AsyncMock, Mock, patch
from app.services.websocket_manager import WebsocketManager
from app.models import Order
from app.enums import OrderStatusType, SideType
from decimal import Decimal
import os
import json
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
    mock_ws_client.ticker.assert_called()

@pytest.mark.asyncio
async def test_message_handler_execution_report_buy_order_filled(websocket_manager, mock_trading_service, test_cycle, test_order, db_session):
    # Set up mock trading service with cycle
    mock_trading_service.cycle = test_cycle
    
    # Simulate order filled message
    msg = {
        "e": "executionReport",
        "i": test_order.exchange_order_id,  # orderId
        "X": "FILLED",  # status
        "s": "BTCUSDT",  # symbol
        "S": "BUY",  # side
        "o": "LIMIT",  # orderType
        "q": "0.02",  # quantity
        "p": "24000",  # price
        "x": "TRADE",  # execution type
        "l": "0.02",  # executed quantity
        "z": "0.02"  # executed quantity
    }

    websocket_manager._handle_execution_report(msg)

    # Verify order was updated - refresh from db to get latest status
    db_session.refresh(test_order)
    assert test_order.status == OrderStatusType.FILLED
    assert test_order.exchange_order_data == msg
    
    # Verify take profit order was updated
    mock_trading_service.update_take_profit_order.assert_called_once()

@pytest.mark.asyncio
async def test_message_handler_execution_report_sell_order_filled(websocket_manager, mock_trading_service, test_cycle, test_order, db_session):
    # Set up mock trading service with cycle
    mock_trading_service.cycle = test_cycle
    
    # Update test_order to be a sell order
    test_order.side = SideType.SELL
    test_order.price = Decimal('100000')
    test_order.amount = Decimal('500')
    test_order.quantity = Decimal('0.02')
    db_session.commit()

    # Simulate order filled message
    msg = {
        "e": "executionReport",
        "i": test_order.exchange_order_id,  # orderId
        "X": "FILLED",  # status
        "s": "BTCUSDT",  # symbol
        "S": "SELL",  # side
        "o": "LIMIT",  # orderType
        "q": "0.02",  # quantity
        "p": "100000",  # price
        "x": "TRADE",  # execution type
        "l": "0.02",  # executed quantity
        "z": "0.02"  # executed quantity
    }

    websocket_manager._handle_execution_report(msg)

    # Verify order was updated - refresh from db to get latest status
    db_session.refresh(test_order)
    assert test_order.status == OrderStatusType.FILLED
    assert test_order.exchange_order_data == msg
    
    # Verify cycle completion was checked
    mock_trading_service.check_cycle_completion.assert_called_once()

@pytest.mark.asyncio
async def test_handle_price_update(websocket_manager, mock_trading_service):
    # Simulate price update message
    msg = {
        "s": "BTCUSDT",
        "c": "25200"  # Current price
    }

    websocket_manager._handle_price_update(msg)
    mock_trading_service.check_grid_update.assert_called_once()

@pytest.mark.asyncio
async def test_message_handler_price_update(websocket_manager, mock_trading_service):
    # Simulate price update message
    msg = {
        "e": "24hrTicker",
        "s": "BTCUSDT",
        "c": "25200"  # Current price
    }

    websocket_manager.message_handler(None, json.dumps(msg))

    # Verify that the price update handler was called
    mock_trading_service.check_grid_update.assert_called_once_with(25200)
