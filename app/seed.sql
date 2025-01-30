-- First, insert the exchange key
INSERT INTO exchange_keys (
    id,
    name,
    exchange,
    api_key,
    api_secret,
    user_id,
    is_active,
    created_at,
    updated_at
) VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',  -- A fixed UUID for testing
    'Test Exchange Key',
    'BINANCE',
    'test_api_key',
    'test_api_secret',
    'b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',  -- A fixed user UUID
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

-- Then, insert the bot that references the exchange key
INSERT INTO bots (
    id,
    name,
    exchange,
    symbol,
    amount,
    grid_length,
    first_order_offset,
    num_orders,
    partial_num_orders,
    next_order_volume,
    profit_percentage,
    price_change_percentage,
    log_coefficient,
    profit_capitalization,
    upper_price_limit,
    status,
    is_active,
    user_id,
    exchange_key_id,
    created_at,
    updated_at
) VALUES (
    'c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',  -- A fixed UUID for testing
    'Test Bot',
    'BINANCE',
    'BTCUSDT',
    1000.0,                -- Initial amount
    10.0,                  -- Grid length
    1.0,                   -- First order offset
    5,                     -- Number of orders
    0,                     -- Partial number of orders
    5.0,                   -- Next order volume
    1.0,                   -- Profit percentage
    1.0,                   -- Price change percentage
    1.0,                   -- Log coefficient
    1.0,                   -- Profit capitalization
    30000.0,              -- Upper price limit
    'ACTIVE',             -- Status
    true,                 -- Is active
    'b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',  -- Same user UUID as above
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',  -- References the exchange key UUID from above
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);
