from decimal import Decimal, ROUND_DOWN
from typing import List, Dict
from binance.spot import Spot
from ..models import Bot, TradingCycle, Order
from ..enums import OrderType, SideType, TimeInForceType, OrderStatusType, CycleStatusType
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging
import os
import time

class TradingService:
    def __init__(self, db: Session, bot: Bot):
        self.client = Spot(
            api_key=bot.api_key,
            api_secret=bot.api_secret,
            base_url='https://testnet.binance.vision' if os.getenv("BINANCE_TESTNET") else 'https://api.binance.com'
        )
        self.db = db
        self.bot = bot
        self.cycle = bot.trading_cycles.filter(
            TradingCycle.status == CycleStatusType.ACTIVE
        ).first()

    def launch(self):
        """Launch a new trading cycle for the bot"""

        if not self.bot.is_active:
            return

        if self.cycle:
            self.query_open_orders()

            if self.cycle.orders.count() == 0:
                self.place_grid_orders()
        else:
            self.start_new_cycle()

    def calculate_grid_prices(self, market_price: Decimal) -> List[Decimal]:
        """Calculate grid order prices"""
        first_order_price = market_price * (Decimal('1') - self.cycle.first_order_offset / Decimal('100'))
        total_drop = first_order_price * (self.cycle.grid_length / Decimal('100'))
        price_step = total_drop / (Decimal(str(self.cycle.num_orders - 1))) if self.cycle.num_orders > 1 else Decimal('0')
        
        prices = []
        for i in range(self.cycle.num_orders):
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
        elif symbol == "PEPEUSDT":
            return Decimal('0.00000001')
        else:
            raise ValueError(f"Unsupported symbol: {symbol}")

    def calculate_grid_quantities(self, prices: List[Decimal]) -> List[Decimal]:
        """Calculate quantities for each grid level"""        
        filled_amount = sum(order.quantity_filled * order.price for order in self.buy_orders())
        if filled_amount >= self.cycle.amount:
            raise Exception(f"Filled amount {filled_amount} is greater than the cycle amount {self.cycle.amount}")

        base_quantity = (self.cycle.amount - filled_amount) / sum(prices)  # Initial equal distribution
        quantities = []
        
        current_quantity = base_quantity
        for _ in range(self.cycle.num_orders):
            quantities.append(current_quantity)
            current_quantity *= (Decimal('1') + self.cycle.next_order_volume / Decimal('100'))

        # Normalize quantities to match total amount
        total_value = sum(p * q for p, q in zip(prices, quantities))
        scale_factor = self.cycle.amount / total_value
        quantities = [q * scale_factor for q in quantities]
        
        return quantities

    def create_binance_order(self, side: str, price: Decimal, quantity: float, number: int) -> Order:
        """Create a Binance order and corresponding Order record"""

        notional_value = price * quantity
        if self.cycle.symbol == "PEPEUSDT" and notional_value < 1:  # TODO: Make this dynamic
            raise Exception(f"Order notional value {notional_value} is below minimum {1}")
        elif notional_value < 5:
            raise Exception(f"Order notional value {notional_value} is below minimum {5}")

        # rounding
        quantity = Decimal(quantity).quantize(self._step_size(self.cycle.symbol), rounding=ROUND_DOWN)
        if self.cycle.symbol == "PEPEUSDT":
            price = round(price, 8)
        else:
            price = round(price, 2)

        try:
            binance_order = self.client.new_order(
                symbol=self.cycle.symbol,
                side=side,
                type="LIMIT",
                timeInForce="GTC",
                quantity=str(quantity),
                price=str(price)
            )
            
            order = Order(
                exchange=self.bot.exchange,
                symbol=self.cycle.symbol,
                side=SideType.BUY if side == "BUY" else SideType.SELL,
                time_in_force=TimeInForceType.GTC,
                type=OrderType.LIMIT,
                price=price,
                quantity=quantity,
                amount=price * quantity,
                status=OrderStatusType.NEW,
                number=number,
                exchange_order_id=binance_order["orderId"],
                exchange_order_data=binance_order,
                cycle_id=self.cycle.id
            )
            self.db.add(order)
            self.db.commit()
            
        except Exception as e:
            raise Exception(f"Failed to create order: {e}")

    # this is a hack to ensure the market price is above 60000 on BTCUSDT pair
    # to avoid failures "Filter failure: PERCENT_PRICE_BY_SIDE"
    # happening in testnet because of high volatility in testnet
    def fetch_market_price(self) -> Decimal:
        while True:
            market_price = Decimal(self.client.ticker_price(symbol=self.cycle.symbol)["price"])

            if market_price > 60000 or self.cycle.symbol != "BTCUSDT":
                break
            time.sleep(5)

        return market_price

    def place_grid_orders(self) -> List[Order]:
        """Place initial grid orders"""

        market_price = self.fetch_market_price()
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

        self.cycle.quantity = self.db.query(
            func.sum(Order.quantity)
        ).filter(
            Order.cycle_id == self.cycle.id,
            Order.side == SideType.BUY,
            Order.status == OrderStatusType.NEW
        ).scalar()

        self.db.commit()

    def sell_quantity_filled(self) -> Decimal:
        return self.db.query(
            func.sum(Order.quantity_filled)
        ).filter(
            Order.cycle_id == self.cycle.id,
            Order.side == SideType.SELL
        ).scalar() or 0

    def buy_orders(self) -> List[Order]:
        return self.cycle.orders.filter(
            Order.side == SideType.BUY
        ).all()

    def place_take_profit_order(self) -> Order:
        """Place or update take profit order"""
        # Calculate average buy price and total quantity
        total_quantity = sum(order.quantity_filled for order in self.buy_orders())
        total_cost = sum(order.price * order.quantity_filled for order in self.buy_orders())
        avg_price = total_cost / total_quantity

        # Calculate take profit price
        take_profit_price = avg_price * (1 + self.cycle.profit_percentage / 100)
        
        self.create_binance_order(
            side = "SELL",
            price = take_profit_price,
            quantity = total_quantity - self.sell_quantity_filled(),
            number = len(self.buy_orders()) + 1
        )

    def start_new_cycle(self) -> TradingCycle:
        """Start a new trading cycle for the bot"""
        # Check for existing active cycle
        active_cycle = self.bot.trading_cycles.filter(
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
            next_order_volume=self.bot.next_order_volume,
            price=market_price,
            profit_percentage=self.bot.profit_percentage,
            price_change_percentage=self.bot.price_change_percentage,
            status=CycleStatusType.ACTIVE,
            bot_id=self.bot.id
        )
        
        self.db.add(self.cycle)
        self.db.commit()
        
        # Place initial grid orders
        self.place_grid_orders()

        return self.cycle

    def cancel_cycle_orders(self):
        """Cancel all active orders in a cycle"""
        orders = self.cycle.orders.filter(
            Order.status == OrderStatusType.NEW
        ).all()

        for order in orders:
            try:
                response = self.client.cancel_order(
                    symbol=order.symbol,
                    orderId=order.exchange_order_id
                )
                if response["status"] == "CANCELED":
                    order.quantity_filled = Decimal(response["executedQty"])
                    order.status = OrderStatusType.CANCELED
                    self.db.commit()
            except Exception as e:
                logging.error(f"Failed to cancel order {order.exchange_order_id}: {e}")

    def update_take_profit_order(self):
        """Update or place take profit order after a buy order is filled"""
        tp_order = self.cycle.orders.filter(
                    Order.side == SideType.SELL,
                    Order.status.in_([OrderStatusType.NEW, OrderStatusType.PARTIALLY_FILLED])
        ).first()

        if tp_order:
            try:
                response = self.client.cancel_order(
                    symbol=tp_order.symbol,
                    orderId=tp_order.exchange_order_id
                )

                if response["status"] == "CANCELED":
                    tp_order.quantity_filled = Decimal(response["executedQty"])
                    tp_order.status = OrderStatusType.CANCELED
                    self.db.commit()

            except Exception as e:
                logging.error(f"Failed to cancel take profit order: {e}")

        if tp_order and tp_order.status == OrderStatusType.CANCELED or tp_order is None:
            # Place new take profit order
            new_tp = self.place_take_profit_order()

    def check_cycle_completion(self):
        """Check if cycle is completed and can be closed"""

        if self.sell_quantity_filled() == self.cycle.quantity:
            # Mark cycle as completed
            self.cycle.status = CycleStatusType.COMPLETED
            self.db.commit()
            
            # Start new cycle if bot is still active
            if self.bot.is_active:
                self.start_new_cycle()

    def check_grid_update(self, current_price: Decimal):
        """Check if grid needs to be updated based on price movement"""
        if not self.cycle:
            return

        price_increase = (current_price - self.cycle.price) / self.cycle.price * 100
        order_statuses = [status[0] for status in self.db.query(
            func.distinct(Order.status)
        ).filter(Order.cycle_id == self.cycle.id).all()]

        if price_increase >= self.cycle.price_change_percentage and order_statuses == [OrderStatusType.NEW]:
            # Update cycle price
            self.cycle.price = current_price
            self.db.commit()

            # Cancel existing orders and create new grid
            self.cancel_cycle_orders()
            self.place_grid_orders()

    def query_open_orders(self):
        """Query open orders for the cycle"""
        orders = self.cycle.orders.filter(
            Order.status.in_([OrderStatusType.NEW, OrderStatusType.PARTIALLY_FILLED])
        ).all()

        for order in orders:
            try:
                binance_order = self.client.get_order(
                    symbol=order.symbol,
                    orderId=order.exchange_order_id
                )

                order.status = binance_order["status"]
                order.quantity_filled = Decimal(binance_order["executedQty"])
                self.db.commit()

            except Exception as e:
                logging.error(f"Failed to query order {order.exchange_order_id}: {e}")

        return orders
