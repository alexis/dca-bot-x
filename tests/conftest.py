import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.database import get_db
from app.services.trading import TradingService
from app.models import Base
from unittest.mock import Mock
import os

# Test database URL
DATABASE_URL = os.getenv('TEST_DATABASE_URL', "postgresql://postgres:postgres@test-db:5432/test_trading_db")

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

#Base = declarative_base()

@pytest.fixture(scope="session")
def db_engine():
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def mock_binance_client():
    return Mock()

@pytest.fixture
def trading_service(mock_binance_client, db_session):
    return TradingService(client=mock_binance_client, db=db_session) 
