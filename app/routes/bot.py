from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..services.trading_service import TradingService
from ..services.websocket_manager import WebsocketManager
from ..models import Bot, TradingCycle, Order
from ..schemas import (
    BotCreate, BotResponse,
    TradingCycleResponse,
    OrderResponse
)
from ..database import get_db
from ..enums import BotStatusType
import os
import uuid

router = APIRouter()

def get_trading_service(db: Session = Depends(get_db)) -> TradingService:
    # Initialize Binance client with credentials from environment
    client = Spot(
        api_key=os.getenv("BINANCE_API_KEY"),
        api_secret=os.getenv("BINANCE_API_SECRET"),
        base_url='https://testnet.binance.vision' if os.getenv("BINANCE_TESTNET") == '1' else 'https://api.binance.com'
    )
    return TradingService(client=client, db=db)

@router.post("/bots/", response_model=BotResponse)
async def create_bot(
    bot_data: BotCreate,
    db: Session = Depends(get_db),
    trading_service: TradingService = Depends(get_trading_service)
):
    """Create a new trading bot and start its first cycle"""
    try:
        # Create bot
        bot = Bot(**bot_data.dict())
        bot.status = BotStatusType.ACTIVE
        db.add(bot)
        db.commit()
        db.refresh(bot)
        
        # Start first trading cycle
        cycle = trading_service.start_new_cycle(bot)
        
        return bot
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bots/", response_model=List[BotResponse])
async def list_bots(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all trading bots"""
    bots = db.query(Bot).offset(skip).limit(limit).all()
    return bots

@router.get("/bots/{bot_id}", response_model=BotResponse)
async def get_bot(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Get specific bot details"""
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot

@router.post("/bots/{bot_id}/start")
async def start_bot(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    trading_service: TradingService = Depends(get_trading_service)
):
    """Start or resume bot trading"""
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    try:
        bot.is_active = True
        bot.status = BotStatusType.ACTIVE
        db.commit()
        
        # Start new cycle if no active cycle exists
        active_cycle = db.query(TradingCycle).filter(
            TradingCycle.bot_id == bot.id,
            TradingCycle.status == CycleStatusType.ACTIVE
        ).first()
        
        if not active_cycle:
            cycle = trading_service.start_new_cycle(bot)
        
        return {"message": "Bot started successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/bots/{bot_id}/stop")
async def stop_bot(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    trading_service: TradingService = Depends(get_trading_service)
):
    """Stop bot trading and cancel all active orders"""
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    try:
        # Cancel orders in active cycle
        active_cycle = db.query(TradingCycle).filter(
            TradingCycle.bot_id == bot.id,
            TradingCycle.status == CycleStatusType.ACTIVE
        ).first()
        
        if active_cycle:
            trading_service.cancel_cycle_orders(active_cycle)
            active_cycle.status = CycleStatusType.CANCELED
        
        bot.is_active = False
        bot.status = BotStatusType.STOPPED
        db.commit()
        
        return {"message": "Bot stopped successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bots/{bot_id}/cycles", response_model=List[TradingCycleResponse])
async def list_bot_cycles(
    bot_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all cycles for a specific bot"""
    cycles = db.query(TradingCycle).filter(
        TradingCycle.bot_id == bot_id
    ).offset(skip).limit(limit).all()
    return cycles

@router.get("/cycles/{cycle_id}/orders", response_model=List[OrderResponse])
async def list_cycle_orders(
    cycle_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all orders in a specific cycle"""
    orders = db.query(Order).filter(
        Order.cycle_id == cycle_id
    ).offset(skip).limit(limit).all()
    return orders 