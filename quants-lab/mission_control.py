import streamlit as st
import pandas as pd
import json
import os
import sys
from datetime import datetime, timedelta
import time
from pathlib import Path
import subprocess

# Add lib to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from uv4_experiments import UV4ExperimentStore
from dune_client import DuneClient

st.set_page_config(page_title="Quants Lab Mission Control", layout="wide", page_icon="🦅")

st.title("🦅 Quants Lab: Phase 5 Agent Mission Control")

# --- Helper Functions ---
def load_env_file(path_str):
    """Robustly load env vars from a file path."""
    path = Path(path_str)
    if not path.exists(): return False
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'): continue
            # Handle 'export VAR=VAL'
            if line.startswith('export '):
                line = line[7:].strip()
            if '=' in line:
                key, val = line.split('=', 1)
                val = val.strip().strip('"').strip("'")
                os.environ[key] = val
    return True

def first_row(obj):
    """Safely extract first row from list or return dict if already dict."""
    if isinstance(obj, list) and obj:
        return obj[0]
    if isinstance(obj, dict):
        return obj
    return None

# --- Sidebar: Configuration ---
st.sidebar.header("System Status")

# Load Env (Try multiple paths)
base_dir = Path(__file__).resolve().parent
env_paths = [
    base_dir / ".env.sh",                   # In quants-lab/
    base_dir.parent / ".env.sh",            # In scratch/
    base_dir.parent / "quants-lab" / ".env.sh"  # Explicit
]

env_loaded = False
for p in env_paths:
    if load_env_file(p):
        env_loaded = True
        break

api_key = os.getenv("DUNE_API_KEY", "Unknown")
masked_key = "Unknown"
if api_key != "Unknown":
    masked_key = api_key[:4] + "..." + api_key[-4:]
    st.sidebar.success(f"Dune API Key: `{masked_key}`")
else:
    st.sidebar.error("Dune API Key Missing")

st.sidebar.info("Agent Mode: **Autonomous Learning**")
if st.sidebar.button("🔄 Reload Dashboard"):
    st.rerun()

# --- Tabs ---
tab1, tab2, tab3, tab4 = st.tabs([
    "🧠 Agent Performance", 
    "📡 Dune Intel (Live)", 
    "🧪 Lab Experiments", 
    "📋 Next Run Proposal"
])

# --- Tab 1: Historical Runs ---
# --- Tab 1: Historical Runs ---
with tab1:
    st.header("🦅 V1 Realtime Intelligence")
    
    try:
        store = UV4ExperimentStore()
    except Exception as e:
        st.error(f"Error loading experiment store: {e}")
        store = None

    if store:
        # Load V1 Data
        df_v1 = store.to_dataframe(min_version="v1_realtime", intel_quality_whitelist=("all",))
        
        # Metrics Calculation
        total_runs = len(df_v1)
        good_runs = len(df_v1[df_v1['intel_quality'] == 'good'])
        stable_runs = len(df_v1[df_v1['regime_at_start'] == df_v1['regime_at_end']])
        
        # Determine Phase
        training_phase = "bootstrap" if good_runs < 30 else "live_tuning"
        phase_color = "orange" if training_phase == "bootstrap" else "green"

        # Top Row Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("V1 Runs", total_runs, help="Total runs tagged v1_realtime")
        m2.metric("Good Quality", good_runs, help="Runs with tradeable=True, Liquidity > 1M")
        m3.metric("Stable Regimes", stable_runs, help="Start Regime == End Regime")
        m4.markdown(f"**Phase**: :{phase_color}[{training_phase.upper()}]")
        
        if not df_v1.empty:
            # Type Conversion
            if 'timestamp' in df_v1.columns:
                df_v1['timestamp'] = pd.to_datetime(df_v1['timestamp'], errors='coerce')
            
            # --- Visualizations ---
            st.divider()
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("Performance (Reward V1)")
                # Filter out bad runs for chart
                chart_df = df_v1[df_v1['intel_quality'] == 'good'].set_index('timestamp').sort_index()
                if not chart_df.empty:
                     st.line_chart(chart_df[['reward_v1', 'reward_v0']])
                else:
                    st.info("No 'good' runs to chart yet.")
            
            with c2:
                st.subheader("Regime Distribution")
                if 'regime_at_start' in df_v1.columns:
                    regime_counts = df_v1['regime_at_start'].value_counts()
                    st.bar_chart(regime_counts)
            
            # --- Data Table ---
            st.subheader("Run Log (V1)")
            
            # Select columns to show
            cols_to_show = [
                'run_id', 'timestamp', 'intel_quality', 
                'regime_at_start', 'reward_v1', 'training_phase'
            ]
            # Add dynamic params
            param_cols = [c for c in df_v1.columns if c.startswith('param_')]
            final_cols = cols_to_show + param_cols
            final_cols = [c for c in final_cols if c in df_v1.columns]
            
            st.dataframe(
                df_v1[final_cols].sort_values(by="timestamp", ascending=False), 
                use_container_width=True
            )
            
            # --- Deep Dive Inspector ---
            st.divider()
            st.header("🔬 Execution Inspector")
            
            run_options = df_v1.sort_values(by="timestamp", ascending=False)['run_id'].tolist()
            
            if run_options:
                selected_run_id = st.selectbox("Select Run to Inspect", run_options)
                
                # Find the file path for this run
                run_row = df_v1[df_v1['run_id'] == selected_run_id].iloc[0]
                run_path = run_row['file_path']
                
                try:
                    with open(run_path, 'r') as f:
                        full_run_data = json.load(f)
                    
                    # Metrics / Logic
                    metrics = full_run_data.get('metrics', {})
                    actions = metrics.get('actions', [])
                    
                    # Columns for details
                    d1, d2 = st.columns(2)
                    with d1:
                        st.subheader("Configuration")
                        st.write(f"**Regime:** `{full_run_data.get('regime_at_start', 'unknown')}` → `{full_run_data.get('regime_at_end', 'unknown')}`")
                        st.write(f"**Quality:** `{full_run_data.get('intel_quality', 'unknown')}`")
                        
                        params = full_run_data.get('params_adjusted') or full_run_data.get('params_original')
                        if params:
                            st.json(params)
                        else:
                            st.warning("No configuration found")
                    
                    with d2:
                        st.subheader("Results")
                        st.metric("Reward V1", f"{full_run_data.get('reward', 0):.4f}")
                        st.metric("PnL (USD)", f"${metrics.get('total_pnl_usd', 0):.2f}")
                        
                        gas = metrics.get('gas_cost_usd', 0)
                        drift = metrics.get('inventory_drift', 0)
                        st.write(f"**Gas:** -${gas:.2f} | **Drift:** {drift*100:.1f}%")
                    
                    # Actions Table
                    st.subheader("📜 Action History")
                    if actions:
                        df_actions = pd.DataFrame(actions)
                        st.dataframe(
                            df_actions[["timestamp", "action", "details", "gas_cost"]],
                            use_container_width=True
                        )
                        
                    
            except Exception as e:
                st.error(f"Failed to load details for {selected_run_id}: {e}")

