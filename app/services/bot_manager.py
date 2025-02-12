import asyncio
from typing import Type, Optional

from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Bot
from .bot_events_handler import BotEventsHandler
from .trading_service import TradingService


class BotManager:
    def __init__(
        self,
        trading_service_class: Type[TradingService] = TradingService,
        events_handler_class: Type[BotEventsHandler] = BotEventsHandler,
        db: Optional[Session] = None
    ):
        self.trading_service_class = trading_service_class
        self.events_handler_class = events_handler_class
        self.db = db
        self.active_bots = []
        self.events_handlers = {}

    async def install(self, bot: Bot):
        if not bot.is_active:
            return

        db = self.db or next(get_db())
        bot = db.merge(bot)

        self.active_bots.append(bot)
        trading_service = self.trading_service_class(db=db, bot=bot)
        trading_service.launch()
        listen_key = trading_service.client.new_listen_key()["listenKey"]

        events_handler = self.events_handler_class(
            bot=bot, trading_service=trading_service, db=db, listen_key=listen_key
        )
        self.events_handlers[bot.id] = events_handler
        await events_handler.start()

    async def install_bots(self, bots):
        await asyncio.gather(*(self.install(bot) for bot in bots))

    def release(self, bot):
        ws_manager = self.events_handlers[bot.id]
        ws_manager.ws_client.stop()
        del self.events_handlers[bot.id]
        self.active_bots.remove(bot)

    def release_all(self):
        for bot in reversed(self.active_bots):
            self.release(bot)
