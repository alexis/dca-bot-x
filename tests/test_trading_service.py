import pytest
from decimal import Decimal
from app.models import TradingCycle, Order
from app.enums import OrderStatusType, SideType, TimeInForceType, OrderType, CycleStatusType
from uuid import uuid4
from unittest.mock import patch
from app.services.trading_service import TradingService
def test_launch(trading_service, test_bot):
    trading_service.launch()

def test_launch_inactive_bot(trading_service, test_bot, mock_binance_client):
    # Set bot as inactive
    test_bot.is_active = False
    
    trading_service.launch()
    
    # Should not create any cycles or orders for inactive bot
    mock_binance_client.ticker_price.assert_not_called()
    mock_binance_client.new_order.assert_not_called()
    assert trading_service.cycle is None

def test_launch_new_cycle(trading_service, test_bot, mock_binance_client, db_session):
    trading_service.launch()
    
    # Should create new cycle and orders
    mock_binance_client.ticker_price.assert_called()
    assert mock_binance_client.new_order.call_count == test_bot.num_orders
    
    # Verify cycle was created
    cycle = test_bot.trading_cycles.filter(
        TradingCycle.status == CycleStatusType.ACTIVE
    ).first()

    assert cycle is not None
    assert cycle.exchange == test_bot.exchange
    assert cycle.symbol == test_bot.symbol
    assert cycle.amount == test_bot.amount
    
    # Verify orders were created
    orders = db_session.query(Order).filter(Order.cycle_id == cycle.id).all()
    assert len(orders) == test_bot.num_orders
    assert all(order.status == OrderStatusType.NEW for order in orders)

def test_calculate_grid_prices(trading_service):
    market_price = Decimal('25000')
    prices = trading_service.calculate_grid_prices(market_price)
    
    assert len(prices) == trading_service.bot.num_orders
    assert prices[0] < market_price
    assert prices[-1] < prices[0]
    
    # Check price intervals are equal
    intervals = [prices[i] - prices[i+1] for i in range(len(prices)-1)]
    assert all(abs(intervals[0] - interval) < Decimal('0.0001') for interval in intervals)

def test_calculate_grid_quantities(trading_service):
    prices = [Decimal('25000'), Decimal('24750'), Decimal('24500'), Decimal('24250'), Decimal('24000')]
    quantities = trading_service.calculate_grid_quantities(prices)
    
    assert len(quantities) == trading_service.bot.num_orders
    assert all(q > Decimal('0') for q in quantities)
    assert quantities[1] > quantities[0]  # Check increasing quantities
    
    # Check total investment matches bot amount
    total_investment = sum(p * q for p, q in zip(prices, quantities))
    assert abs(total_investment - trading_service.bot.amount) < 1

def test_place_grid_orders(trading_service, mock_binance_client, test_cycle):
    trading_service.cycle = test_cycle
    trading_service.place_grid_orders()
    
    assert test_cycle.orders.count() == trading_service.bot.num_orders
    assert all(isinstance(order, Order) for order in test_cycle.orders)
    assert all(order.side == SideType.BUY for order in test_cycle.orders)
    assert mock_binance_client.new_order.call_count == trading_service.bot.num_orders

def test_place_take_profit_order(trading_service, mock_binance_client, test_cycle, db_session):
    trading_service.cycle = test_cycle

    # Create some filled buy orders
    filled_orders = [
        Order(
            exchange=trading_service.bot.exchange,
            symbol=trading_service.bot.symbol,
            side=SideType.BUY,
            price=Decimal('24000'),
            quantity=Decimal('0.02'),
            status=OrderStatusType.FILLED,
            cycle_id=test_cycle.id,
            exchange_order_id=123,
            time_in_force=TimeInForceType.GTC,
            type=OrderType.LIMIT,
            amount=Decimal('480'),  # price * quantity
            number=1
        ),
        Order(
            exchange=trading_service.bot.exchange,
            symbol=trading_service.bot.symbol,
            side=SideType.BUY,
            price=Decimal('23000'),
            quantity=Decimal('0.02'),
            status=OrderStatusType.FILLED,
            cycle_id=test_cycle.id,
            exchange_order_id=124,
            time_in_force=TimeInForceType.GTC,
            type=OrderType.LIMIT,
            amount=Decimal('460'),  # price * quantity
            number=2
        )
    ]
    db_session.add_all(filled_orders)
    db_session.commit()
    
    tp_order = trading_service.place_take_profit_order(filled_orders)
    
    assert isinstance(tp_order, Order)
    assert tp_order.side == SideType.SELL
    assert tp_order.type == OrderType.LIMIT
    assert tp_order.status == OrderStatusType.NEW
    assert mock_binance_client.new_order.call_count == 1

