-- Query 3: Realized Volatility & Jump Rate
-- Pool: WETH-USDC 0.05% (0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640)
-- Purpose: Determine regime frequencies and volatility characteristics

WITH hourly_prices AS (
    SELECT
        date_trunc('hour', minute) AS hour,
        AVG(price) AS avg_price
    FROM prices.usd
    WHERE blockchain = 'ethereum'
        AND contract_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2  -- WETH
        AND minute >= NOW() - INTERVAL '90' DAY
    GROUP BY 1
),
returns AS (
    SELECT
        hour,
        avg_price,
        LN(avg_price / LAG(avg_price) OVER (ORDER BY hour)) AS log_return,
        ABS(LN(avg_price / LAG(avg_price) OVER (ORDER BY hour))) AS abs_log_return
    FROM hourly_prices
),
rolling_stats AS (
    SELECT
        hour,
        log_return,
        abs_log_return,
        -- Rolling 24h realized volatility (annualized)
        STDDEV(log_return) OVER (
            ORDER BY hour
            ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
        ) * SQRT(24 * 365) AS realized_vol_24h,
        -- Rolling 24h mean return
        AVG(log_return) OVER (
            ORDER BY hour
            ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
        ) AS mean_return_24h
    FROM returns
    WHERE log_return IS NOT NULL
)
SELECT
    -- Volatility statistics
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY realized_vol_24h) AS vol_median,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY realized_vol_24h) AS vol_p75,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY realized_vol_24h) AS vol_p90,
    AVG(realized_vol_24h) AS vol_mean,
    
    -- Jump detection (|return| > 2 std devs)
    SUM(CASE WHEN abs_log_return > 2 * STDDEV(log_return) OVER () THEN 1 ELSE 0 END)::FLOAT / COUNT(*) AS jump_rate,
    
    -- Trend detection (|mean_return_24h| > threshold)
    SUM(CASE WHEN ABS(mean_return_24h) > 0.01 THEN 1 ELSE 0 END)::FLOAT / COUNT(*) AS trend_rate,
    
    -- Mean revert detection (low vol + low trend)
    SUM(CASE 
        WHEN realized_vol_24h < PERCENTILE_CONT(0.33) WITHIN GROUP (ORDER BY realized_vol_24h) OVER ()
        AND ABS(mean_return_24h) < 0.005 
        THEN 1 ELSE 0 END)::FLOAT / COUNT(*) AS mean_revert_rate,
    
    -- Total hours
    COUNT(*) AS hours_observed
FROM rolling_stats
WHERE realized_vol_24h IS NOT NULL;

-- Also get time series for regime classification
-- SELECT
--     hour,
--     realized_vol_24h,
--     mean_return_24h,
--     abs_log_return,
--     CASE
--         WHEN abs_log_return > 2 * STDDEV(log_return) OVER () THEN 'jumpy'
--         WHEN ABS(mean_return_24h) > 0.01 THEN 'trend'
--         WHEN realized_vol_24h < PERCENTILE_CONT(0.33) WITHIN GROUP (ORDER BY realized_vol_24h) OVER () THEN 'mean_revert'
--         ELSE 'mid'
--     END AS regime
-- FROM rolling_stats
-- WHERE realized_vol_24h IS NOT NULL
-- ORDER BY hour DESC
-- LIMIT 1000;
