-- Query 4: Historical Tick Data for Episode Replay
-- Pool: WETH-USDC 0.05% (0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640)
-- Purpose: Fetch tick-level price data for realistic episode simulation

WITH hourly_snapshots AS (
    SELECT
        date_trunc('hour', block_time) AS snapshot_time,
        -- Calculate WETH/USDC price from amounts
        -- token0 = USDC (6 decimals), token1 = WETH (18 decimals)
        AVG(ABS(CAST(amount1 AS DOUBLE)) / POW(10, 18) / NULLIF(ABS(CAST(amount0 AS DOUBLE)) / POW(10, 6), 0)) AS weth_price_usd,
        SUM(amount_usd) AS volume_usd,
        COUNT(*) AS swap_count
    FROM uniswap_v3_ethereum.Pool_evt_Swap
    WHERE contract_address = 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640
        AND block_time >= from_unixtime({{start_timestamp}})
        AND block_time < from_unixtime({{end_timestamp}})
    GROUP BY 1
),
tick_data AS (
    SELECT
        snapshot_time,
        weth_price_usd,
        -- Convert price to tick: tick = floor(log(price) / log(1.0001))
        -- For WETH/USDC, we need to invert since tick is for token0/token1
        CAST(FLOOR(LN(1.0 / weth_price_usd) / LN(1.0001)) AS INTEGER) AS tick,
        volume_usd,
        swap_count
    FROM hourly_snapshots
)
SELECT
    CAST(to_unixtime(snapshot_time) AS BIGINT) AS timestamp,
    snapshot_time,
    tick,
    weth_price_usd,
    volume_usd,
    swap_count
FROM tick_data
ORDER BY snapshot_time ASC;

-- Notes:
-- 1. This query returns hourly tick snapshots
-- 2. Tick calculation is approximate - for exact ticks, need sqrtPriceX96 from Swap events
-- 3. Volume is aggregated per hour
-- 4. For minute-level granularity, change date_trunc('hour', ...) to date_trunc('minute', ...)
-- 5. Typical 6-hour window will return ~6 rows (hourly) or ~360 rows (minute-level)
-- 6. Parameters: {{start_timestamp}} and {{end_timestamp}} as Unix timestamps

