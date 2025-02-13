INSERT INTO bots (
    id,
    name,
    exchange,
    symbol,
    amount,
    grid_length,
    first_order_offset,
    num_orders,
    next_order_volume,
    profit_percentage,
    price_change_percentage,
    upper_price_limit,
    status,
    is_active,
    api_key,
    api_secret,
    created_at,
    updated_at
) VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',  -- UUID
    'Test Bot',
    'BINANCE',
    'BTCUSDT',
    250.0,                -- amount
    10.0,                  -- grid_length
    1,                   -- first_order_offset
    5,                     -- num_orders
    20.0,                   -- next_order_volume
    5.0,                   -- profit_percentage
    1.0,                   -- price_change_percentage
    30000.0,              -- upper_price_limit
    'RUNNING',             -- status
    true,                 -- is_active
    'api_key',       -- api_key
    'api_secret',    -- api_secret
    CURRENT_TIMESTAMP,    -- created_at
    CURRENT_TIMESTAMP     -- updated_at
);
