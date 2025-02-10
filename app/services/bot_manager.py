import asyncio
from ..models import Bot
from ..database import get_db
from .trading_service import TradingService
from .bot_events_handler import BotEventsHandler


class BotManager:
    def __init__(self):
        self.ws_managers = {}
        self.active_bots = []

    async def install(self, bot: Bot):
        if not bot.is_active:
            return

        self.active_bots.append(bot)

        db = get_db(next)

        trading_service = TradingService(db=db, bot=bot)
        trading_service.launch()
        listen_key = trading_service.client.new_listen_key()["listenKey"]

        ws_manager = BotEventsHandler(
            bot=bot, trading_service=trading_service, db=db, listen_key=listen_key
        )
        self.ws_managers[bot.id] = ws_manager

        await ws_manager.start()

    async def release(self, bot):
        ws_manager = self.ws_managers[bot.id]
        await ws_manager.ws_client.close_connection()
        del self.ws_managers[bot.id]
        self.active_bots.remove(bot)

    async def install_bots(self, bots):
        await asyncio.gather(*(self.install(bot) for bot in bots))

    async def release_bots(self, bots):
        await asyncio.gather(*(self.release(bot) for bot in bots))

    async def release_all(self):
        await self.release_bots(self.active_bots)