# --- Tab 2: Live Sensor Intel ---
with tab2:
    st.header("Real-Time Market Intelligence (Dune)")
    st.markdown("Fetching live data from Dune Analytics API...")
    
    if st.button("Refresh Intel", key="refresh_t2"):
        try:
            client = DuneClient()
            
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("🔥 Volatility & Gas (Q4)")
                gas_data = client.get_gas_regime()
                gas_row = first_row(gas_data)
                if gas_row:
                    st.json(gas_row)
                else:
                    st.write("No Gas Data")
                
                st.subheader("☠️ Toxic Flow / LVR (Q16)")
                toxic_data = client.get_toxic_flow_index("0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640")
                toxic_row = first_row(toxic_data)
                if toxic_row:
                    t_pct = toxic_row.get('toxic_percentage', 0)
                    st.metric("Toxic Flow %", f"{t_pct}%")
                    st.json(toxic_row)
                else:
                    st.write("No Toxic Flow Data")

            with c2:
                st.subheader("⚡ JIT Liquidity Risk (Q17)")
                jit_data = client.get_jit_liquidity_monitor("0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640")
                jit_row = first_row(jit_data)
                if jit_row:
                    st.json(jit_row)
                else:
                    st.write("No JIT Data")
                
                st.subheader("🧬 Dynamic Config (Q25)")
                conf_data = client.get_hummingbot_config()
                conf_row = first_row(conf_data)
                if conf_row:
                    st.code(conf_row.get('config_yaml', 'N/A'), language='yaml')
                else:
                    st.write("No Config Generated")
                    
        except Exception as e:
            st.error(f"Connection Error: {e}")

