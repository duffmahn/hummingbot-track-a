-- Query 2: Gas Cost Distribution for Uniswap V3 Position Manager Operations
-- Purpose: Determine median/p90 gas costs to calibrate FEE_GATE

WITH position_manager_txs AS (
    SELECT
        t.hash,
        t.block_time,
        t.gas_used,
        t.gas_price,
        g.tx_fee_usd,
        -- Decode function selector to identify operation type
        CASE
            WHEN SUBSTRING(t.data, 1, 10) = '0x88316456' THEN 'mint'
            WHEN SUBSTRING(t.data, 1, 10) = '0x219f5d17' THEN 'increaseLiquidity'
            WHEN SUBSTRING(t.data, 1, 10) = '0x0c49ccbe' THEN 'decreaseLiquidity'
            WHEN SUBSTRING(t.data, 1, 10) = '0xfc6f7865' THEN 'collect'
            WHEN SUBSTRING(t.data, 1, 10) = '0x42966c68' THEN 'burn'
            ELSE 'other'
        END AS operation_type
    FROM ethereum.transactions t
    INNER JOIN gas.fees g ON g.tx_hash = t.hash
    WHERE t.to = 0xC36442b4a4522E871399CD717aBDD847Ab11FE88  -- Uniswap V3 Position Manager
        AND t.block_time >= NOW() - INTERVAL '90' DAY
        AND t.success = true
)
SELECT
    -- Overall gas statistics
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY tx_fee_usd) AS gas_median_usd,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY tx_fee_usd) AS gas_p75_usd,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY tx_fee_usd) AS gas_p90_usd,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY tx_fee_usd) AS gas_p95_usd,
    AVG(tx_fee_usd) AS gas_mean_usd,
    MAX(tx_fee_usd) AS gas_max_usd,
    
    -- Count by operation type
    COUNT(*) AS total_operations,
    SUM(CASE WHEN operation_type = 'mint' THEN 1 ELSE 0 END) AS mint_count,
    SUM(CASE WHEN operation_type = 'increaseLiquidity' THEN 1 ELSE 0 END) AS increase_count,
    SUM(CASE WHEN operation_type = 'decreaseLiquidity' THEN 1 ELSE 0 END) AS decrease_count,
    SUM(CASE WHEN operation_type = 'collect' THEN 1 ELSE 0 END) AS collect_count
FROM position_manager_txs;

-- Also get per-operation-type stats
-- SELECT
--     operation_type,
--     PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY tx_fee_usd) AS gas_median_usd,
--     PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY tx_fee_usd) AS gas_p90_usd,
--     COUNT(*) AS count
-- FROM position_manager_txs
-- GROUP BY operation_type
-- ORDER BY gas_median_usd DESC;
