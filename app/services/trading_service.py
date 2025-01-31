from decimal import Decimal, ROUND_DOWN
from typing import List, Dict
from binance.spot import Spot
from ..models import Bot, TradingCycle, Order
from ..enums import OrderType, SideType, TimeInForceType, OrderStatusType, CycleStatusType
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

class TradingService:
    def __init__(self, client: Spot, db: Session):
        self.client = client
        self.db = db

    def calculate_grid_prices(self, market_price: Decimal, bot: Bot) -> List[Decimal]:
        """Calculate grid order prices"""
        # Convert bot parameters to Decimal to ensure consistent arithmetic
        first_order_offset = Decimal(str(bot.first_order_offset))
        grid_length = Decimal(str(bot.grid_length))
        
        first_order_price = market_price * (Decimal('1') - first_order_offset / Decimal('100'))
        total_drop = first_order_price * (grid_length / Decimal('100'))
        price_step = total_drop / (Decimal(str(bot.num_orders - 1))) if bot.num_orders > 1 else Decimal('0')
        
        prices = []
        for i in range(bot.num_orders):
            price = round(first_order_price - (price_step * Decimal(str(i))), 2)
            prices.append(price)
        
        return prices

    def calculate_grid_quantities(self, prices: List[Decimal], bot: Bot) -> List[Decimal]:
        """Calculate quantities for each grid level"""
        # Convert bot parameters to Decimal
        amount = Decimal(str(bot.amount))
        next_order_volume = Decimal(str(bot.next_order_volume))
        
        base_quantity = amount / sum(prices)  # Initial equal distribution
        quantities = []
        
        current_quantity = base_quantity
        for _ in range(bot.num_orders):
            quantities.append(current_quantity)
            current_quantity *= (Decimal('1') + next_order_volume / Decimal('100'))
            
        # Normalize quantities to match total amount
        total_value = sum(p * q for p, q in zip(prices, quantities))
        scale_factor = amount / total_value
        quantities = [(q * scale_factor).quantize(Decimal('0.000001'), rounding=ROUND_DOWN) for q in quantities]
        
        return quantities

    def place_grid_orders(self, bot: Bot, cycle: TradingCycle) -> List[Order]:
        """Place initial grid orders"""
        market_price = Decimal(self.client.ticker_price(symbol=bot.symbol)["price"])
        prices = self.calculate_grid_prices(market_price, bot)
        quantities = self.calculate_grid_quantities(prices, bot)
        
        orders = []
        for i, (price, quantity) in enumerate(zip(prices, quantities)):
            try:
                binance_order = self.client.new_order(
                    symbol=bot.symbol,
                    side="BUY",
                    type="LIMIT",
                    timeInForce="GTC",
                    quantity=str(quantity),
                    price=str(price)
                )
                
                order = Order(
                    exchange=bot.exchange,
                    symbol=bot.symbol,
                    side=SideType.BUY,
                    time_in_force=TimeInForceType.GTC,
                    type=OrderType.LIMIT,
                    price=float(price),
                    quantity=float(quantity),
                    amount=float(price * quantity),
                    status=OrderStatusType.NEW,
                    number=i + 1,
                    exchange_order_id=binance_order["orderId"],
                    exchange_order_data=binance_order,
                    cycle_id=cycle.id
                )
                orders.append(order)
                
            except Exception as e:
                # Handle error, cancel placed orders if needed
                raise Exception(f"Failed to place grid order: {e}")
                
        return orders

    def place_take_profit_order(self, bot: Bot, cycle: TradingCycle, filled_orders: List[Order]) -> Order:
        """Place or update take profit order"""
        # Calculate average entry price and total quantity
        total_quantity = sum(order.quantity for order in filled_orders)
        total_cost = sum(order.price * order.quantity for order in filled_orders)
        avg_price = total_cost / total_quantity
        
        # Calculate take profit price
        take_profit_price = avg_price * (1 + bot.profit_percentage / 100)
        
        try:
            binance_order = self.client.new_order(
                symbol=bot.symbol,
                side="SELL",
                type="LIMIT",
                timeInForce="GTC",
                quantity=str(total_quantity),
                price=str(take_profit_price)
            )
            
            order = Order(
                exchange=bot.exchange,
                symbol=bot.symbol,
                side=SideType.SELL,
                time_in_force=TimeInForceType.GTC,
                type=OrderType.LIMIT,
                price=float(take_profit_price),
                quantity=float(total_quantity),
                amount=float(take_profit_price * total_quantity),
                status=OrderStatusType.NEW,
                number=len(filled_orders) + 1,
                exchange_order_id=binance_order["orderId"],
                exchange_order_data=binance_order,
                cycle_id=cycle.id
            )
            return order
            
        except Exception as e:
            raise Exception(f"Failed to place take profit order: {e}")

    def start_new_cycle(self, bot: Bot) -> TradingCycle:
        """Start a new trading cycle for the bot"""
        market_price = Decimal(self.client.ticker_price(symbol=bot.symbol)["price"])
        
        cycle = TradingCycle(
            exchange=bot.exchange,
            symbol=bot.symbol,
            amount=bot.amount,
            grid_length=bot.grid_length,
            first_order_offset=bot.first_order_offset,
            num_orders=bot.num_orders,
            partial_num_orders=0,
            next_order_volume=bot.next_order_volume,
            price=float(market_price),
            profit_percentage=bot.profit_percentage,
            price_change_percentage=bot.price_change_percentage,
            status=CycleStatusType.ACTIVE,
        )
        
        self.db.add(cycle)
        self.db.commit()
        self.db.refresh(cycle)
        
        try:
            # Place initial grid orders
            orders = self.place_grid_orders(bot, cycle)
            self.db.add_all(orders)
            self.db.commit()
            
            return cycle
        except Exception as e:
            # Rollback cycle creation if order placement fails
            self.db.delete(cycle)
            self.db.commit()
            raise e

    def cancel_cycle_orders(self, cycle: TradingCycle):
        """Cancel all active orders in a cycle"""
        orders = self.db.query(Order).filter(
            Order.cycle_id == cycle.id,
            Order.status.in_([OrderStatusType.NEW, OrderStatusType.PARTIALLY_FILLED])
        ).all()
        
        for order in orders:
            try:
                self.client.cancel_order(
                    symbol=order.symbol,
                    orderId=order.exchange_order_id
                )
                order.status = OrderStatusType.CANCELED
            except Exception as e:
                logger.error(f"Failed to cancel order {order.exchange_order_id}: {e}")
        
        self.db.commit()

    def update_take_profit_order(self, cycle: TradingCycle):
        """Update or place take profit order after a buy order is filled"""
        filled_orders = self.db.query(Order).filter(
            Order.cycle_id == cycle.id,
            Order.side == SideType.BUY,
            Order.status == OrderStatusType.FILLED
        ).all()
        
        # Cancel existing take profit order if exists
        existing_tp = self.db.query(Order).filter(
            Order.cycle_id == cycle.id,
            Order.side == SideType.SELL,
            Order.status.in_([OrderStatusType.NEW, OrderStatusType.PARTIALLY_FILLED])
        ).first()
        
        if existing_tp:
            try:
                self.client.cancel_order(
                    symbol=existing_tp.symbol,
                    orderId=existing_tp.exchange_order_id
                )
                existing_tp.status = OrderStatusType.CANCELED
                self.db.commit()
            except Exception as e:
                logger.error(f"Failed to cancel take profit order: {e}")
        
        # Place new take profit order
        new_tp = self.place_take_profit_order(cycle.bot, cycle, filled_orders)
        self.db.add(new_tp)
        self.db.commit()

    def check_cycle_completion(self, cycle: TradingCycle):
        """Check if cycle is completed and can be closed"""
        # Check if take profit order is filled
        tp_order = self.db.query(Order).filter(
            Order.cycle_id == cycle.id,
            Order.side == SideType.SELL,
            Order.status == OrderStatusType.FILLED
        ).first()
        
        if tp_order:
            # Cancel remaining buy orders
            self.cancel_cycle_orders(cycle)
            
            # Mark cycle as completed
            cycle.status = CycleStatusType.COMPLETED
            self.db.commit()
            
            # Start new cycle if bot is still active
            bot = self.db.query(Bot).filter(Bot.id == cycle.bot_id).first()
            if bot and bot.is_active:
                self.start_new_cycle(bot) 