def test_cancel_cycle_orders(trading_service, mock_binance_client, test_cycle, db_session):
    trading_service.cycle = test_cycle
    # Add some active orders
    orders = [
        Order(
            exchange=test_cycle.exchange,
            symbol=test_cycle.symbol,
            side=SideType.BUY,
            status=OrderStatusType.NEW,
            cycle_id=test_cycle.id,
            exchange_order_id=123,
            time_in_force=TimeInForceType.GTC,
            type=OrderType.LIMIT,
            price=Decimal('24000'),
            quantity=Decimal('0.02'),
            amount=Decimal('480'),
            number=1
        ),
        Order(
            exchange=test_cycle.exchange,
            symbol=test_cycle.symbol,
            side=SideType.BUY,
            status=OrderStatusType.PARTIALLY_FILLED,
            cycle_id=test_cycle.id,
            exchange_order_id=124,
            time_in_force=TimeInForceType.GTC,
            type=OrderType.LIMIT,
            price=Decimal('24000'),
            quantity=Decimal('0.02'),
            amount=Decimal('480'),
            number=2
        )
    ]
    db_session.add_all(orders)
    db_session.commit()
    
    trading_service.cancel_cycle_orders()
    
    # Verify cancel_order was called
    assert mock_binance_client.cancel_order.call_count == 2
    # Verify orders were marked as canceled
    assert all(order.status == OrderStatusType.CANCELED for order in orders)

def test_update_take_profit_order(trading_service, mock_binance_client, test_cycle, db_session):
    trading_service.cycle = test_cycle
    # Create existing take profit order
    existing_tp_order = Order(
        cycle_id=test_cycle.id,
        exchange=trading_service.bot.exchange,
        symbol=trading_service.bot.symbol,
        side=SideType.SELL,
        price=Decimal('24240'),  # 1% above 24000
        quantity=Decimal('0.02'),
        status=OrderStatusType.NEW,
        exchange_order_id=123,
        type=OrderType.LIMIT,
        time_in_force=TimeInForceType.GTC,
        number=1,
        amount=Decimal('484.8')  # price * quantity
    )
    
    # Create new filled buy order
    new_filled_order = Order(
        cycle_id=test_cycle.id,
        exchange=trading_service.bot.exchange,
        symbol=trading_service.bot.symbol,
        side=SideType.BUY,
        price=Decimal('23000'),
        quantity=Decimal('0.03'),
        status=OrderStatusType.FILLED,
        exchange_order_id=124,
        type=OrderType.LIMIT,
        time_in_force=TimeInForceType.GTC,
        number=2,
        amount=Decimal('690')  # price * quantity
    )
    
    db_session.add_all([existing_tp_order, new_filled_order])
    db_session.commit()
    
    trading_service.update_take_profit_order()

    # Verify the old order was cancelled
    mock_binance_client.cancel_order.assert_called_once_with(
        symbol=trading_service.bot.symbol,
        orderId=123
    )
    
    # Verify new order was placed
    assert mock_binance_client.new_order.call_count == 1
    
    # Check that old TP order is canceled and new one is created
    updated_tp = test_cycle.orders.filter(
        Order.side == SideType.SELL,
        Order.status == OrderStatusType.NEW
    ).first()
    assert updated_tp is not None
    assert updated_tp.price == Decimal('23230')

def test_check_cycle_completion(trading_service, mock_binance_client, test_cycle, db_session):
    trading_service.cycle = test_cycle
    # Add a filled sell order (take profit)
    tp_order = Order(
        exchange=test_cycle.exchange,
        symbol=test_cycle.symbol,
        side=SideType.SELL,
        status=OrderStatusType.FILLED,
        cycle_id=test_cycle.id,
        exchange_order_id="124",
        time_in_force=TimeInForceType.GTC,
        type=OrderType.LIMIT,
        price=Decimal('24000'),
        quantity=Decimal('0.02'),
        amount=Decimal('480'),
        number=1
    )
    db_session.add(tp_order)
    db_session.commit()
    
    trading_service.check_cycle_completion()
    
    assert test_cycle.status == CycleStatusType.COMPLETED
    # Should try to start a new cycle since bot is active
    assert mock_binance_client.ticker_price.call_count == 2

def test_start_new_cycle(trading_service, mock_binance_client):
    # Setup mock
    mock_binance_client.ticker_price.return_value = {"price": "25000"}
    mock_binance_client.new_order.return_value = {
        "orderId": 123,
        "status": "NEW"
    }
    
    cycle = trading_service.start_new_cycle()
    
    assert cycle is not None
    assert cycle.exchange == trading_service.bot.exchange
    assert cycle.symbol == trading_service.bot.symbol
    assert cycle.amount == trading_service.bot.amount
    assert cycle.bot_id == trading_service.bot.id
    assert cycle.status == CycleStatusType.ACTIVE
    
    # Verify orders were placed
    assert mock_binance_client.new_order.call_count == trading_service.bot.num_orders

