"""
UniswapV4ParamController

A Quants Lab Compatible Controller that bridges Phase5LearningAgent logic
into the standard Hummingbot V2 Controller architecture.

This allows the Learning Agent's "brain" to plug into the standard
Executor "body" while gaining access to backtesting and database storage.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import json

# --- Controller Config (Pydantic-style, for YAML serialization) ---

@dataclass
class UniswapV4ParamControllerConfig:
    """
    Configuration for the UniswapV4ParamController.
    This is intended to be serializable to YAML for use with v2_with_controllers.py.
    """
    # Identity
    controller_name: str = "uniswap_v4_param_controller"
    controller_type: str = "directional_trading"  # or "market_making"
    
    # Target Pool
    connector_name: str = "uniswap_v4_ethereum_mainnet"
    trading_pair: str = "WETH-USDC"
    pool_address: str = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"
    
    # Strategy Parameters (Proposed by Learning Agent)
    spread_bps: int = 50
    range_width_pct: float = 2.0
    rebalance_threshold_pct: float = 5.0
    max_position_usd: float = 1000.0
    
    # Risk Limits (Hard Constraints - never overridden by agent)
    max_drawdown_usd: float = 100.0
    max_gas_per_action_usd: float = 10.0
    min_simulation_success_rate: float = 0.8
    
    # Execution Settings
    leverage: int = 1
    position_mode: str = "ONE_WAY"
    
    # Kill Switch
    manual_kill_switch: bool = False
    
    # Metadata
    version: str = "v1"
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    source_agent: str = "Phase5LearningAgent"
    confidence: str = "medium"  # low, medium, high
    regime: str = "unknown"


# --- Controller Interface ---

class UniswapV4ParamController:
    """
    Quants Lab Controller for Uniswap V4 Parameter Optimization.
    
    This class bridges the Phase5LearningAgent (Brain) with the
    Hummingbot V2 Executor system (Body).
    
    Lifecycle:
        1. Agent calls `propose_config()` with current market intel.
        2. Controller generates a `UniswapV4ParamControllerConfig`.
        3. Config is saved to YAML.
        4. `v2_with_controllers.py` loads the YAML and executes.
        5. Results are logged via `record_outcome()`.
    """
    
    def __init__(self, agent=None, experiment_store=None):
        """
        Args:
            agent: Optional Phase5LearningAgent instance for proposal logic.
            experiment_store: Optional UV4ExperimentStore for historical data.
        """
        self.agent = agent
        self.store = experiment_store
        self.current_config: Optional[UniswapV4ParamControllerConfig] = None
    
    def propose_config(
        self,
        market_intel: Dict[str, Any],
        historical_runs: Optional[List[Dict]] = None
    ) -> UniswapV4ParamControllerConfig:
        """
        Generate a new controller config based on market intelligence.
        
        This is where the Learning Agent's proposal logic lives.
        
        Args:
            market_intel: Dict from MarketIntelligence.get_market_regime()
            historical_runs: Optional list of past experiment results.
        
        Returns:
            A new UniswapV4ParamControllerConfig ready for execution.
        """
        regime = market_intel.get("regime", "unknown")
        volatility = market_intel.get("volatility", 0.5)
        
        # Default params
        params = {
            "spread_bps": 50,
            "range_width_pct": 2.0,
            "rebalance_threshold_pct": 5.0,
        }
        
        # Regime-based adjustments (simplified from Phase5LearningAgent)
        if regime == "high_vol_high_liquidity":
            params["spread_bps"] = 80
            params["range_width_pct"] = 3.0
        elif regime == "low_vol_high_liquidity":
            params["spread_bps"] = 30
            params["range_width_pct"] = 1.5
        elif regime == "high_vol_low_liquidity":
            params["spread_bps"] = 100
            params["range_width_pct"] = 4.0
        # low_vol_low_liquidity uses defaults
        
        # Apply learning from historical runs if available
        if historical_runs and self.agent:
            # Delegate to agent's optimization logic
            params = self.agent.optimize_params(regime, historical_runs)
        
        # Calculate confidence
        confidence = "medium"
        if historical_runs and len(historical_runs) >= 10:
            confidence = "high"
        elif not historical_runs:
            confidence = "low"
        
        config = UniswapV4ParamControllerConfig(
            spread_bps=params.get("spread_bps", 50),
            range_width_pct=params.get("range_width_pct", 2.0),
            rebalance_threshold_pct=params.get("rebalance_threshold_pct", 5.0),
            regime=regime,
            confidence=confidence,
        )
        
        self.current_config = config
        return config
    
    def validate_config(self, config: UniswapV4ParamControllerConfig) -> Dict[str, Any]:
        """
        Validate a config against safety rules.
        
        Returns:
            Dict with 'valid' (bool) and 'errors' (list of strings).
        """
        errors = []
        
        if config.spread_bps < 10:
            errors.append("spread_bps too low (min 10)")
        if config.spread_bps > 500:
            errors.append("spread_bps too high (max 500)")
        if config.range_width_pct < 0.5:
            errors.append("range_width_pct too narrow (min 0.5%)")
        if config.range_width_pct > 10.0:
            errors.append("range_width_pct too wide (max 10%)")
        if config.max_drawdown_usd <= 0:
            errors.append("max_drawdown_usd must be positive")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }
    
    def to_yaml(self, config: UniswapV4ParamControllerConfig) -> str:
        """
        Serialize config to YAML for use with v2_with_controllers.py.
        """
        import yaml
        return yaml.dump(config.__dict__, default_flow_style=False)
    
    def record_outcome(
        self,
        config: UniswapV4ParamControllerConfig,
        metrics: Dict[str, Any],
        intel_start: Dict[str, Any],
        intel_end: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Record the outcome of an experiment run.
        
        This creates a standard experiment record compatible with UV4ExperimentStore.
        
        Args:
            config: The config that was executed.
            metrics: Performance metrics (pnl, drawdown, gas, etc.).
            intel_start: Market intel at start of run.
            intel_end: Market intel at end of run.
        
        Returns:
            The experiment record (dict) that was saved.
        """
        from datetime import datetime
        import uuid
        
        record = {
            "run_id": str(uuid.uuid4())[:8],
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "experiment_version": "v1_realtime",
            "status": "completed",
            "params": {
                "spread_bps": config.spread_bps,
                "range_width_pct": config.range_width_pct,
                "rebalance_threshold_pct": config.rebalance_threshold_pct,
            },
            "metrics": metrics,
            "intel_start": intel_start,
            "intel_end": intel_end,
            "regime_at_start": intel_start.get("regime", "unknown"),
            "regime_at_end": intel_end.get("regime", "unknown"),
            "training_phase": "exploitation" if config.confidence == "high" else "exploration",
            "controller_version": config.version,
        }
        
        if self.store:
            # Save to experiment store
            self.store.save_run(record)
        
        return record


