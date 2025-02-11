import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Bot, Base
from app.services.bot_manager import BotManager
from uuid import uuid4

@pytest.fixture
def bot_manager():
    """Create a fresh BotManager instance for each test"""
    return BotManager()

class MockTradingService:
    def __init__(self, **kwargs):
        self.client = AsyncMock()
        self.client.new_listen_key.return_value = {"listenKey": "test_listen_key"}
        self.launch = AsyncMock()
        self.initialize = AsyncMock()
        self.db = kwargs.get('db')
        self.bot = kwargs.get('bot')

class MockBotEventsHandler:
    def __init__(self, **kwargs):
        self.ws_client = AsyncMock()
        self.ws_client.close_connection = AsyncMock()
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.db = kwargs.get('db')
        self.bot = kwargs.get('bot')
        self.trading_service = kwargs.get('trading_service')


@pytest.mark.skip
@pytest.mark.asyncio
async def test_install_bot(db_session, bot_manager, test_bot):
    """Test if a bot is correctly installed"""
    mock_trading_service = MagicMock()
    mock_trading_service.client.new_listen_key.return_value = {"listenKey": "test_key"}
    mock_trading_service.client.launch.return_value = True

    mock_events_handler = AsyncMock()
    mock_events_handler.start = AsyncMock()

    with pytest.MonkeyPatch.context() as m:
        # Patch TradingService and BotEventsHandler
        m.setattr("app.services.trading_service.TradingService", lambda **kw: mock_trading_service)
        m.setattr("app.services.bot_events_handler.BotEventsHandler", lambda **kw: mock_events_handler)

        await bot_manager.install(test_bot, db=db_session)

    assert test_bot in bot_manager.active_bots
    assert test_bot.id in bot_manager.events_handlers
    mock_events_handler.start.assert_awaited()


@pytest.mark.asyncio
async def test_release_bot(bot_manager, test_bot):
    """Test releasing an active bot"""
    mock_trading_service = MockTradingService(bot=test_bot)
    mock_events_handler = MockBotEventsHandler(bot=test_bot, trading_service=mock_trading_service)
    
    # Add bot to active bots
    bot_manager.active_bots.append(test_bot)
    bot_manager.events_handlers[test_bot.id] = mock_events_handler

    await bot_manager.release(test_bot)

    assert test_bot.id not in bot_manager.events_handlers
    assert test_bot not in bot_manager.active_bots
    mock_events_handler.ws_client.close_connection.assert_awaited_once()

@pytest.mark.skip
@pytest.mark.asyncio
async def test_install_bots(bot_manager):
    """Test installing multiple bots"""
    bots = [Bot(id='1', name='B', is_active=True), Bot(id='2', name='C', is_active=True)]

    with pytest.MonkeyPatch.context() as m:
        # Mock dependencies
        m.setattr("app.services.trading_service.TradingService", lambda db, bot: MagicMock())
        m.setattr("app.services.bot_events_handler.BotEventsHandler", lambda **kwargs: AsyncMock())

        await bot_manager.install_bots(bots)

    assert len(bot_manager.active_bots) == 2
    assert all(bot.id in bot_manager.events_handlers for bot in bots)

@pytest.mark.asyncio
async def test_release_all(bot_manager):
    """Test releasing all active bots"""
    bots = [Bot(id='1', name='B', is_active=True), Bot(id='2', name='C', is_active=True)]

    mock_handlers = {}
    for bot in bots:
        mock_trading_service = MockTradingService(bot=bot)
        mock_handler = MockBotEventsHandler(bot=bot, trading_service=mock_trading_service)
        mock_handlers[bot.id] = mock_handler
        bot_manager.events_handlers[bot.id] = mock_handler
        bot_manager.active_bots.append(bot)

    await bot_manager.release_all()

    assert not bot_manager.active_bots
    assert not bot_manager.events_handlers
    for bot in bots:
        mock_handlers[bot.id].ws_client.close_connection.assert_awaited_once()
