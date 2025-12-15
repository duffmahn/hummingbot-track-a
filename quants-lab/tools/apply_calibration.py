#!/usr/bin/env python3
"""
Apply Dune calibration constants to agent configuration.

This script updates phase5_learning_agent.py constants from calibration.json
and optionally creates a backup of the original constants.
"""

import json
import argparse
from pathlib import Path
import re


def load_calibration(calibration_file: Path) -> dict:
    """Load calibration data from JSON file."""
    with open(calibration_file) as f:
        return json.load(f)


def apply_calibration(agent_file: Path, calibration: dict, dry_run: bool = False):
    """Apply calibration constants to agent file."""
    
    # Read current agent file
    with open(agent_file) as f:
        content = f.read()
    
    # Extract calibrated constants
    constants = calibration['calibrated_constants']
    
    # Prepare replacements
    replacements = [
        # GAS_USD
        (
            r'GAS_USD\s*=\s*[\d.]+',
            f'GAS_USD = {constants["GAS_USD"]}'
        ),
        # FEE_GATE
        (
            r'FEE_GATE\s*=\s*[\d.]+\s*\*\s*GAS_USD',
            f'FEE_GATE = {constants["FEE_GATE"]}'
        ),
        # DEFAULT_MIN_WIDTH
        (
            r'DEFAULT_MIN_WIDTH\s*=\s*\d+',
            f'DEFAULT_MIN_WIDTH = 1200'
        ),
    ]
    
    # Apply replacements
    new_content = content
    for pattern, replacement in replacements:
        new_content = re.sub(pattern, replacement, new_content)
    
    # Update REGIME_MIN_WIDTH dictionary
    width_dict = constants['REGIME_MIN_WIDTH']
    width_str = "REGIME_MIN_WIDTH = {\n"
    for regime, width in width_dict.items():
        width_str += f'    "{regime}": {width},\n'
    width_str += "}"
    
    # Replace REGIME_MIN_WIDTH block
    new_content = re.sub(
        r'REGIME_MIN_WIDTH\s*=\s*\{[^}]+\}',
        width_str,
        new_content,
        flags=re.DOTALL
    )
    
    # Update OOR_CRITICAL_BY_REGIME dictionary
    oor_dict = constants['OOR_CRITICAL_BY_REGIME']
    oor_str = "OOR_CRITICAL_BY_REGIME = {\n"
    for regime, threshold in oor_dict.items():
        oor_str += f'    "{regime}": {threshold},\n'
    oor_str += "}"
    
    # Replace OOR_CRITICAL_BY_REGIME block
    new_content = re.sub(
        r'OOR_CRITICAL_BY_REGIME\s*=\s*\{[^}]+\}',
        oor_str,
        new_content,
        flags=re.DOTALL
    )
    
    # Update OOR_CRITICAL_DEFAULT
    new_content = re.sub(
        r'OOR_CRITICAL_DEFAULT\s*=\s*[\d.]+',
        f'OOR_CRITICAL_DEFAULT = {constants["OOR_CRITICAL_DEFAULT"]}',
        new_content
    )
    
    if dry_run:
        print("DRY RUN - Changes that would be applied:")
        print("=" * 80)
        print(f"GAS_USD: {constants['GAS_USD']}")
        print(f"FEE_GATE: {constants['FEE_GATE']}")
        print(f"DEFAULT_MIN_WIDTH: 1200")
        print(f"REGIME_MIN_WIDTH: {width_dict}")
        print(f"OOR_CRITICAL_BY_REGIME: {oor_dict}")
        print(f"OOR_CRITICAL_DEFAULT: {constants['OOR_CRITICAL_DEFAULT']}")
        return
    
    # Write updated content
    with open(agent_file, 'w') as f:
        f.write(new_content)
    
    print("✅ Applied Dune calibration to agent constants")
    print(f"   GAS_USD: {constants['GAS_USD']}")
    print(f"   FEE_GATE: {constants['FEE_GATE']}")
    print(f"   Width floors updated")
    print(f"   OOR thresholds updated")


def main():
    parser = argparse.ArgumentParser(description="Apply Dune calibration to agent")
    parser.add_argument(
        "--calibration",
        default="dune_queries/calibration_report.json",
        help="Path to calibration JSON file"
    )
    parser.add_argument(
        "--agent-file",
        default="phase5_learning_agent.py",
        help="Path to agent file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without applying"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup of original file"
    )
    
    args = parser.parse_args()
    
    calibration_file = Path(args.calibration)
    agent_file = Path(args.agent_file)
    
    if not calibration_file.exists():
        print(f"❌ Calibration file not found: {calibration_file}")
        return 1
    
    if not agent_file.exists():
        print(f"❌ Agent file not found: {agent_file}")
        return 1
    
    # Load calibration
    calibration = load_calibration(calibration_file)
    
    # Create backup if requested
    if args.backup and not args.dry_run:
        backup_file = agent_file.with_suffix('.py.backup')
        with open(agent_file) as f:
            with open(backup_file, 'w') as fb:
                fb.write(f.read())
        print(f"📁 Backup created: {backup_file}")
    
    # Apply calibration
    apply_calibration(agent_file, calibration, dry_run=args.dry_run)
    
    if not args.dry_run:
        print("\n✅ Calibration applied successfully!")
        print("\nNext steps:")
        print("1. Review changes in phase5_learning_agent.py")
        print("2. Run 3-way comparison: ./run_3way_comparison.sh")
        print("3. Analyze results to validate calibration")


if __name__ == "__main__":
    exit(main() or 0)
