-- Query 1: Hourly Pool Volume & Implied Fees
-- Pool: WETH-USDC 0.05% (0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640)
-- Purpose: Determine fee budget available per hour to justify gas interventions

WITH hourly_trades AS (
    SELECT
        date_trunc('hour', block_time) AS hour,
        SUM(amount_usd) AS volume_usd,
        COUNT(*) AS trade_count
    FROM dex.trades
    WHERE blockchain = 'ethereum'
        AND project = 'uniswap'
        AND version = '3'
        AND pool_address = 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640
        AND block_time >= NOW() - INTERVAL '90' DAY
    GROUP BY 1
),
hourly_fees AS (
    SELECT
        hour,
        volume_usd,
        volume_usd * 0.0005 AS fees_usd,  -- 0.05% fee tier
        trade_count
    FROM hourly_trades
)
SELECT
    -- Summary statistics
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY fees_usd) AS fees_median_usd,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY fees_usd) AS fees_p75_usd,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY fees_usd) AS fees_p90_usd,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY fees_usd) AS fees_p95_usd,
    AVG(fees_usd) AS fees_mean_usd,
    
    -- Volume stats
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY volume_usd) AS volume_median_usd,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY volume_usd) AS volume_p90_usd,
    
    -- Trade frequency
    AVG(trade_count) AS avg_trades_per_hour,
    
    -- Total observations
    COUNT(*) AS hours_observed
FROM hourly_fees;

-- Also get time series for visualization
-- SELECT hour, fees_usd, volume_usd, trade_count
-- FROM hourly_fees
-- ORDER BY hour DESC
-- LIMIT 1000;
