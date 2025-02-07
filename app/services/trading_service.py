from decimal import Decimal, ROUND_DOWN
from typing import List, Dict
from binance.spot import Spot
from ..models import Bot, TradingCycle, Order
from ..enums import OrderType, SideType, TimeInForceType, OrderStatusType, CycleStatusType
from sqlalchemy.orm import Session
import logging
import os

class TradingService:
    def __init__(self, db: Session, bot: Bot):
        self.client = Spot(
            api_key=bot.api_key,
            api_secret=bot.api_secret,
            base_url='https://testnet.binance.vision' if os.getenv("BINANCE_TESTNET") else 'https://api.binance.com'
        )
        self.db = db
        self.bot = bot
        self.cycle = self.db.query(TradingCycle).filter(
            TradingCycle.bot_id == self.bot.id,
            TradingCycle.status == CycleStatusType.ACTIVE
        ).first()

    def launch(self):
        """Launch a new trading cycle for the bot"""

        if not self.bot.is_active: return

        if self.cycle:
            self.query_open_orders()
            self.check_cycle_completion()
        else:
            self.start_new_cycle()

    def calculate_grid_prices(self, market_price: Decimal) -> List[Decimal]:
        """Calculate grid order prices"""
        # Convert bot parameters to Decimal to ensure consistent arithmetic
        first_order_offset = Decimal(str(self.bot.first_order_offset))
        grid_length = Decimal(str(self.bot.grid_length))
        
        first_order_price = market_price * (Decimal('1') - first_order_offset / Decimal('100'))
        total_drop = first_order_price * (grid_length / Decimal('100'))
        price_step = total_drop / (Decimal(str(self.bot.num_orders - 1))) if self.bot.num_orders > 1 else Decimal('0')
        
        prices = []
        for i in range(self.bot.num_orders):
            price = first_order_price - (price_step * Decimal(str(i)))
            prices.append(price)
        
        return prices

    # TODO: we need to get the step size from the client dynamically
    def _step_size(self, symbol: str) -> Decimal:
        """Get the step size for a symbol"""
        if symbol == "BTCUSDT":
            return Decimal('0.00001')
        elif symbol == "ETHUSDT":
            return Decimal('0.0001')
        else:
            raise ValueError(f"Unsupported symbol: {symbol}")

    def calculate_grid_quantities(self, prices: List[Decimal]) -> List[Decimal]:
        """Calculate quantities for each grid level"""
        # Convert bot parameters to Decimal
        amount = Decimal(str(self.bot.amount))
        next_order_volume = Decimal(str(self.bot.next_order_volume))
        
        base_quantity = amount / sum(prices)  # Initial equal distribution
        quantities = []
        
        current_quantity = base_quantity
        for _ in range(self.bot.num_orders):
            quantities.append(current_quantity)
            current_quantity *= (Decimal('1') + next_order_volume / Decimal('100'))
            
        # Normalize quantities to match total amount
        total_value = sum(p * q for p, q in zip(prices, quantities))
        scale_factor = amount / total_value
        quantities = [q * scale_factor for q in quantities]
        
        return quantities

    def create_binance_order(self, side: str, price: Decimal, quantity: Decimal, number: int) -> Order:
        """Create a Binance order and corresponding Order record"""

        if (price * quantity) < 5: # TODO: Make this dynamic
            raise Exception(f"Order notional value {price * quantity} is below minimum {5}")

        # rounding
        quantity = quantity.quantize(self._step_size(self.bot.symbol), rounding=ROUND_DOWN)
        if self.bot.symbol == "PEPEUSDT":
            price = round(price, 8)
        else:
            price = round(price, 2)

        try:
            binance_order = self.client.new_order(
                symbol=self.bot.symbol,
                side=side,
                type="LIMIT",
                timeInForce="GTC",
                quantity=str(quantity),
                price=str(price)
            )
            
            order = Order(
                exchange=self.bot.exchange,
                symbol=self.bot.symbol,
                side=SideType.BUY if side == "BUY" else SideType.SELL,
                time_in_force=TimeInForceType.GTC,
                type=OrderType.LIMIT,
                price=float(price),
                quantity=float(quantity),
                amount=float(price * quantity),
                status=OrderStatusType.NEW,
                number=number,
                exchange_order_id=binance_order["orderId"],
                exchange_order_data=binance_order,
                cycle_id=self.cycle.id
            )
            return order
            
        except Exception as e:
            raise Exception(f"Failed to create order: {e}")

    def place_grid_orders(self) -> List[Order]:
        """Place initial grid orders"""
        market_price = Decimal(self.client.ticker_price(symbol=self.bot.symbol)["price"])
        prices = self.calculate_grid_prices(market_price)
        quantities = self.calculate_grid_quantities(prices)
        
        orders = []
        for i, (price, quantity) in enumerate(zip(prices, quantities)):
            order = self.create_binance_order(
                side="BUY",
                price=price,
                quantity=quantity,
                number=i + 1
            )
            orders.append(order)
                
        return orders

    def place_take_profit_order(self, filled_orders: List[Order]) -> Order:
        """Place or update take profit order"""
        # Calculate average buy price and total quantity
        total_quantity = sum(order.quantity for order in filled_orders)
        total_cost = sum(order.price * order.quantity for order in filled_orders)
        avg_price = total_cost / total_quantity

        # Calculate take profit price
        take_profit_price = avg_price * (1 + self.bot.profit_percentage / 100)
        
        return self.create_binance_order(
            side="SELL",
            price=Decimal(str(take_profit_price)),
            quantity=Decimal(str(total_quantity)),
            number=len(filled_orders) + 1
        )

    def start_new_cycle(self) -> TradingCycle:
        """Start a new trading cycle for the bot"""
        # Check for existing active cycle
        active_cycle = self.db.query(TradingCycle).filter(
            TradingCycle.bot_id == self.bot.id,
            TradingCycle.status == CycleStatusType.ACTIVE
        ).first()
        
        if active_cycle:
            raise ValueError(f"Bot {self.bot.name} already has an active cycle")

        market_price = Decimal(self.client.ticker_price(symbol=self.bot.symbol)["price"])
        
        self.cycle = TradingCycle(
            exchange=self.bot.exchange,
            symbol=self.bot.symbol,
            amount=self.bot.amount,
            grid_length=self.bot.grid_length,
            first_order_offset=self.bot.first_order_offset,
            num_orders=self.bot.num_orders,
            partial_num_orders=0,
            next_order_volume=self.bot.next_order_volume,
            price=market_price,
            profit_percentage=self.bot.profit_percentage,
            price_change_percentage=self.bot.price_change_percentage,
            status=CycleStatusType.ACTIVE,
            bot_id=self.bot.id
        )
        
        self.db.add(self.cycle)
        self.db.commit()
        self.db.refresh(self.cycle)
        
        # Place initial grid orders
        orders = self.place_grid_orders()
        self.db.add_all(orders)
        self.db.commit()

        return self.cycle

    def cancel_cycle_orders(self):
        """Cancel all active orders in a cycle"""
        orders = self.db.query(Order).filter(
            Order.cycle_id == self.cycle.id,
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
                logging.error(f"Failed to cancel order {order.exchange_order_id}: {e}")
        
        self.db.commit()

    def update_take_profit_order(self):
        """Update or place take profit order after a buy order is filled"""
        filled_orders = self.db.query(Order).filter(
            Order.cycle_id == self.cycle.id,
            Order.side == SideType.BUY,
            Order.status == OrderStatusType.FILLED
        ).all()
        
        # Cancel existing take profit order if exists
        existing_tp = self.db.query(Order).filter(
            Order.cycle_id == self.cycle.id,
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
                logging.error(f"Failed to cancel take profit order: {e}")
        
        # Place new take profit order
        new_tp = self.place_take_profit_order(filled_orders)
        self.db.add(new_tp)
        self.db.commit()

    def check_cycle_completion(self):
        """Check if cycle is completed and can be closed"""
        # Check if take profit order is filled
        tp_order = self.db.query(Order).filter(
            Order.cycle_id == self.cycle.id,
            Order.side == SideType.SELL,
            Order.status == OrderStatusType.FILLED
        ).first()
        
        if tp_order:
            # Cancel remaining buy orders
            self.cancel_cycle_orders()
            
            # Mark cycle as completed
            self.cycle.status = CycleStatusType.COMPLETED
            self.db.commit()
            
            # Start new cycle if bot is still active
            bot = self.db.query(Bot).filter(Bot.id == self.cycle.bot_id).first()
            if bot and bot.is_active:
                self.start_new_cycle()

    def check_grid_update(self, current_price: float):
        """Check if grid needs to be updated based on price movement"""
        if not self.cycle:
            return

        price_change = abs(current_price - self.cycle.price) / self.cycle.price * 100

        # Update cycle price
        self.cycle.price = current_price
        self.db.commit()

        if price_change >= self.bot.price_change_percentage:
            # Cancel existing orders and create new grid
            self.cancel_cycle_orders()

            # Place new grid orders
            try:
                orders = self.place_grid_orders()
                self.db.add_all(orders)
                self.db.commit()
            except Exception as e:
                logging.error(f"Failed to update grid: {e}")

    def query_open_orders(self):
        """Query open orders for the cycle"""
        orders = self.db.query(Order).filter(
            Order.cycle_id == self.cycle.id,
            Order.status.in_([OrderStatusType.NEW, OrderStatusType.PARTIALLY_FILLED])
        ).all()

        for order in orders:
            try:
                binance_order = self.client.get_order(
                    symbol=order.symbol,
                    orderId=order.exchange_order_id
                )

                if binance_order["status"] != order.status:
                    order.status = binance_order["status"]
                    self.db.commit()

            except Exception as e:
                logging.error(f"Failed to query order {order.exchange_order_id}: {e}")

        return orders