def test_start_new_cycle_with_active_cycle(trading_service, mock_binance_client, db_session):
    # Create an active cycle
    active_cycle = TradingCycle(
        exchange=trading_service.bot.exchange,
        symbol=trading_service.bot.symbol,
        amount=trading_service.bot.amount,
        grid_length=trading_service.bot.grid_length,
        first_order_offset=trading_service.bot.first_order_offset,
        num_orders=trading_service.bot.num_orders,
        partial_num_orders=0,
        next_order_volume=trading_service.bot.next_order_volume,
        price=Decimal('25000'),
        profit_percentage=trading_service.bot.profit_percentage,
        price_change_percentage=trading_service.bot.price_change_percentage,
        status=CycleStatusType.ACTIVE,
        bot_id=trading_service.bot.id
    )
    db_session.add(active_cycle)
    db_session.commit()
    
    # Try to start a new cycle
    with pytest.raises(ValueError, match=f"Bot {trading_service.bot.name} already has an active cycle"):
        trading_service.start_new_cycle()

def test_create_binance_order_success(trading_service, mock_binance_client, test_cycle):
    trading_service.cycle = test_cycle
    # Setup mock response
    mock_binance_order = {
        "orderId": 12345,
        "status": "NEW",
        "executedQty": "0",
        "cummulativeQuoteQty": "0"
    }
    mock_binance_client.new_order.return_value = mock_binance_order
    
    # Test creating a buy order
    order = trading_service.create_binance_order(
        side="BUY",
        price=Decimal('24000.00'),
        quantity=Decimal('0.02000'),
        number=1
    )
    
    # Verify Binance API was called correctly
    mock_binance_client.new_order.assert_called_once_with(
        symbol=trading_service.bot.symbol,
        side="BUY",
        type="LIMIT",
        timeInForce="GTC",
        quantity="0.02000",
        price="24000.00"
    )
    
    # Verify Order object was created correctly
    assert order.exchange == trading_service.bot.exchange
    assert order.symbol == trading_service.bot.symbol
    assert order.side == SideType.BUY
    assert order.type == OrderType.LIMIT
    assert order.time_in_force == TimeInForceType.GTC
    assert order.price == float(24000)
    assert order.quantity == float(0.02)
    assert order.amount == float(24000 * 0.02)
    assert order.status == OrderStatusType.NEW
    assert order.number == 1
    assert order.exchange_order_id == 12345
    assert order.exchange_order_data == mock_binance_order
    assert order.cycle_id == test_cycle.id

def test_create_binance_order_error(trading_service, mock_binance_client, test_cycle):
    trading_service.cycle = test_cycle
    # Setup mock to raise an exception
    mock_binance_client.new_order.side_effect = Exception("API Error")
    
    # Test that the error is propagated
    with pytest.raises(Exception) as exc_info:
        trading_service.create_binance_order(
            side="BUY",
            price=Decimal('24000'),
            quantity=Decimal('0.02'),
            number=1
        )
    
    assert "Failed to create order" in str(exc_info.value)

@patch.object(TradingService, 'cancel_cycle_orders')
def test_check_grid_update(mock_cancel_cycle_orders, trading_service, mock_binance_client, test_cycle):
    trading_service.cycle = test_cycle
    current_price = 25200

    trading_service.check_grid_update(current_price)

    # Verify grid was updated
    assert test_cycle.price == current_price
    assert mock_binance_client.new_order.call_count == trading_service.bot.num_orders
    
    # Verify cancel_cycle_orders was called for existing orders
    mock_cancel_cycle_orders.assert_called()

@patch.object(TradingService, 'cancel_cycle_orders')
def test_check_grid_update_without_cycle(mock_cancel_cycle_orders, trading_service, mock_binance_client):
    trading_service.cycle = None
    current_price = 25200

    trading_service.check_grid_update(current_price)

    # Verify no actions were taken
    mock_cancel_cycle_orders.assert_not_called()
    mock_binance_client.new_order.assert_not_called()

def test_check_grid_update_small_change(trading_service, mock_binance_client, test_cycle):
    trading_service.cycle = test_cycle
    current_price = 24010  # Less than 0.5% change from 24000

    trading_service.check_grid_update(current_price)

    # Verify no grid update was performed
    mock_binance_client.cancel_order.assert_not_called()
    mock_binance_client.new_order.assert_not_called()
    assert test_cycle.price == 24010

