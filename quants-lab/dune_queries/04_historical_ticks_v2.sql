WITH hourly AS (
  SELECT
    date_trunc('hour', evt_block_time) AS snapshot_time,
    CAST(to_unixtime(date_trunc('hour', evt_block_time)) AS BIGINT) AS timestamp,
    AVG(tick) AS avg_tick,
    COUNT(*) AS swap_count,

    SUM(ABS(CAST(amount0 AS DOUBLE))) / POW(10, 6) AS volume_usdc,
    SUM(ABS(CAST(amount1 AS DOUBLE))) / POW(10, 18) AS volume_weth,

    SUM(GREATEST(CAST(amount0 AS DOUBLE), 0)) / POW(10, 6) AS amount0_in_usdc,
    SUM(GREATEST(CAST(amount1 AS DOUBLE), 0)) / POW(10, 18) AS amount1_in_weth
  FROM uniswap_v3_ethereum.uniswapv3pool_evt_swap
  WHERE contract_address = from_hex('88e6a0c2ddd26feeb64f039a2c41296fcb3f5640')
    AND evt_block_time >= from_unixtime({{start_timestamp}})
    AND evt_block_time < from_unixtime({{end_timestamp}})
  GROUP BY 1, 2
),
priced AS (
  SELECT
    *,
    (volume_usdc / NULLIF(volume_weth, 0)) AS weth_usd,
    0.0005 AS fee_rate,
    -- Calculate approximate volume USD using the WETH price
    (volume_usdc + (volume_weth * (volume_usdc / NULLIF(volume_weth, 0)))) AS volume_usd
  FROM hourly
  WHERE volume_weth > 0 AND volume_usdc > 0
)
SELECT
  timestamp,
  snapshot_time,
  CAST(FLOOR(avg_tick) AS INTEGER) AS tick,
  volume_usdc,
  volume_weth,
  volume_usd,
  swap_count,
  weth_usd,
  -- Calculate explicit fee components
  fee_rate * amount0_in_usdc AS fees_usdc,
  fee_rate * amount1_in_weth AS fees_weth,
  -- Calculate USD fees using the explicit components and that hour's price
  (fee_rate * amount0_in_usdc) + (fee_rate * amount1_in_weth) * weth_usd AS fees_usd,

  -- Validation 1: Input-Based Volume & Fees (Should match fees_usd approx 1:1)
  (amount0_in_usdc + amount1_in_weth * weth_usd) AS volume_usd_inputs,
  fee_rate * (amount0_in_usdc + amount1_in_weth * weth_usd) AS pool_fees_usd_from_inputs,

  -- Validation 2: Two-Sided (Double Counted) Volume & Fees (Should be approx 2x inputs)
  volume_usd AS volume_usd_two_sided,
  fee_rate * volume_usd AS pool_fees_usd_two_sided
FROM priced
ORDER BY snapshot_time;
