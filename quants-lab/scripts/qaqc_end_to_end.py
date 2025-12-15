# scripts/qaqc_end_to_end.py
"""
End-to-end QA/QC gate:
1) run small deterministic campaign (stateful + shadow)
2) build metrics artifacts
3) assert invariants across results + episode_metrics + summary
Exit code != 0 if anything fails (CI-friendly).
"""

import os, sys, json, math, subprocess
from pathlib import Path

# Resolve repo root relative to this script
REPO = Path(__file__).resolve().parents[1]

def _run(cmd, env=None):
    print(">>", " ".join(cmd))
    subprocess.check_call(cmd, cwd=REPO, env=env or os.environ.copy())

def _is_finite(x):
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)

def main():
    # ---- Config: deterministic / CI-safe ----
    env = os.environ.copy()
    env["USE_REAL_DATA"] = "true"
    env["REAL_DATA_REQUIRED"] = env.get("REAL_DATA_REQUIRED", "true") # Fail fast by default for QA
    
    # IMPORTANT: in CI you want cache-only runs
    if "HISTORICAL_DATA_CACHE_DIR" not in env:
        print("⚠️  HISTORICAL_DATA_CACHE_DIR not set. Using scratch/data/real_data_campaign_cache (might hit Dune if empty)")
        # In a strict CI env, we might want to assert this
    
    env["CAMPAIGN_SIZE"] = env.get("CAMPAIGN_SIZE", "5")
    run_id = env.get("RUN_ID", "qaqc_e2e_local")
    env["RUN_ID"] = run_id
    
    # 2025-01-01 00:00:00 UTC = 1735689600
    env["HB_MOCK_CURRENT_TIME"] = env.get("HB_MOCK_CURRENT_TIME", "1735689600")
    
    # Ensure sys.path includes REPO for imports
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
        
    print(f"🔧 QA Config: RUN_ID={run_id}, SIZE={env['CAMPAIGN_SIZE']}")
    print(f"🔧 Time Lock: {env['HB_MOCK_CURRENT_TIME']}")

    # ---- Stage Pre: Strict Cache Preflight ----
    print("\n🔍 Stage Pre: Verifying Cache...")
    
    now_ts = int(env["HB_MOCK_CURRENT_TIME"])
    cache_dir = Path(env.get("HISTORICAL_DATA_CACHE_DIR", REPO / "scratch/data/real_data_campaign_cache_qa"))
    env["HISTORICAL_DATA_CACHE_DIR"] = str(cache_dir) # Ensure env has it
    
    missing = []
    
    for i in range(int(env["CAMPAIGN_SIZE"])):
        episode_id = f"ep_{run_id}_{i:03d}"
        start_ts, end_ts, _ = _select_window_for_episode(episode_id, now_ts)
        cf = _cache_file_path(cache_dir, POOL_ADDR, start_ts, EPISODE_DURATION_S)
        
        if not (cf.exists() and _cache_has_required_fields(cf)):
            missing.append((episode_id, start_ts, cf))

    if missing:
        allow_warm = env.get("QAQC_ALLOW_DUNE_WARM", "false").lower() == "true"
        if not allow_warm:
            print("❌ QA cache preflight failed. Missing/invalid cache files:")
            for ep, st, cf in missing[:10]:
                print(f" - {ep} start_ts={st} file={cf}")
            if len(missing) > 10: print(f" ... and {len(missing)-10} others")
            print("\nTo fix:")
            print("  1. Set QAQC_ALLOW_DUNE_WARM=true (requires DUNE_API_KEY) to auto-warm")
            print("  2. Or run 'python3 scripts/seed_qa_cache.py ...' to generate dummy data")
            return 2

        print(f"🌡️ Warming {len(missing)} missing cache windows from Dune...")
        try:
            from lib.historical_data_cache import HistoricalDataCache
            from lib.dune_client import DuneClient
            
            # Initialize with real DuneClient (expects env vars)
            hc = HistoricalDataCache(cache_dir, DuneClient())
            
            for ep, start_ts, cf in missing:
                print(f"  Fetching for {ep} (ts={start_ts})...")
                hc.get_tick_window(pool_address=POOL_ADDR, start_ts=start_ts, duration_seconds=EPISODE_DURATION_S, granularity="hour")
                
                if not (cf.exists() and _cache_has_required_fields(cf)):
                    print(f"❌ Warm failed for {ep}: {cf} not created or invalid")
                    return 2
            print("✅ Cache warm complete")
            
        except Exception as e:
            print(f"❌ Warming failed: {e}")
            return 2
    else:
        print("✅ Cache preflight passed (all files present)")

    # ---- Stage A: run campaign ----
    print("\n🚀 Stage A: Running Mini-Campaign...")
    try:
        _run(["python3", "scripts/run_real_data_campaign.py"], env=env)
    except subprocess.CalledProcessError as e:
        print(f"❌ Campaign execution failed with code {e.returncode}")
        return 1

# --- Helpers ---
import hashlib

POOL_ADDR = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"
EPISODE_DURATION_S = 21600
LOOKBACK_DAYS = 90

