# Dune Analytics Queries - Complete Catalog

## Overview
You have **25 Dune Analytics queries** integrated for real-time on-chain data analysis. These queries provide comprehensive market intelligence for Uniswap V3/V4 liquidity provision and trading.

## Query Categories

### 📊 Core Market Data (Q1-Q3)
**Q1: Liquidity Depth Heatmap** (`DUNE_Q1_LIQ_DEPTH`)
- **Data:** Tick-by-tick liquidity distribution
- **Use:** Identify optimal price ranges for LP positions
- **Method:** `client.get_liquidity_depth(pool_address)`

**Q2: Dynamic Fee & Volume Analysis** (`DUNE_Q2_DYNAMIC_FEE`)
- **Data:** Fee tier performance, volume patterns
- **Use:** Choose optimal fee tier (0.05%, 0.30%, 1.00%)
- **Method:** `client.get_dynamic_fee_analysis(pool_address)`

**Q3: Impermanent Loss Tracker** (`DUNE_Q3_IL_TRACKER`)
- **Data:** Real-time IL calculations, historical IL trends
- **Use:** Risk assessment for LP positions
- **Method:** `client.get_impermanent_loss_tracker(pool_address)`

### ⛽ Gas & Execution (Q4)
**Q4: Gas Optimization Signal** (`DUNE_Q4_GAS`)
- **Data:** Current gas prices, optimal execution times
- **Use:** Time trades to minimize gas costs
- **Method:** `client.get_gas_regime()`

### 🏊 Liquidity Intelligence (Q5, Q10-Q12)
**Q5: Liquidity Competition Analysis** (`DUNE_Q5_LIQ_COMP`)
- **Data:** LP concentration, competitive positioning
- **Use:** Identify crowded vs. underserved price ranges
- **Method:** `client.get_liquidity_competition(pool_address)`

**Q10: Cross-DEX Migration Tracker** (`DUNE_Q10_MIGRATION`)
- **Data:** Liquidity flows between DEXs
- **Use:** Detect capital rotation trends
- **Method:** `client.get_cross_dex_migration(pool_address)`

**Q11: Fee Tier Optimization** (`DUNE_Q11_FEE_OPT`)
- **Data:** Fee tier profitability comparison
- **Use:** Maximize fee revenue
- **Method:** `client.get_fee_tier_optimization(pool_address)`

**Q12: Pool Health Score** (`DUNE_Q12_POOL_HEALTH`)
- **Data:** Composite health metric (volume, liquidity, volatility)
- **Use:** Pool selection and risk monitoring
- **Method:** `client.get_pool_health_score(pool_address)`

### 💰 Trading Opportunities (Q6, Q13-Q14)
**Q6: Arbitrage Opportunity Detection** (`DUNE_Q6_ARBITRAGE`)
- **Data:** Cross-pool price discrepancies
- **Use:** Identify arb opportunities
- **Method:** `client.get_arbitrage_opportunities(pool_address)`

**Q13: Yield Farming Scanner** (`DUNE_Q13_YIELD`)
- **Data:** Real-time APR/APY across pools
- **Use:** Capital allocation optimization
- **Method:** `client.get_yield_farming_opportunities()`

**Q14: Automated Rebalancing Signal** (`DUNE_Q14_REBALANCE`)
- **Data:** Position drift alerts, optimal rebalance timing
- **Use:** Minimize out-of-range time
- **Method:** `client.get_rebalance_hint(pool_address)`

### 🎣 Uniswap V4 Hooks (Q7, Q19)
**Q7: Hook Analysis** (`DUNE_Q7_HOOK_ANALYSIS`)
- **Data:** Hook usage patterns, performance metrics
- **Use:** Evaluate hook effectiveness
- **Method:** `client.get_hook_analysis(hook_address)`

**Q19: Hook Gas Efficiency** (`DUNE_Q19_HOOK_GAS`)
- **Data:** Gas costs per hook, performance benchmarks
- **Use:** Optimize hook selection
- **Method:** `client.get_hook_gas_performance(hook_address)`

### 🛡️ Risk Management (Q8, Q16-Q17)
**Q8: MEV Sandwich Protection** (`DUNE_Q8_MEV`)
- **Data:** Sandwich attack frequency, victim pools
- **Use:** Avoid toxic pools, set slippage protection
- **Method:** `client.get_mev_risk(pool_address)`

**Q16: Toxic Flow Index (LVR Estimator)** (`DUNE_Q16_TOXIC_FLOW`)
- **Data:** Loss-versus-rebalancing metrics
- **Use:** Quantify adverse selection risk
- **Method:** `client.get_toxic_flow_index(pool_address)`

**Q17: JIT Liquidity Monitor** (`DUNE_Q17_JIT_MONITOR`)
- **Data:** Just-in-time liquidity attacks
- **Use:** Detect and avoid JIT-prone pools
- **Method:** `client.get_jit_liquidity_monitor(pool_address)`

### 🐋 Market Sentiment (Q9, Q18)
**Q9: Institutional Wallet Tracking** (`DUNE_Q9_WHALES_TRADES`)
- **Data:** Large wallet activity, whale trades
- **Use:** Follow smart money
- **Method:** `client.get_whale_sentiment(pair)`

**Q18: Correlation Matrix** (`DUNE_Q18_CORRELATION`)
- **Data:** Asset correlation analysis
- **Use:** Portfolio diversification
- **Method:** `client.get_correlation_matrix(pool_address)`