# --- Tab 3: Quants Lab Experiments ---
with tab3:
    st.header("🧪 Hummingbot Quants Lab Experiments")
    st.markdown("Advanced signals for backtesting, strategy optimization, and risk management.")
    
    if st.button("🧬 Run Quants Lab Analysis", key="run_ql"):
        try:
            client = DuneClient()
            
            # --- Row 1: Strategy & Backtest ---
            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Strategy Attribution (Q22)")
                attr = client.get_strategy_attribution()
                latest = first_row(attr)
                if latest:
                    eff = latest.get('rolling_24h_effectiveness', 0)
                    st.metric("Strategy Effectiveness", f"{eff:.1f}/100")
                    st.write(f"**Recommendation:** {latest.get('strategy_recommendation', 'N/A')}")
                    st.json(latest)
                else:
                    st.warning("No Data (Q22)")

            with c2:
                st.subheader("Backtesting Data (Q20)")
                
                # Dynamic Date Inputs
                st.caption("Select Date Range for Backtest Simulation")
                bd1, bd2 = st.columns(2)
                with bd1:
                    start_d = st.date_input("Start Date", value=datetime.today() - timedelta(days=7))
                with bd2:
                    end_d = st.date_input("End Date", value=datetime.today())
                
                # Format dates for Dune (YYYY-MM-DD 00:00:00)
                s_str = f"{start_d} 00:00:00"
                e_str = f"{end_d} 00:00:00"
                
                backtest = client.get_backtesting_data(start_date=s_str, end_date=e_str)
                if backtest:
                    df_bt = pd.DataFrame(backtest)
                    st.dataframe(df_bt.head(5), use_container_width=True)
                    st.caption(f"Loaded {len(df_bt)} intervals for simulation.")
                else:
                    st.warning("No Data (Q20)")

            # --- Row 2: Execution & Impact ---
            st.divider()
            c3, c4 = st.columns(2)
            with c3:
                st.subheader("Order Impact (Q21)")
                impact = client.get_order_impact()
                if impact:
                    df_imp = pd.DataFrame(impact)
                    cols = [c for c in ['liquidity_tier', 'recommended_max_order_size', 'sizing_adjustment'] if c in df_imp.columns]
                    st.dataframe(df_imp[cols], hide_index=True)
                else:
                    st.warning("No Data (Q21)")
            
            with c4:
                st.subheader("Execution Quality (Q23)")
                qual = client.get_execution_quality()
                best = first_row(qual)
                if best:
                    score = best.get('composite_execution_quality', 0)
                    st.metric("Execution Score", f"{score:.1f}")
                    st.write(f"**Timing:** {best.get('execution_recommendation', 'N/A')}")
                else:
                    st.warning("No Data (Q23)")

            # --- Row 3: Allocation ---
            st.divider()
            st.subheader("Capital Allocation (Q24)")
            alloc = client.get_portfolio_allocation()
            if alloc:
                df_alloc = pd.DataFrame(alloc)
                # Pie Chart
                if 'normalized_allocation_weight' in df_alloc.columns:
                    st.bar_chart(df_alloc.set_index('pool_name')['normalized_allocation_weight'])
                st.dataframe(df_alloc)
            else:
                st.warning("No Data (Q24)")
                
        except Exception as e:
            st.error(f"Analysis Error: {e}")

# --- Tab 4: Proposal Viewer ---
with tab4:
    st.header("Next Run Proposal (Phase 5 Agent)")
    
    # Locate proposal file: ../data/uniswap_v4_param_proposals.json relative to this file
    proposal_path = Path(__file__).resolve().parent.parent / "data" / "uniswap_v4_param_proposals.json"
    
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(f"Reading from: `{proposal_path}`")
    with c2:
        if st.button("🚀 Execute Proposal"):
            st.info("Executing proposal script...")
            # Run the executor
            # Assumes we are in scratch/ or have correct relatives
            # We will try to run from scratch root
            cwd = Path(__file__).resolve().parent.parent # scratch/
            cmd = ["python3", "hummingbot/scripts/execute_next_proposal.py"]
            try:
                result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
                if result.returncode == 0:
                    st.success("Execution Success! Check Tab 1 for new run.")
                    st.code(result.stdout)
                else:
                    st.error("Execution Failed")
                    st.code(result.stderr)
            except Exception as e:
                st.error(f"Subprocess Error: {e}")

    if proposal_path.exists():
        try:
            with open(proposal_path) as f:
                proposal = json.load(f)

            st.subheader("Summary")
            st.write(f"**Generated at:** `{proposal.get('generated_at')}`")
            st.write(f"**Detected Regime:** `{proposal.get('current_regime', 'unknown')}`")

            nxt = proposal.get('next_run_proposal', {})
            if nxt:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.subheader("Proposed Parameters")
                    st.json(nxt.get('params', {}))
                    st.write(f"**Confidence:** `{nxt.get('confidence')}`")
                    st.write(f"**Notes:** {nxt.get('notes', '')}")
                
                with col_b:
                    st.subheader("Intel Snapshot (Used for Decision)")
                    st.json(nxt.get('intel_snapshot', {}))
            else:
                st.warning("Proposal file exists but contains no 'next_run_proposal'.")
                
        except Exception as e:
            st.error(f"Error reading proposal file: {e}")
    else:
        st.warning("No proposal file found. Run `phase5_learning_agent.py` to generate one.")

st.sidebar.markdown("---")
st.sidebar.markdown("Running on **Hummingbot Quants Lab**")