def test_query_open_orders(trading_service, mock_binance_client, test_cycle, db_session):
    trading_service.cycle = test_cycle
    
    # Create test orders with different statuses
    orders = [
        Order(
            exchange=test_cycle.exchange,
            symbol=test_cycle.symbol,
            side=SideType.BUY,
            status=OrderStatusType.NEW,
            cycle_id=test_cycle.id,
            exchange_order_id=123,
            time_in_force=TimeInForceType.GTC,
            type=OrderType.LIMIT,
            price=Decimal('24000'),
            quantity=Decimal('0.02'),
            amount=Decimal('480'),
            number=1
        ),
        Order(
            exchange=test_cycle.exchange,
            symbol=test_cycle.symbol,
            side=SideType.BUY,
            status=OrderStatusType.PARTIALLY_FILLED,
            cycle_id=test_cycle.id,
            exchange_order_id=124,
            time_in_force=TimeInForceType.GTC,
            type=OrderType.LIMIT,
            price=Decimal('24000'),
            quantity=Decimal('0.02'),
            amount=Decimal('480'),
            number=2
        )
    ]
    db_session.add_all(orders)
    db_session.commit()

    # Mock Binance API responses
    mock_binance_client.get_order.side_effect = [
        {"orderId": 123, "status": "FILLED"},
        {"orderId": 124, "status": "PARTIALLY_FILLED"}
    ]

    # Call the method
    queried_orders = trading_service.query_open_orders()

    # Verify Binance API was called for each order
    assert mock_binance_client.get_order.call_count == 2
    mock_binance_client.get_order.assert_any_call(
        symbol=test_cycle.symbol,
        orderId=123
    )
    mock_binance_client.get_order.assert_any_call(
        symbol=test_cycle.symbol,
        orderId=124
    )

    # Verify order statuses were updated
    updated_orders = test_cycle.orders.order_by(Order.exchange_order_id).all()

    assert updated_orders[0].status == "FILLED"
    assert updated_orders[1].status == "PARTIALLY_FILLED"
    assert len(queried_orders) == 2

def test_cycle_profit_calculation(test_cycle, db_session):
    # Create filled buy orders
    buy_orders = [
        Order(
            exchange=test_cycle.exchange,
            symbol=test_cycle.symbol,
            side=SideType.BUY,
            status=OrderStatusType.FILLED,
            cycle_id=test_cycle.id,
            exchange_order_id=123,
            time_in_force=TimeInForceType.GTC,
            type=OrderType.LIMIT,
            price=Decimal('24000'),
            quantity=Decimal('0.02'),
            amount=Decimal('480'),  # price * quantity
            number=1
        ),
        Order(
            exchange=test_cycle.exchange,
            symbol=test_cycle.symbol,
            side=SideType.BUY,
            status=OrderStatusType.FILLED,
            cycle_id=test_cycle.id,
            exchange_order_id=124,
            time_in_force=TimeInForceType.GTC,
            type=OrderType.LIMIT,
            price=Decimal('23000'),
            quantity=Decimal('0.02'),
            amount=Decimal('460'),  # price * quantity
            number=2
        )
    ]
    
    # Create filled sell (take profit) order
    sell_order = Order(
        exchange=test_cycle.exchange,
        symbol=test_cycle.symbol,
        side=SideType.SELL,
        status=OrderStatusType.FILLED,
        cycle_id=test_cycle.id,
        exchange_order_id=125,
        time_in_force=TimeInForceType.GTC,
        type=OrderType.LIMIT,
        price=Decimal('24500'),  # Higher than buy prices
        quantity=Decimal('0.04'),  # Total quantity from buy orders
        amount=Decimal('980'),  # price * quantity
        number=3
    )
    
    db_session.add_all(buy_orders + [sell_order])
    test_cycle.status = CycleStatusType.COMPLETED
    db_session.commit()
    
    # Expected profit: sell amount - total buy amount = 980 - (480 + 460) = 40
    assert test_cycle.profit() == 40.00

def test_cycle_profit_incomplete_cycle(test_cycle, db_session):
    # Create some orders but keep cycle status as ACTIVE
    buy_order = Order(
        exchange=test_cycle.exchange,
        symbol=test_cycle.symbol,
        side=SideType.BUY,
        status=OrderStatusType.FILLED,
        cycle_id=test_cycle.id,
        exchange_order_id=123,
        time_in_force=TimeInForceType.GTC,
        type=OrderType.LIMIT,
        price=Decimal('24000'),
        quantity=Decimal('0.02'),
        amount=Decimal('480'),
        number=1
    )
    
    db_session.add(buy_order)
    test_cycle.status = CycleStatusType.ACTIVE  # Cycle not completed
    db_session.commit()
    
    # Should return 0 as cycle is not completed
    assert test_cycle.profit() == 0

def test_cycle_profit_no_orders(test_cycle, db_session):
    # Set cycle as completed but with no orders
    test_cycle.status = CycleStatusType.COMPLETED
    db_session.commit()
    
    # Should return 0 as there are no orders
    assert test_cycle.profit() == 0