### 📈 Portfolio Management (Q15, Q20-Q25)
**Q15: Portfolio Dashboard** (`DUNE_Q15_DASHBOARD`)
- **Data:** Wallet-level P&L, position summary
- **Use:** Track overall performance
- **Method:** `client.get_portfolio_dashboard(wallet_address)`

**Q20: Backtesting Data Pipeline** (`DUNE_Q20_BACKTEST`)
- **Data:** Historical tick data, swap events
- **Use:** Strategy backtesting
- **Method:** `client.get_backtesting_data(start_date, end_date)`

**Q21: Order Impact Estimation** (`DUNE_Q21_ORDER_IMPACT`)
- **Data:** Price impact predictions
- **Use:** Optimize order sizing
- **Method:** `client.get_order_impact()`

**Q22: Strategy Attribution** (`DUNE_Q22_ATTRIBUTION`)
- **Data:** Performance breakdown by strategy
- **Use:** Identify winning strategies
- **Method:** `client.get_strategy_attribution()`

**Q23: Execution Quality Monitor** (`DUNE_Q23_EXECUTION`)
- **Data:** Slippage, fill rates, execution metrics
- **Use:** Improve trade execution
- **Method:** `client.get_execution_quality()`

**Q24: Portfolio Rebalancing Optimizer** (`DUNE_Q24_ALLOCATION`)
- **Data:** Optimal capital allocation
- **Use:** Multi-pool portfolio management
- **Method:** `client.get_portfolio_allocation()`

**Q25: Dynamic Hummingbot Config Generator** (`DUNE_Q25_CONFIG_GEN`)
- **Data:** Optimized bot parameters
- **Use:** Auto-configure Hummingbot strategies
- **Method:** `client.get_hummingbot_config()`

## Setup Instructions

### 1. Get Dune API Key
```bash
# Sign up at https://dune.com
# Get API key from https://dune.com/settings/api
export DUNE_API_KEY="your_key_here"
```

### 2. Configure Query IDs
Set environment variables for each query you want to use:
```bash
export DUNE_Q1_LIQ_DEPTH=6321818
export DUNE_Q2_DYNAMIC_FEE=6321824
export DUNE_Q3_IL_TRACKER=6321829
export DUNE_Q4_GAS=6321836
export DUNE_Q5_LIQ_COMP=6321842
export DUNE_Q6_ARBITRAGE=6321846
export DUNE_Q7_HOOK_ANALYSIS=6321849
export DUNE_Q8_MEV=6321856
export DUNE_Q9_WHALES_TRADES=6321861
export DUNE_Q10_MIGRATION=6321866
export DUNE_Q11_FEE_OPT=6321869
export DUNE_Q12_POOL_HEALTH=6321874
export DUNE_Q13_YIELD=6321882
export DUNE_Q14_REBALANCE=6321886
export DUNE_Q15_DASHBOARD=6321891
export DUNE_Q16_TOXIC_FLOW=6321899
export DUNE_Q17_JIT_MONITOR=6321924
export DUNE_Q18_CORRELATION=6321931
export DUNE_Q19_HOOK_GAS=6321949
export DUNE_Q20_BACKTEST=TBD
export DUNE_Q21_ORDER_IMPACT=TBD
export DUNE_Q22_ATTRIBUTION=TBD
export DUNE_Q23_EXECUTION=TBD
export DUNE_Q24_ALLOCATION=TBD
export DUNE_Q25_CONFIG_GEN=TBD
```

### 3. Test Queries
```bash
cd /home/a/.gemini/antigravity/scratch/quants-lab
python3 test_dune_queries.py
```

## Integration with Track A

The Dune client is already integrated into `MarketIntelligence`:

```python
from lib.market_intel import MarketIntelligence

intel = MarketIntelligence()

# Get pool health
health = intel.get_pool_health("0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640")

# Get regime classification
regime = intel.classify_regime(
    pair="WETH-USDC",
    pool_address="0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"
)
```

## Data You Can Get

### Real-Time Metrics
- ✅ Liquidity distribution (tick-level)
- ✅ Swap volumes and prices
- ✅ Fee revenue by tier
- ✅ Gas prices and optimal execution windows
- ✅ Impermanent loss calculations
- ✅ MEV attack frequency
- ✅ Whale wallet activity

### Historical Analysis
- ✅ Price history
- ✅ Volume trends
- ✅ Liquidity migrations
- ✅ Strategy performance attribution
- ✅ Backtesting datasets

### Predictive Signals
- ✅ Rebalancing recommendations
- ✅ Arbitrage opportunities
- ✅ Optimal fee tier selection
- ✅ Portfolio allocation suggestions
- ✅ Dynamic bot configuration

## Query Status

**Configured (Q1-Q19):** 19 queries with IDs
**Pending (Q20-Q25):** 6 queries need Dune query creation

## Next Steps

1. **Create missing queries (Q20-Q25)** in Dune UI
2. **Test configured queries** with real API key
3. **Integrate into agent** decision-making
4. **Monitor query costs** (Dune API has rate limits)

## Cost Considerations

- **Free tier:** 25 queries/month
- **Hobbyist:** $39/month, 1000 queries/month
- **Pro:** $399/month, unlimited queries

For production use with Track A, recommend **Hobbyist tier** minimum.
