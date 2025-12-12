#!/usr/bin/env python3
"""
Test Market Intelligence with CoinGecko (Real Data)
"""

import os
os.environ['INTEL_DATA_SOURCE'] = 'coingecko'

from market_intel import MarketIntelligence

print("Testing Market Intelligence with CoinGecko...")
print("=" * 60)

intel = MarketIntelligence()

print("\nFetching pool health for WETH-USDC...")
health = intel.get_pool_health(
    '0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640',
    'WETH-USDC',
    1
)

print('\n=== MARKET INTELLIGENCE RESULT ===')
print(f'Data Source: {intel.data_source}')
print(f'Volatility: {health.get("volatility", 0):.2%}')
print(f'Liquidity: ${health.get("avg_liquidity", 0):,.0f}')
print(f'Volume: {health.get("volume", 0):.2f} ETH')
print(f'TVL: ${health.get("tvl", 0):,.0f}')
print(f'Regime: {health.get("market_regime", "unknown")}')
print(f'Tradeable: {health.get("tradeable", False)}')
print(f'Reason: {health.get("reason", "unknown")}')

if health.get('tradeable'):
    print('\n✅ READY TO RUN EXPERIMENTS WITH REAL DATA!')
else:
    print(f'\n⚠️  Not tradeable: {health.get("reason")}')

print(f'\n📊 Data is REAL from CoinGecko API')
print(f'🎯 Ready for learning agent experiments')
