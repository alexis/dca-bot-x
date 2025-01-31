import asyncio
from typing import Dict, Set
from binance.spot import Spot
# from binance.websocket.websocket_client import WebsocketClient
from ..models import Bot, TradingCycle, Order
from .trading_service import TradingService
from sqlalchemy.orm import Session
from ..enums import OrderStatusType, SideType
import logging

logger = logging.getLogger(__name__)

class BotWebsocketManager:
    def __init__(self, trading_service: TradingService, db: Session, ws_client: Spot):
        self.trading_service = trading_service
        self.db = db
        self.ws_client = ws_client
        self.active_bots: Dict[str, Bot] = {}
        self.active_cycles: Dict[str, TradingCycle] = {}
        self.active_symbols: Set[str] = set()

    async def start(self):
        """Start WebSocket connection and subscribe to relevant streams"""
        # Subscribe to order updates for active bots
        for symbol in self.active_symbols:
            self.ws_client.user_data(
                listen_key=self._get_listen_key(),
                callback=self.handle_user_data
            )
            self.ws_client.ticker(
                symbol=symbol,
                callback=self.handle_price_update
            )

    def handle_user_data(self, msg: dict):
        """Handle order execution updates"""
        if msg.get("e") == "executionReport":
            self._process_order_update(msg)

    def handle_price_update(self, msg: dict):
        """Handle price updates and check if grid needs to be updated"""
        symbol = msg.get("s")
        price = float(msg.get("c", 0))
        
        for bot_id, bot in self.active_bots.items():
            if bot.symbol == symbol:
                self._check_grid_update(bot, price)

    def _process_order_update(self, msg: dict):
        """Process order execution updates and manage take profit orders"""
        order_id = msg.get("i")
        status = msg.get("X")
        symbol = msg.get("s")
        
        # Find order in database
        order = self.db.query(Order).filter(
            Order.exchange_order_id == str(order_id)
        ).first()
        
        if not order:
            return
            
        cycle = self.db.query(TradingCycle).filter(
            TradingCycle.id == order.cycle_id
        ).first()
        
        if status == "FILLED":
            # Update order status
            order.status = OrderStatusType.FILLED
            order.exchange_order_data = msg
            self.db.commit()
            
            if order.side == SideType.BUY:
                # Update take profit order
                self.trading_service.update_take_profit_order(cycle)
            elif order.side == SideType.SELL:
                # Check if cycle is completed
                self.trading_service.check_cycle_completion(cycle)

    def _check_grid_update(self, bot: Bot, current_price: float):
        """Check if grid needs to be updated based on price movement"""
        cycle = self.active_cycles.get(str(bot.id))
        if not cycle:
            return
            
        price_change = abs(current_price - cycle.price) / cycle.price * 100
        if price_change >= bot.price_change_percentage:
            # Cancel existing orders and create new grid
            self.trading_service.cancel_cycle_orders(cycle)
            
            # Update cycle price
            cycle.price = current_price
            self.db.commit()
            
            # Place new grid orders
            try:
                orders = self.trading_service.place_grid_orders(bot, cycle)
                self.db.add_all(orders)
                self.db.commit()
            except Exception as e:
                logger.error(f"Failed to update grid: {e}")

    def _get_listen_key(self) -> str:
        """Get Binance listen key for user data stream"""
        return self.trading_service.client.new_listen_key()["listenKey"] 
