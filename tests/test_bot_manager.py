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
    return BotManager(MockTradingService, MockBotEventsHandler)

class MockTradingService:
    def __init__(self, **kwargs):
        self.client = Mock()
        self.client.new_listen_key.return_value = {"listenKey": "test_listen_key"}
        self.launch = Mock()
        self.initialize = Mock()
        self.db = kwargs.get('db')
        self.bot = kwargs.get('bot')

class MockBotEventsHandler:
    def __init__(self, **kwargs):
        self.ws_client = AsyncMock()
        self.ws_client.stop = MagicMock()
        self.start = AsyncMock()
        self.db = kwargs.get('db')
        self.bot = kwargs.get('bot')
        self.trading_service = kwargs.get('trading_service')

@pytest.mark.asyncio
async def test_install_bot(bot_manager, test_bot):
    """Test if a bot is correctly installed"""
    await bot_manager.install(test_bot)

    assert test_bot.id in [bot.id for bot in bot_manager.active_bots]
    assert test_bot.id in bot_manager.events_handlers
    bot_manager.events_handlers[test_bot.id].start.assert_awaited_once()

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
    mock_events_handler.ws_client.stop.assert_called_once_with()

@pytest.mark.asyncio
async def test_install_bots(bot_manager):
    """Test installing multiple bots"""
    bots = [Bot(id=uuid4(), name='B', is_active=True), Bot(id=uuid4(), name='C', is_active=True)]

    await bot_manager.install_bots(bots)

    assert len(bot_manager.active_bots) == 2
    assert all(bot.id in bot_manager.events_handlers for bot in bots)

@pytest.mark.asyncio
async def test_release_all(bot_manager):
    """Test releasing all active bots"""
    bots = [Bot(id=uuid4(), name='B', is_active=True), Bot(id=uuid4(), name='C', is_active=True)]

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
        mock_handlers[bot.id].ws_client.stop.assert_called_once_with()
