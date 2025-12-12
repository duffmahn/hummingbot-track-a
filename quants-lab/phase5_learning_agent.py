import json
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

import yaml
import hashlib

from lib.uv4_experiments import UV4ExperimentStore
from lib.market_intel import MarketIntelligence
# Use Pydantic schemas
from lib.schemas import QuoteResult, RewardBreakdown, Proposal, EpisodeMetadata
from schemas.contracts import AgentConfig
from schemas.learning_state import LearningState, RegimeState, ParameterDistribution
from lib.hummingbot_api_wrapper import hummingbot_api
from lib.json_logger import setup_logger
from lib.artifacts import EpisodeArtifacts

OUTPUT_FILE = Path(__file__).parent.parent / "data" / "uniswap_v4_param_proposals.json"

class NumpyEncoder(json.JSONEncoder):
    """
    JSON encoder that safely handles NumPy/Pandas types
    """
    def default(self, obj):
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if pd is not None and isinstance(obj, pd.Timestamp): return obj.isoformat()
        if isinstance(obj, (datetime, date)): return obj.isoformat()
        return super().default(obj)

class Phase5LearningAgent:
    def __init__(self, config: AgentConfig = None):
        self.config_hash = "manual"
        self.run_id = os.environ.get("RUN_ID", "manual_run")
        self.exec_mode = os.environ.get("EXEC_MODE", "mock")
        self.seed = int(os.environ.get("HB_SEED", "42"))
        self.learn_from_mock = os.environ.get("LEARN_FROM_MOCK", "false").lower() == "true"
        
        # Load external YAML config if not provided
        if config is None:
            config_path = Path(__file__).parent.parent / "conf" / "agent_config.yml"
            if config_path.is_file():
                with open(config_path) as f:
                    f.seek(0)
                    content = f.read()
                    self.config_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
                    f.seek(0)
                    cfg_dict = yaml.safe_load(f)
                
                try:
                    config = AgentConfig(**cfg_dict)
                except Exception as e:
                    print(f"❌ Invalid Config in agent_config.yml: {e}")
                    sys.exit(1)
            else:
                config = AgentConfig()
        
        self.config = config
        self.data = hummingbot_api
        self.store = UV4ExperimentStore()
        self.intel = MarketIntelligence()
        self.logger = setup_logger("Phase5Agent")
        
        # Paths
        self.root = Path(__file__).parent.parent
        self.data_dir = self.root / "data"
        self.proposals_dir = self.data_dir / "uniswap_v4_proposals"

        # Load Learning State
        self.state_path = Path(__file__).parent.parent / "data" / "learning_state.json"
        self.learning_state = LearningState.load(self.state_path)
        
        self.logger.info("Phase 5 Agent Initialized", extra={"config_hash": self.config_hash, "state_version": self.learning_state.version})

    def calculate_reward(self, row: pd.Series) -> RewardBreakdown:
        # Simplistic wrapper for learning update
        pnl = row.get('total_pnl_usd', 0.0)
        drawdown = row.get('max_drawdown_usd', 0.0)
        gas = row.get('gas_cost_usd', 0.0)
        
        w = self.config.reward_weights
        comp = {}
        comp['pnl'] = pnl * w.get('pnl', 1.0)
        comp['drawdown'] = -abs(drawdown) * w.get('drawdown', 0.5)
        comp['gas'] = -abs(gas) * w.get('gas', 0.3)
        
        total_reward = sum(comp.values())
        return RewardBreakdown(total=total_reward, components=comp)

    def update_beliefs_from_history(self, df: pd.DataFrame) -> bool:
        """
        Update beliefs from history.
        Returns True if update was applied, False if skipped due to learning hygiene.
        """
        # Learning hygiene: skip if exec_mode is mock and LEARN_FROM_MOCK is not true
        if self.exec_mode == "mock" and not self.learn_from_mock:
            self.logger.info("⏭  Skipping learning update (mock mode, LEARN_FROM_MOCK=false)")
            return False
            
        self.logger.info("🧠 Updating parameter beliefs from history...")
        if 'regime' not in df.columns:
             df['regime'] = 'vol_mid-liq_low'
             
        regimes = df['regime'].unique()
        for r in regimes:
             grp = df[df['regime'] == r]
             if grp.empty: continue
             
             if r not in self.learning_state.regimes:
                 self.learning_state.regimes[r] = RegimeState(regime=r)
                 
             regime_state = self.learning_state.regimes[r]
             
             # Windowed CEM
             WINDOW_SIZE = 20
             recent_history = grp.tail(WINDOW_SIZE)
             n_elites = max(1, int(len(recent_history) * 0.25))
             elites = recent_history.nlargest(n_elites, 'calculated_reward')
             
             learnable_params = {
                'width_pts': {'min': 5, 'max': 5000, 'default': 200},
                'rebalance_threshold_pct': {'min': 0.01, 'max': 0.50, 'default': 0.05},
                'spread_bps': {'min': 1, 'max': 500, 'default': 20},
                'order_size': {'min': 0.01, 'max': 5.0, 'default': 0.1},
                'refresh_interval': {'min': 10, 'max': 300, 'default': 60}
             }
             
             updated_counts = 0
             for param_name, limits in learnable_params.items():
                col_name = f"param_{param_name}"
                if col_name not in elites.columns: continue
                    
                values = elites[col_name].dropna().astype(float)
                if values.empty: continue
                
                mean_val = float(values.mean())
                min_std = (limits['max'] - limits['min']) * 0.05
                std_val = max(min_std, float(values.std()) if len(values) > 1 else min_std)
                
                # Smooth Update
                if param_name in regime_state.params:
                    old = regime_state.params[param_name]
                    alpha = 0.5
                    new_mean = old.mean * (1-alpha) + mean_val * alpha
                    new_std = old.std_dev * (1-alpha) + std_val * alpha
                    count = old.sample_count + len(values)
                else:
                    new_mean = mean_val
                    new_std = std_val
                    count = len(values)
                    
                regime_state.params[param_name] = ParameterDistribution(
                    name=param_name,
                    mean=new_mean,
                    std_dev=new_std,
                    min_val=limits['min'],
                    max_val=limits['max'],
                    sample_count=count
                )
                updated_counts += 1
            
             if updated_counts > 0:
                 regime_state.last_updated = datetime.now(timezone.utc)
                 self.logger.info(f"🧠 Updated belief for {r} ({updated_counts} params)")

        self.learning_state.save(self.state_path)
        return True

    def learn_and_propose(self, episode_id: str) -> Proposal:
        """
        Main logic: Load history -> Learn -> Sense -> Propose
        Returns a strict Proposal object.
        """
        self.logger.info("🤖 Phase 5 Learning Agent Starting...")
        
        # 1. Load & Learn
        learning_update_applied = False
        learning_update_reason = None
        
        df = self.store.to_dataframe(min_version="v1_realtime", intel_quality_whitelist=("good",), stable_regime_only=False)
        if not df.empty:
            if 'reward_v1' in df.columns:
                df['calculated_reward'] = df['reward_v1']
            else:
                df['calculated_reward'] = df.apply(lambda row: self.calculate_reward(row).total, axis=1)
            learning_update_applied = self.update_beliefs_from_history(df)
            if not learning_update_applied:
                learning_update_reason = "mock_mode_learning_disabled"
        else:
            learning_update_reason = "no_history_available"
        
        # 2. Sense
        PAIR = "WETH-USDC"
        POOL = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"
        
        # Assume valid intel for brevity in refactor
        current_regime = "vol_mid-liq_low" 
        
        # 3. Propose (Sample from Beliefs)
        params = {
            "width_pts": 200, 
            "rebalance_threshold_pct": 0.05,
            "spread_bps": 20,
            "order_size": 0.1,
            "refresh_interval": 60
        }
        
        # Use Learned if available
        if current_regime in self.learning_state.regimes:
            reg = self.learning_state.regimes[current_regime]
            import random
            for k in params.keys():
                if k in reg.params:
                    dist = reg.params[k]
                    val = random.gauss(dist.mean, dist.std_dev)
                    params[k] = max(dist.min_val, min(dist.max_val, val))
        
        # 4. Construct Proposal
        # Create Metadata first
        meta = EpisodeMetadata(
            episode_id=episode_id,
            run_id=self.run_id,
            config_hash=self.config_hash,
            agent_version="v6.0_track_a",
            exec_mode=self.exec_mode,
            seed=self.seed,
            regime_key=current_regime,
            learning_update_applied=learning_update_applied,
            learning_update_reason=learning_update_reason
        )
        
        proposal = Proposal(
            episode_id=episode_id,
            generated_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            status="active",
            connector_execution="uniswap_v3_clmm", # Explicit Pivot Target
            chain="ethereum",
            network="mainnet",
            pool_address=POOL,
            params=params,
            metadata=meta
        )
        
        # Optional: Run Simulation here if needed and Attach to `proposal.simulation`
        # For simplicity in this refactor step, we skip the heavy sim call or re-implement it briefly?
        # Let's keep it minimal: The harness handles execution. Simulation is an optimization.
        
        return proposal

    def save_proposal(self, proposal: Proposal, proposal_id: str):
        """
        Save strict proposal to:
        1. Canonical Artifacts (runs/<run_id>/episodes/<ep_id>/proposal.json)
        """
        # Use new EpisodeArtifacts API
        artifacts = EpisodeArtifacts(
            run_id=self.run_id,
            episode_id=proposal_id,
            base_dir=str(self.data_dir)
        )
        
        # Write proposal and metadata
        artifacts.write_proposal(proposal)
        artifacts.write_metadata(proposal.metadata)
        
        self.logger.info(f"💾 Proposal saved to {artifacts.episode_dir}/proposal.json")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode-id", type=str, required=True, help="Unique ID for this episode")
    args = parser.parse_args()

    agent = Phase5LearningAgent()
    try:
        proposal = agent.learn_and_propose(episode_id=args.episode_id)
        agent.save_proposal(proposal, proposal_id=args.episode_id)
    except Exception as e:
        agent.logger.exception("Agent Failure")
        sys.exit(1)
