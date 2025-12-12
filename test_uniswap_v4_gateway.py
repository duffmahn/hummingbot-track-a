#!/usr/bin/env python3
"""
Test script for Uniswap V4 Gateway integration
"""

import requests
import json

GATEWAY_URL = "http://localhost:15888"

def test_connectors():
    """Test that uniswap_v4 is listed in connectors"""
    print("=" * 60)
    print("TEST 1: List Connectors")
    print("=" * 60)
    
    response = requests.get(f"{GATEWAY_URL}/config/connectors")
    data = response.json()
    
    uniswap_v4 = next((c for c in data['connectors'] if c['name'] == 'uniswap_v4'), None)
    
    if uniswap_v4:
        print("✅ uniswap_v4 connector found!")
        print(json.dumps(uniswap_v4, indent=2))
        return True
    else:
        print("❌ uniswap_v4 connector NOT found")
        return False

def test_health():
    """Test health endpoint"""
    print("\n" + "=" * 60)
    print("TEST 2: Health Check")
    print("=" * 60)
    
    response = requests.get(f"{GATEWAY_URL}/connectors/uniswap_v4/amm/health")
    data = response.json()
    
    print(json.dumps(data, indent=2))
    
    if data.get('status') == 'ok':
        print("✅ Health check passed!")
        return True
    else:
        print("❌ Health check failed")
        return False

def test_tokens():
    """Test tokens endpoint"""
    print("\n" + "=" * 60)
    print("TEST 3: List Tokens")
    print("=" * 60)
    
    response = requests.get(f"{GATEWAY_URL}/connectors/uniswap_v4/amm/tokens")
    data = response.json()
    
    tokens = data.get('tokens', [])
    print(f"Found {len(tokens)} tokens:")
    for token in tokens:
        print(f"  - {token['symbol']}: {token['address']}")
    
    if len(tokens) > 0:
        print("✅ Tokens loaded successfully!")
        return True
    else:
        print("❌ No tokens found")
        return False

def test_pools():
    """Test pools endpoint"""
    print("\n" + "=" * 60)
    print("TEST 4: Find Pools (WETH-USDC)")
    print("=" * 60)
    
    response = requests.get(
        f"{GATEWAY_URL}/connectors/uniswap_v4/amm/pools",
        params={"tokenIn": "WETH", "tokenOut": "USDC"}
    )
    data = response.json()
    
    pools = data.get('pools', [])
    print(f"Found {len(pools)} pools:")
    for pool in pools:
        print(f"  - Pool ID: {pool['id']}")
        print(f"    Fee: {pool['fee']} ({pool['fee']/10000}%)")
        print(f"    Liquidity: {pool['liquidity']}")
    
    if len(pools) > 0:
        print("✅ Pools found successfully!")
        return True
    else:
        print("❌ No pools found")
        return False

def test_quote():
    """Test quote endpoint"""
    print("\n" + "=" * 60)
    print("TEST 5: Get Quote (0.001 WETH -> USDC)")
    print("=" * 60)
    
    # 0.001 WETH = 1000000000000000 wei
    payload = {
        "tokenIn": "WETH",
        "tokenOut": "USDC",
        "amountIn": "1000000000000000",
        "exactIn": True,
        "slippageBps": 100,
        "chainId": 11155111
    }
    
    response = requests.post(
        f"{GATEWAY_URL}/connectors/uniswap_v4/amm/quote",
        json=payload
    )
    data = response.json()
    
    if data.get('success'):
        print(f"✅ Quote successful!")
        print(f"  Amount In: {int(data['amountIn']) / 1e18} WETH")
        print(f"  Amount Out: {int(data['amountOut']) / 1e6} USDC")
        print(f"  Price: {data['price']}")
        print(f"  Gas Estimate: {data['gasEstimate']}")
        return True
    else:
        print(f"❌ Quote failed: {data}")
        return False

def main():
    print("\n🚀 Uniswap V4 Gateway Integration Test\n")
    
    results = []
    
    # Run all tests
    results.append(("Connectors", test_connectors()))
    results.append(("Health", test_health()))
    results.append(("Tokens", test_tokens()))
    results.append(("Pools", test_pools()))
    results.append(("Quote", test_quote()))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:20s} {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Gateway is ready for Hummingbot integration!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    exit(main())
