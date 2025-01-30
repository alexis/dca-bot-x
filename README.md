# Binance DCA Trading Bot

A cloud-based Dollar Cost Averaging (DCA) trading bot for Binance exchange. The bot implements a grid trading strategy with dynamic position sizing and automated profit taking.

## Features

- Grid trading strategy with customizable parameters
- WebSocket integration for real-time order updates
- Automatic take-profit order management
- Position size scaling based on grid levels
- REST API for bot management
- PostgreSQL database for state persistence
- Docker containerization

## Technical Architecture

### Components

- **FastAPI Backend**: Handles HTTP requests and WebSocket connections
- **PostgreSQL Database**: Stores bot configurations, trading cycles, and orders
- **Binance API Integration**: Real-time market data and order execution
- **WebSocket Manager**: Maintains connections for real-time updates
- **Trading Service**: Implements core trading logic

### Trading Logic

The bot implements a DCA (Dollar Cost Averaging) strategy with the following features:

1. **Grid Setup**:
   - Creates a grid of buy orders below current market price
   - First order offset configurable from market price
   - Equal price intervals between grid levels
   - Increasing position sizes at lower levels

2. **Take Profit Management**:
   - Automatic take-profit order after initial buy
   - Dynamic take-profit updates based on average entry price
   - Profit percentage configurable per bot

3. **Position Sizing**:
   - Base position size calculated from total investment amount
   - Position size increases by configured percentage at each level
   - Total grid investment matches configured amount

## API Endpoints

### Bot Management 