# --- CLI ---

if __name__ == "__main__":
    import argparse
    import sys
    
    # Add lib to path for imports
    sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
    
    parser = argparse.ArgumentParser(
        description="UniswapV4ParamController CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - show what config would be generated
  python3 uniswap_v4_param_controller.py --dry-run
  
  # Save config to YAML file
  python3 uniswap_v4_param_controller.py --save-yaml config.yml
  
  # Record a mock outcome to test store integration
  python3 uniswap_v4_param_controller.py --record-mock
        """
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate and validate config without saving")
    parser.add_argument("--save-yaml", type=str, metavar="FILE",
                        help="Save generated config to YAML file")
    parser.add_argument("--record-mock", action="store_true",
                        help="Record a mock experiment outcome to test store")
    parser.add_argument("--regime", type=str, default="low_vol_high_liquidity",
                        choices=["low_vol_low_liquidity", "low_vol_high_liquidity",
                                 "high_vol_low_liquidity", "high_vol_high_liquidity"],
                        help="Market regime for config generation")
    
    args = parser.parse_args()
    
    # Initialize store for record-mock
    store = None
    if args.record_mock:
        from uv4_experiments import UV4ExperimentStore
        store = UV4ExperimentStore()
    
    controller = UniswapV4ParamController(experiment_store=store)
    
    # Generate mock intel based on regime
    mock_intel = {
        "regime": args.regime,
        "volatility": 0.45 if "low_vol" in args.regime else 1.2,
        "liquidity": 5_000_000 if "high_liquidity" in args.regime else 500_000,
        "volume": 100_000,
    }
    
    print(f"🎯 Market Intel: {args.regime}")
    print(f"   Volatility: {mock_intel['volatility']:.0%}")
    print(f"   Liquidity: ${mock_intel['liquidity']:,.0f}")
    
    # Propose config
    config = controller.propose_config(mock_intel)
    
    print(f"\n📋 Generated Config:")
    print(f"   Spread: {config.spread_bps} bps")
    print(f"   Range Width: {config.range_width_pct}%")
    print(f"   Rebalance Threshold: {config.rebalance_threshold_pct}%")
    print(f"   Confidence: {config.confidence}")
    
    # Validate
    validation = controller.validate_config(config)
    if validation["valid"]:
        print(f"\n✅ Validation: PASS")
    else:
        print(f"\n❌ Validation: FAIL")
        for err in validation["errors"]:
            print(f"   - {err}")
        sys.exit(1)
    
    # Save YAML if requested
    if args.save_yaml:
        yaml_content = controller.to_yaml(config)
        with open(args.save_yaml, "w") as f:
            f.write(yaml_content)
        print(f"\n💾 Saved YAML to: {args.save_yaml}")
    
    # Record mock outcome if requested
    if args.record_mock:
        mock_metrics = {
            "total_pnl_usd": 15.50,
            "max_drawdown_usd": 5.20,
            "gas_cost_usd": 2.10,
            "trade_count": 3,
            "actions_count": 5,
            "inventory_drift": 0.02,
        }
        record = controller.record_outcome(
            config=config,
            metrics=mock_metrics,
            intel_start=mock_intel,
            intel_end=mock_intel,  # Same for mock
        )
        print(f"\n📊 Recorded mock outcome:")
        print(f"   Run ID: {record['run_id']}")
        print(f"   PnL: ${record['metrics']['total_pnl_usd']:.2f}")
    
    # Dry run - just show YAML
    if args.dry_run or (not args.save_yaml and not args.record_mock):
        print(f"\n📄 YAML Output:")
        print("-" * 40)
        print(controller.to_yaml(config))
