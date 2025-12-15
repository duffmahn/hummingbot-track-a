-- Historical Ticks Query - FIXED PRICE CALCULATION
-- Calculates price directly from tick for accuracy

WITH hourly_snapshots AS (
    SELECT
        date_trunc('hour', evt_block_time) AS snapshot_time,
        -- Get average tick from sqrtPriceX96 if available, otherwise calculate from amounts
        AVG(CAST(tick AS DOUBLE)) AS avg_tick,
        -- Calculate volume from amounts
        SUM(ABS(CAST(amount0 AS DOUBLE)) / POW(10, 6)) AS volume_usdc,
        SUM(ABS(CAST(amount1 AS DOUBLE)) / POW(10, 18)) AS volume_weth,
        COUNT(*) AS swap_count
    FROM uniswap_v3_ethereum.uniswapv3pool_evt_swap
    WHERE contract_address = from_hex('88e6a0c2ddd26feeb64f039a2c41296fcb3f5640')
        AND evt_block_time >= from_unixtime({{start_timestamp}})
        AND evt_block_time < from_unixtime({{end_timestamp}})
    GROUP BY 1
),
tick_data AS (
    SELECT
        snapshot_time,
        CAST(ROUND(avg_tick) AS INTEGER) AS tick,
        -- Calculate WETH price from tick: price = 1.0001^tick
        -- For USDC/WETH pool (token0=USDC, token1=WETH), tick is USDC per WETH
        -- WETH price in USD = 1.0001^tick (already accounts for decimals in Uniswap v3)
        POW(1.0001, avg_tick) AS weth_price_usd,
        volume_usdc,
        volume_weth,
        swap_count
    FROM hourly_snapshots
    WHERE avg_tick IS NOT NULL
)
SELECT
    CAST(to_unixtime(snapshot_time) AS BIGINT) AS timestamp,
    snapshot_time,
    tick,
    weth_price_usd,
    COALESCE(volume_usdc, 0) AS volume_usdc,
    COALESCE(volume_weth, 0) AS volume_weth,
    swap_count
FROM tick_data
ORDER BY snapshot_time ASC;
