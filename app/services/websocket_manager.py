import asyncio
from typing import Dict, Set
from binance.websocket.spot.websocket_stream import SpotWebsocketStreamClient
from ..models import Bot, Order
from .trading_service import TradingService
from sqlalchemy.orm import Session
from ..enums import OrderStatusType, SideType
import logging
import os
import json
class WebsocketManager:
    def __init__(self, bot: Bot, trading_service: TradingService, db: Session, listen_key: str):
        self.bot = bot
        self.trading_service = trading_service
        self.db = db
        self.active_symbols: Set[str] = ['BTCUSDT', 'ETHUSDT']
        self.listen_key = listen_key
        self.ws_client = SpotWebsocketStreamClient(
            stream_url=self._stream_url(),
            on_message=self.message_handler
        )

    def _stream_url(self):
        return "wss://stream.testnet.binance.vision" if os.getenv("BINANCE_TESTNET") else "wss://stream.binance.com"

    def message_handler(self, _, msg):
        if os.getenv("ENV") == "development":
            logging.info(msg)
        
        json_msg = json.loads(msg)
        
        match json_msg.get("e"):
            case "executionReport":
                self._handle_execution_report(json_msg)
            case "24hrTicker":
                self._handle_price_update(json_msg)

    async def start(self):
        """Start WebSocket connection and subscribe to relevant streams"""

        self.ws_client.user_data(listen_key=self.listen_key)

        for symbol in self.active_symbols:
            self.ws_client.ticker(symbol=symbol)

    def _handle_price_update(self, msg: dict):
        """Handle price updates and check if grid needs to be updated"""
        symbol = msg.get("s")
        price = float(msg.get("c", 0))
        
        if self.bot.symbol == symbol:
            self.trading_service.check_grid_update(price)

    def _handle_execution_report(self, msg: dict):
        """Process order execution updates and manage take profit orders"""

        order_id = msg.get("i")
        status = msg.get("X")
        symbol = msg.get("s")
        
        # Find order in the database
        order = self.db.query(Order).filter(
            Order.exchange_order_id == str(order_id)
        ).first()

        if order and status == "FILLED":
            # Update order status
            order.status = OrderStatusType.FILLED
            order.exchange_order_data = msg
            self.db.commit()
            
            if order.side == SideType.BUY:
                # Update take profit order
                self.trading_service.update_take_profit_order()
            elif order.side == SideType.SELL:
                # Check if cycle is completed
                self.trading_service.check_cycle_completion()
