-- Query 5: LP Position Performance for Baseline Validation
-- Pool: WETH-USDC 0.05% (0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640)
-- Purpose: Fetch real LP position performance to validate simulated baselines
-- Dune v2 Schema

WITH position_mints AS (
    SELECT
        tx_hash,
        block_time,
        owner,
        tickLower AS tick_lower,
        tickUpper AS tick_upper,
        amount AS liquidity,
        amount0,
        amount1
    FROM uniswap_v3_ethereum.Mint
    WHERE contract_address = 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640
        AND block_time >= from_unixtime({{start_timestamp}})
        AND block_time < from_unixtime({{end_timestamp}})
),
position_burns AS (
    SELECT
        tx_hash,
        block_time,
        owner,
        tickLower AS tick_lower,
        tickUpper AS tick_upper,
        amount AS liquidity,
        amount0,
        amount1
    FROM uniswap_v3_ethereum.Burn
    WHERE contract_address = 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640
        AND block_time >= from_unixtime({{start_timestamp}})
        AND block_time < from_unixtime({{end_timestamp}})
),
position_collects AS (
    SELECT
        tx_hash,
        block_time,
        owner,
        tickLower AS tick_lower,
        tickUpper AS tick_upper,
        amount0 AS fee0_collected,
        amount1 AS fee1_collected
    FROM uniswap_v3_ethereum.Collect
    WHERE contract_address = 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640
        AND block_time >= from_unixtime({{start_timestamp}})
        AND block_time < from_unixtime({{end_timestamp}})
),
position_summary AS (
    SELECT
        m.owner,
        m.tick_lower,
        m.tick_upper,
        (m.tick_upper - m.tick_lower) AS width_ticks,
        m.block_time AS entry_time,
        COALESCE(b.block_time, from_unixtime({{end_timestamp}})) AS exit_time,
        -- Fee collection (in USD, approximate using $2000 WETH price)
        COALESCE(SUM(CAST(c.fee0_collected AS DOUBLE)) / POW(10, 6), 0) + 
        COALESCE(SUM(CAST(c.fee1_collected AS DOUBLE)) / POW(10, 18) * 2000, 0) AS fees_collected_usd,
        COUNT(DISTINCT c.tx_hash) AS collect_count
    FROM position_mints m
    LEFT JOIN position_burns b
        ON m.owner = b.owner
        AND m.tick_lower = b.tick_lower
        AND m.tick_upper = b.tick_upper
        AND b.block_time > m.block_time
    LEFT JOIN position_collects c
        ON m.owner = c.owner
        AND m.tick_lower = c.tick_lower
        AND m.tick_upper = c.tick_upper
        AND c.block_time BETWEEN m.block_time AND COALESCE(b.block_time, from_unixtime({{end_timestamp}}))
    GROUP BY 1, 2, 3, 4, 5, 6
)
SELECT
    owner,
    tick_lower,
    tick_upper,
    width_ticks,
    CAST(to_unixtime(entry_time) AS BIGINT) AS entry_timestamp,
    CAST(to_unixtime(exit_time) AS BIGINT) AS exit_timestamp,
    CAST(date_diff('second', entry_time, exit_time) AS BIGINT) AS duration_seconds,
    fees_collected_usd,
    collect_count,
    -- Estimate gas costs (2 USD per mint/burn, 0.5 USD per collect)
    (2.0 + CASE WHEN exit_time < from_unixtime({{end_timestamp}}) THEN 2.0 ELSE 0 END + collect_count * 0.5) AS estimated_gas_usd,
    -- Net PnL (fees - gas, excluding IL)
    fees_collected_usd - (2.0 + CASE WHEN exit_time < from_unixtime({{end_timestamp}}) THEN 2.0 ELSE 0 END + collect_count * 0.5) AS net_pnl_usd
FROM position_summary
WHERE width_ticks >= COALESCE({{min_width_ticks}}, 0)
    AND width_ticks <= COALESCE({{max_width_ticks}}, 1000000)
ORDER BY fees_collected_usd DESC
LIMIT 100;