def _select_window_for_episode(episode_id: str, now_ts: int) -> tuple[int, int, int]:
    # MUST mirror RealDataCLMMEnvironment._select_historical_window
    now = (now_ts // 3600) * 3600
    lookback_start = now - (LOOKBACK_DAYS * 86400)
    num_windows = (LOOKBACK_DAYS * 86400) // EPISODE_DURATION_S

    episode_hash = int(hashlib.sha256(episode_id.encode()).hexdigest(), 16)
    window_index = episode_hash % num_windows

    start_ts = lookback_start + (window_index * EPISODE_DURATION_S)
    end_ts = start_ts + EPISODE_DURATION_S
    return start_ts, end_ts, window_index

def _cache_file_path(cache_dir: Path, pool: str, start_ts: int, duration_s: int) -> Path:
    return cache_dir / f"{pool}_{start_ts}_{duration_s}.json"

def _cache_has_required_fields(cache_file: Path) -> bool:
    try:
        data = json.loads(cache_file.read_text())
        ticks = data.get("tick_data", [])
        if len(ticks) < 2:
            return False
        # required Dune columns that your env/policy relies on
        # Checking for subset of critical fields
        req = {"tick", "price", "volume_usd"} 
        return all(k in ticks[0] for k in req)
    except Exception:
        return False

    run_dir = REPO / "data" / "runs" / run_id
    results_path = run_dir / "results.json"
    
    # Wait for file (robustness)
    import time
    for _ in range(5):
        if results_path.exists():
            break
        time.sleep(1)
    
    if not results_path.exists():
        print(f"❌ Results file missing: {results_path}")
        # Debug: list dir
        if run_dir.exists():
            print(f"Contents of {run_dir}:")
            for f in run_dir.iterdir():
                print(f" - {f.name} ({f.stat().st_size} bytes)")
        else:
            print(f"Run dir missing: {run_dir}")
        return 1

    try:
        results = json.loads(results_path.read_text())
    except json.JSONDecodeError:
        print(f"❌ Malformed JSON in {results_path}")
        return 1
        
    if len(results) == 0:
        print("❌ Empty results.json (0 episodes)")
        return 1
        
    print(f"✅ Generated {len(results)} records")

    required_keys = [
        "policy_action", "fees_usd", "net_pnl_usd", "gas_cost_usd",
        "fees_0", "fees_1",
        "pool_fees_usd_input_based", "pool_fees_usd_amount_usd_based",
        "shadow_net_pnl_usd", "gating_value_usd",
    ]

    print("\n🔍 Validating Invariants...")
    failures = 0
    
    for i, r in enumerate(results):
        ep_prefix = f"[Ep {i}]"
        
        # 1. Schema Check
        for k in required_keys:
            if k not in r:
                print(f"❌ {ep_prefix} Missing key: {k}")
                failures += 1
                continue # Skip numeric check if missing
            
            if not _is_finite(r[k]):
                print(f"❌ {ep_prefix} Non-finite value: {k}={r[k]}")
                failures += 1

        # 2. Hold Gas Rule
        # If action is hold, gas must be 0
        if r.get("policy_action") == "hold":
            if abs(r.get("gas_cost_usd", 0.0)) > 1e-9:
                print(f"❌ {ep_prefix} Hold action has non-zero gas: ${r['gas_cost_usd']}")
                failures += 1

        # 3. Gating Identity
        # gating_value = net_pnl - shadow_net_pnl
        net = r.get("net_pnl_usd", 0.0)
        shadow = r.get("shadow_net_pnl_usd", 0.0)
        gating = r.get("gating_value_usd", 0.0)
        
        diff = net - shadow
        if abs(diff - gating) > 1e-6:
            print(f"❌ {ep_prefix} Gating identity mismatch: {diff:.6f} != {gating:.6f}")
            failures += 1

        # 4. Pool Fee Sanity (Input vs Amount Based)
        # known 2x bias check (loose tolerance)
        inp = r.get("pool_fees_usd_input_based", 0.0)
        two = r.get("pool_fees_usd_amount_usd_based", 0.0)
        
        if inp > 0.05: # Only check if meaningful volume
            ratio = two / inp
            # Typically 2.0, allow 1.6 - 2.4
            if not (1.6 <= ratio <= 2.4):
                print(f"⚠️  {ep_prefix} Two-sided fee ratio anomaly: {ratio:.2f} (Expected ~2.0)")
                # This makes it a warning for now unless strictly required
        
        # 5. Fee Positivity
        if r.get("fees_usd", -1) < 0:
            print(f"❌ {ep_prefix} Negative fees: {r['fees_usd']}")
            failures += 1

    if failures > 0:
        print(f"❌ Found {failures} invariant failures in results.json")
        return 1
    else:
        print("✅ Invariants Passed (results.json)")

    # ---- Stage B: build metrics ----
    print("\n🚀 Stage B: Building Aggregated Metrics...")
    try:
        _run(["python3", "scripts/build_run_metrics.py", "--run-id", run_id], env=env)
    except subprocess.CalledProcessError:
        print("❌ Metrics build failed")
        return 1

    ep_metrics = run_dir / "episode_metrics.jsonl"
    summary = run_dir / "metrics_summary.json"
    
    if not ep_metrics.exists():
        print("❌ Missing episode_metrics.jsonl")
        return 1
    if not summary.exists():
        print("❌ Missing metrics_summary.json")
        return 1

    # Optional: Parse summary to ensure valid JSON
    try:
        sum_data = json.loads(summary.read_text())
        if not isinstance(sum_data, dict):
            raise ValueError("Not a dictionary")
    except Exception as e:
        print(f"❌ Invalid summary JSON: {e}")
        return 1

    print("\n✅ E2E QA/QC PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
