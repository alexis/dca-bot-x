import pytest
from decimal import Decimal
from app.models import Bot, TradingCycle, Order
from app.enums import ExchangeType, SymbolType, BotStatusType, OrderStatusType, SideType, TimeInForceType, OrderType, CycleStatusType
from uuid import uuid4

def test_calculate_grid_prices(trading_service, test_bot):
    market_price = Decimal('25000')
    prices = trading_service.calculate_grid_prices(market_price, test_bot)
    
    assert len(prices) == test_bot.num_orders
    assert prices[0] < market_price
    assert prices[-1] < prices[0]
    
    # Check price intervals are equal
    intervals = [prices[i] - prices[i+1] for i in range(len(prices)-1)]
    assert all(abs(intervals[0] - interval) < Decimal('0.0001') for interval in intervals)

def test_calculate_grid_quantities(trading_service, test_bot):
    prices = [Decimal('25000'), Decimal('24750'), Decimal('24500'), Decimal('24250'), Decimal('24000')]
    quantities = trading_service.calculate_grid_quantities(prices, test_bot)
    
    assert len(quantities) == test_bot.num_orders
    assert all(q > Decimal('0') for q in quantities)
    assert quantities[1] > quantities[0]  # Check increasing quantities
    
    # Check total investment matches bot amount
    total_investment = sum(p * q for p, q in zip(prices, quantities))
    assert abs(total_investment - test_bot.amount) < Decimal('0.1')

def test_place_grid_orders(trading_service, mock_binance_client, test_bot, test_cycle):
    orders = trading_service.place_grid_orders(test_bot, test_cycle)
    
    assert len(orders) == test_bot.num_orders
    assert all(isinstance(order, Order) for order in orders)
    assert all(order.side == SideType.BUY for order in orders)
    assert mock_binance_client.new_order.call_count == test_bot.num_orders

def test_place_take_profit_order(trading_service, mock_binance_client, test_bot, test_cycle, db_session):
    # Create some filled buy orders
    filled_orders = [
        Order(
            exchange=test_bot.exchange,
            symbol=test_bot.symbol,
            side=SideType.BUY,
            price=Decimal('24000'),
            quantity=Decimal('0.02'),
            status=OrderStatusType.FILLED,
            cycle_id=test_cycle.id,
            exchange_order_id="123",
            time_in_force=TimeInForceType.GTC,
            type=OrderType.LIMIT,
            amount=Decimal('480'),  # price * quantity
            number=1
        ),
        Order(
            exchange=test_bot.exchange,
            symbol=test_bot.symbol,
            side=SideType.BUY,
            price=Decimal('23000'),
            quantity=Decimal('0.02'),
            status=OrderStatusType.FILLED,
            cycle_id=test_cycle.id,
            exchange_order_id="124",
            time_in_force=TimeInForceType.GTC,
            type=OrderType.LIMIT,
            amount=Decimal('460'),  # price * quantity
            number=2
        )
    ]
    db_session.add_all(filled_orders)
    db_session.commit()
    
    tp_order = trading_service.place_take_profit_order(test_bot, test_cycle, filled_orders)
    
    assert isinstance(tp_order, Order)
    assert tp_order.side == SideType.SELL
    assert tp_order.type == OrderType.LIMIT
    assert tp_order.status == OrderStatusType.NEW
    assert mock_binance_client.new_order.call_count == 1

def test_cancel_cycle_orders(trading_service, mock_binance_client, test_cycle, db_session):
    # Add some active orders
    orders = [
        Order(
            exchange=test_cycle.exchange,
            symbol=test_cycle.symbol,
            side=SideType.BUY,
            status=OrderStatusType.NEW,
            cycle_id=test_cycle.id,
            exchange_order_id="123",
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
            exchange_order_id="124",
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
    
    trading_service.cancel_cycle_orders(test_cycle)
    
    assert mock_binance_client.cancel_order.call_count == 2
    assert all(order.status == OrderStatusType.CANCELED for order in orders)

def test_update_take_profit_order(trading_service, mock_binance_client, test_bot, test_cycle, db_session):
    # Create existing take profit order
    existing_tp_order = Order(
        cycle_id=test_cycle.id,
        exchange=test_bot.exchange,
        symbol=test_bot.symbol,
        side=SideType.SELL,
        price=Decimal('24240'),  # 1% above 24000
        quantity=Decimal('0.02'),
        status=OrderStatusType.NEW,
        exchange_order_id="123",
        type=OrderType.LIMIT,
        time_in_force=TimeInForceType.GTC,
        number=1,
        amount=Decimal('484.8')  # price * quantity
    )
    
    # Create new filled buy order
    new_filled_order = Order(
        cycle_id=test_cycle.id,
        exchange=test_bot.exchange,
        symbol=test_bot.symbol,
        side=SideType.BUY,
        price=Decimal('23000'),
        quantity=Decimal('0.03'),
        status=OrderStatusType.FILLED,
        exchange_order_id="124",
        type=OrderType.LIMIT,
        time_in_force=TimeInForceType.GTC,
        number=2,
        amount=Decimal('690')  # price * quantity
    )
    
    db_session.add_all([existing_tp_order, new_filled_order])
    db_session.commit()
    
    trading_service.update_take_profit_order(test_cycle)

    # Verify the old order was cancelled
    mock_binance_client.cancel_order.assert_called_once_with(
        symbol=test_bot.symbol,
        orderId="123"
    )
    
    # Verify new order was placed
    assert mock_binance_client.new_order.call_count == 1
    
    # Check that old TP order is canceled and new one is created
    updated_tp = db_session.query(Order).filter(
        Order.cycle_id == test_cycle.id,
        Order.side == SideType.SELL,
        Order.status == OrderStatusType.NEW
    ).first()
    assert updated_tp is not None
    assert updated_tp.price == Decimal('23230')

def test_check_cycle_completion(trading_service, mock_binance_client, test_bot, test_cycle, db_session):
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
    
    trading_service.check_cycle_completion(test_cycle)
    
    assert test_cycle.status == CycleStatusType.COMPLETED
    # Should try to start a new cycle since bot is active
    assert mock_binance_client.ticker_price.call_count == 2

def test_start_new_cycle(trading_service, mock_binance_client, test_bot):
    # Setup mock
    mock_binance_client.ticker_price.return_value = {"price": "25000"}
    mock_binance_client.new_order.return_value = {
        "orderId": "123",
        "status": "NEW"
    }
    
    cycle = trading_service.start_new_cycle(test_bot)
    
    assert cycle is not None
    assert cycle.exchange == test_bot.exchange
    assert cycle.symbol == test_bot.symbol
    assert cycle.amount == test_bot.amount
    
    # Verify orders were placed
    assert mock_binance_client.new_order.call_count == test_bot.num_orders 
