#!/usr/bin/env python3
"""
Test Market Intelligence with Hummingbot API
"""

import os
os.environ['INTEL_DATA_SOURCE'] = 'hbot'
os.environ['HBOT_API_USERNAME'] = 'admin'
os.environ['HBOT_API_PASSWORD'] = 'admin'

from market_intel import MarketIntelligence

print("Testing Market Intelligence with Hummingbot API...")
print("=" * 60)

intel = MarketIntelligence()

print("\nFetching pool health...")
health = intel.get_pool_health(
    '0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640',
    'WETH-USDC',
    1
)

print('\n=== MARKET INTELLIGENCE RESULT ===')
print(f'Data Source: {health.get("data_source", "unknown")}')
print(f'Volatility: {health.get("volatility", 0):.2%}')
print(f'Liquidity: ${health.get("avg_liquidity", 0):,.0f}')
print(f'Volume: {health.get("volume", 0):.2f}')
print(f'TVL: ${health.get("tvl", 0):,.0f}')
print(f'Regime: {health.get("market_regime", "unknown")}')
print(f'Tradeable: {health.get("tradeable", False)}')
print(f'Reason: {health.get("reason", "unknown")}')

if health.get('tradeable'):
    print('\n✅ READY TO RUN EXPERIMENTS WITH REAL DATA!')
else:
    print(f'\n⚠️  Not tradeable: {health.get("reason")}')
