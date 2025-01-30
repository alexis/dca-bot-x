import pytest
from app.models import Bot, TradingCycle
from app.enums import ExchangeType, SymbolType, BotStatusType
from uuid import uuid4

def test_calculate_grid_prices(trading_service):
    bot = Bot(
        grid_length=10,
        first_order_offset=1,
        num_orders=5,
        amount=1000,
        next_order_volume=5
    )
    market_price = 25000
    
    prices = trading_service.calculate_grid_prices(market_price, bot)
    
    assert len(prices) == 5
    assert prices[0] < market_price
    assert prices[-1] < prices[0]
    
    # Check price intervals are equal
    intervals = [prices[i] - prices[i+1] for i in range(len(prices)-1)]
    assert all(abs(intervals[0] - interval) < 0.0001 for interval in intervals)

def test_calculate_grid_quantities(trading_service):
    bot = Bot(
        amount=1000,
        next_order_volume=5,
        num_orders=5
    )
    prices = [25000, 24750, 24500, 24250,24000]
    
    quantities = trading_service.calculate_grid_quantities(prices, bot)
    
    assert len(quantities) == 5
    assert all(q > 0 for q in quantities)
    assert quantities[1] > quantities[0]  # Check increasing quantities
    
    # Check total investment matches bot amount
    total_investment = sum(p * q for p, q in zip(prices, quantities))
    assert abs(total_investment - bot.amount) < 0.01

@pytest.mark.asyncio
async def test_start_new_cycle(trading_service, mock_binance_client):
    # Setup mock
    mock_binance_client.ticker_price.return_value = {"price": "25000"}
    mock_binance_client.new_order.return_value = {
        "orderId": "123",
        "status": "NEW"
    }
    
    bot = Bot(
        id=uuid4(),
        name="Test Bot",
        exchange=ExchangeType.BINANCE,
        symbol=SymbolType.BTC_USDT,
        amount=1000,
        grid_length=10,
        first_order_offset=1,
        num_orders=5,
        next_order_volume=5,
        profit_percentage=1,
        price_change_percentage=1,
        status=BotStatusType.ACTIVE,
        is_active=True
    )
    
    cycle = trading_service.start_new_cycle(bot)
    
    assert cycle is not None
    assert cycle.exchange == bot.exchange
    assert cycle.symbol == bot.symbol
    assert cycle.amount == bot.amount
    
    # Verify orders were placed
    assert mock_binance_client.new_order.call_count == bot.num_orders 
