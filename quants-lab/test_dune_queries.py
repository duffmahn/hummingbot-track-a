
import os
import sys
from datetime import datetime
import time

# Ensure we can import from lib
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

# Load environment logic manually to ensure we catch recent .env.sh updates
def load_env_sh():
    # Try finding .env.sh in current or parent dirs
    search_paths = [".env.sh", "quants-lab/.env.sh", "../.env.sh", "scratch/quants-lab/.env.sh"]
    env_path = None
    for p in search_paths:
        if os.path.exists(p):
            env_path = p
            break
            
    if env_path:
        print(f"Loading env from: {env_path}")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                
                # Handle "export KEY=VAL"
                if line.startswith('export '):
                    line = line[7:]
                
                if '=' in line:
                    key, val = line.split('=', 1)
                    val = val.strip().strip('"').strip("'")
                    os.environ[key] = val
    else:
        print("⚠️  .env.sh not found!")

load_env_sh()

from dune_client import DuneClient

def test_queries():
    print("🔎 Scanning Dune Queries (Q1-Q15)...")
    print(f"API Key Present: {'Yes' if os.environ.get('DUNE_API_KEY') else 'No'}")
    print("=" * 60)

    client = DuneClient()
    
    # Test Context
    POOL = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640" # WETH-USDC V3 (Using V3 as proxy for generic queries)
    PAIR = "WETH-USDC"
    
    # Define probes
    probes = [
        ("Q1 Swaps (Universal)", lambda: client.get_swaps_for_pair("WETH-USDC", int(time.time()) - 3600*24, int(time.time()), POOL)),
        ("Q1 Liquidity Depth", lambda: client.get_liquidity_depth(POOL)),
        ("Q2 Dynamic Fee", lambda: client.get_dynamic_fee_analysis(POOL)),
        ("Q3 IL Tracker", lambda: client.get_impermanent_loss_tracker(POOL)),
        ("Q4 Gas Regime", lambda: client.get_gas_regime()),
        ("Q5 Liq Competition", lambda: client.get_liquidity_competition(POOL)),
        ("Q6 Arbitrage", lambda: client.get_arbitrage_opportunities(POOL)),
        ("Q7 Hook Analysis", lambda: client.get_hook_analysis()),
        ("Q8 MEV Risk", lambda: client.get_mev_risk(POOL)),
        ("Q9 Whale Sentiment", lambda: client.get_whale_sentiment(PAIR)),
        ("Q10 Migration", lambda: client.get_cross_dex_migration(POOL)),
        ("Q11 Fee Opt", lambda: client.get_fee_tier_optimization(POOL)),
        ("Q12 Pool Health", lambda: client.get_pool_health_score(POOL)),
        ("Q13 Yield Farming", lambda: client.get_yield_farming_opportunities()),
        ("Q14 Rebalance Signal", lambda: client.get_rebalance_hint(POOL)),
        ("Q15 Portfolio Dash", lambda: client.get_portfolio_dashboard("0x000...")) # Dummy wallet
    ]

    results = []
    
    for name, func in probes:
        print(f"Testing {name}...", end=" ", flush=True)
        try:
            # We don't want to actually wait for 15 queries sequentially if we can avoid it, 
            # but for a true test we must.
            # However, if API Key is missing, we fail fast.
            if not os.environ.get('DUNE_API_KEY'):
                print("❌ Skipped (No API Key)")
                results.append((name, "SKIPPED"))
                continue
                
            data = func()
            if data and len(data) > 0:
                print(f"✅ Data! ({len(data)} rows)")
                results.append((name, "OK"))
            else:
                print("⚠️  Empty")
                results.append((name, "EMPTY"))
        except Exception as e:
            print(f"❌ Error: {str(e)[:50]}...")
            results.append((name, "ERROR"))

    print("\nSummary:")
    for name, status in results:
        print(f"{name}: {status}")

if __name__ == "__main__":
    test_queries()
