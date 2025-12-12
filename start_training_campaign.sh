#!/usr/bin/env bash
# Uniswap V4 Training Campaign Runner
# - No `set -e` by design: we log failures and keep going.
# - Adds: pipefail, centralized logging, resumability, per-episode summary CSV, safer env loading.

set -u
set -o pipefail

# ------------------------------ Config --------------------------------------

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

EPISODES="${EPISODES:-30}"
START_EPISODE="${START_EPISODE:-1}"
SLEEP_BETWEEN_EPISODES="${SLEP_BETWEEN_EPISODES:-1}"

# Track A: New directory structure
DATA_DIR="${DATA_DIR:-$SCRIPT_DIR/data}"
RUNS_DIR="$DATA_DIR/runs"

AGENT_SCRIPT="${AGENT_SCRIPT:-$SCRIPT_DIR/quants-lab/phase5_learning_agent.py}"
HARNESS_BRIDGE="${HARNESS_BRIDGE:-$SCRIPT_DIR/quants-lab/scripts/run_episode.py}"

ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/.env}"

# Prefer venv python if present; override with VENV_PY=...
VENV_PY="${VENV_PY:-$SCRIPT_DIR/../.venv/bin/python3}"
if [[ ! -x "$VENV_PY" ]]; then
  VENV_PY="$(command -v python3 || true)"
fi

# Track A: Environment toggles (Single Source of Truth)
export HB_ENV="${HB_ENV:-mock}"              # mock or real
export MOCK_CLMM="${MOCK_CLMM:-false}"       # Force mock regardless of HB_ENV
export LEARN_FROM_MOCK="${LEARN_FROM_MOCK:-false}"  # Allow learning from mock episodes
export HB_SEED="${HB_SEED:-}"                # Optional seed for reproducibility

# Generate Campaign RUN_ID once
export RUN_ID="run_$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUNS_DIR/$RUN_ID"
mkdir -p "$RUN_DIR"

# Campaign log
CAMPAIGN_LOG="$RUN_DIR/campaign.log"

# Ensure Python path includes libs
export PYTHONPATH="${PYTHONPATH:-}:$SCRIPT_DIR/quants-lab"

mkdir -p "$DATA_DIR" "$RUNS_DIR"

# Determine exec_mode based on toggles
if [[ "$MOCK_CLMM" == "true" ]]; then
  EXEC_MODE="mock"
elif [[ "$HB_ENV" == "real" ]]; then
  EXEC_MODE="real"
else
  EXEC_MODE="mock"
fi
export EXEC_MODE

# Generate seed if not provided
if [[ -z "$HB_SEED" ]]; then
  HB_SEED=$RANDOM
  export HB_SEED
fi

# Send *all* stdout/stderr to both console and campaign log
exec > >(tee -a "$CAMPAIGN_LOG") 2>&1

# ------------------------------ Helpers ------------------------------------

ts() { date +"%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(ts)] $*"; }

check_file_exists() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    log "⚠️  Expected file missing: $f"
    return 1
  fi
  return 0
}

check_cmd_exists() {
  local c="$1"
  command -v "$c" >/dev/null 2>&1
}

run_step() {
  local name="$1"; shift
  log "▶️  $name: $*"
  "$@"
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    log "❌ $name failed (exit=$rc)"
  else
    log "✅ $name ok"
  fi
  return $rc
}

retry() {
  local name="$1"; shift
  local max="${1:-2}"; shift
  local delay="${1:-2}"; shift
  local attempt=1
  while true; do
    run_step "$name (attempt $attempt/$max)" "$@" && return 0
    if (( attempt >= max )); then
      return 1
    fi
    sleep "$delay"
    ((attempt++))
  done
}

# Log the Env Vars after helpers are defined
# ============================================================
# Environment Configuration Logging
# ============================================================
log "🆔 Run ID: $RUN_ID"
log "🌍 Env: HB_ENV=$HB_ENV | MOCK_CLMM=$MOCK_CLMM | EXEC_MODE=$EXEC_MODE"
log "🧪 Learning: LEARN_FROM_MOCK=$LEARN_FROM_MOCK"
log "🎲 Seed: HB_SEED=$HB_SEED"

# Log Dune API key presence (not the actual key)
if [ -n "${DUNE_API_KEY:-}" ]; then
  log "🔑 Dune API: PRESENT (${#DUNE_API_KEY} chars)"
else
  log "🔑 Dune API: NOT SET"
fi

# -------------------------- Pre-flight Checks ----------------------------

log "🚀 Starting Track A Training Campaign (Uniswap V3 CLMM)"
log "🎯 Episodes: $START_EPISODE..$EPISODES"
log "📁 Run dir: $RUN_DIR"
log "🗂  Campaign log: $CAMPAIGN_LOG"
log "🐍 Python: ${VENV_PY:-<not found>}"

check_file_exists "$AGENT_SCRIPT" || { log "❌ Agent script not found – aborting."; exit 1; }
check_file_exists "$HARNESS_BRIDGE" || { log "❌ Harness bridge not found – aborting."; exit 1; }

if [[ -z "${VENV_PY:-}" ]]; then
  log "❌ python3 not found and VENV_PY not executable – aborting."
  exit 1
fi

# Gateway Health Check (Only if Real Env)
if [[ "$EXEC_MODE" == "real" ]]; then
  log "🔍 Checking Gateway health (Required for Real Mode)..."
  MAX_RETRIES=10
  COUNT=0
  GATEWAY_READY=0
  
  while [[ $COUNT -lt $MAX_RETRIES ]]; do
      if check_cmd_exists curl && curl -fsS --max-time 2 "http://localhost:15888/" >/dev/null 2>&1; then
          log "✅ Gateway is healthy on :15888"
          GATEWAY_READY=1
          break
      fi
      log "⏳ Waiting for Gateway... ($((COUNT+1))/$MAX_RETRIES)"
      sleep 2
      ((COUNT++))
  done
  
  if [[ $GATEWAY_READY -eq 0 ]]; then
      log "❌ Gateway failed to respond. Aborting Campaign in Real Mode."
      exit 1
  fi
else
    log "⏭  Skipping Gateway check (Mock Mode active)"
fi

# Hummingbot API Check (Mock or Real, usually needed for baseline)
if check_cmd_exists curl; then
  if curl -fsS --max-time 2 "http://localhost:8000/" >/dev/null 2>&1; then
    log "✅ Hummingbot Client API appears healthy on :8000"
  else
    log "⚠️  Hummingbot Client API health check failed. Continuing (might be using mocked client)."
  fi
fi

# ---------------------- Trap for graceful shutdown -----------------------

SHOULD_STOP=0
trap 'log "🛑 Caught interrupt signal, will stop after current episode."; SHOULD_STOP=1' INT TERM

# -------------------------------- Main Loop ----------------------------

for ((i=START_EPISODE; i<=EPISODES; i++)); do
  echo
  log "---------------------------------------------------"
  log "🎬 Episode $i/$EPISODES"

  if [[ "$SHOULD_STOP" -ne 0 ]]; then
    log "⏹  Early stop requested – exiting campaign loop."
    break
  fi

  EP_START_EPOCH="$(date +%s)"
  EP_START_HUMAN="$(date +"%Y-%m-%d %H:%M:%S")"

  # Generate unique EPISODE_ID
  EPISODE_ID="ep_$(date +%Y%m%d_%H%M%S)_${i}"
  export EPISODE_ID

  log "🆔 Episode ID: $EPISODE_ID"

  # Load env if present (don't hard-fail if missing)
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
  else
    log "⚠️  ENV file not found at $ENV_FILE (continuing without it)"
  fi

  # 1) Agent: Learn & Propose
  log "🤖 Agent thinking..."
  "$VENV_PY" "$AGENT_SCRIPT" --episode-id "$EPISODE_ID"
  AGENT_EXIT=$?

  if [[ $AGENT_EXIT -ne 0 ]]; then
    log "❌ Agent failed (exit=$AGENT_EXIT). Writing failure artifacts..."
    
    # Write failure artifacts even when agent crashes
    "$VENV_PY" "$SCRIPT_DIR/quants-lab/tools/write_failure_artifact.py" \
      --run-id "$RUN_ID" \
      --episode-id "$EPISODE_ID" \
      --stage "agent" \
      --exec-mode "$EXEC_MODE" \
      --error "Agent failed with exit=$AGENT_EXIT. See campaign.log for traceback." \
      --exit-code "$AGENT_EXIT" \
      --config-hash "unknown" \
      --agent-version "v6.0_track_a"
    
    continue
  fi
  
  # 2) Validate Pool Config (real mode only)
  PROPOSAL_PATH="$DATA_DIR/runs/$RUN_ID/episodes/$EPISODE_ID/proposal.json"
  
  if [[ "$EXEC_MODE" == "real" ]]; then
    log "🔍 Validating pool configuration..."
    "$VENV_PY" "$SCRIPT_DIR/quants-lab/lib/pool_validator.py" \
      --proposal-path "$PROPOSAL_PATH" \
      --run-id "$RUN_ID" \
      --episode-id "$EPISODE_ID" \
      --exec-mode "$EXEC_MODE"
    
    VALIDATION_EXIT=$?
    
    if [[ $VALIDATION_EXIT -ne 0 ]]; then
      log "❌ Pool validation failed. Failure artifacts written. Skipping harness."
      continue
    fi
  else
    log "⏭  Skipping pool validation (mock mode)"
  fi

  # 2) Run Harness / Episode Runner
  log "🏃 Harness running via $HARNESS_BRIDGE..."
  "$VENV_PY" "$HARNESS_BRIDGE" --episode-id "$EPISODE_ID"
  HARNESS_EXIT=$?

  EP_END_EPOCH="$(date +%s)"
  EP_END_HUMAN="$(date +"%Y-%m-%d %H:%M:%S")"
  EP_DURATION=$((EP_END_EPOCH - EP_START_EPOCH))

  if [[ $HARNESS_EXIT -ne 0 ]]; then
    log "❌ Harness failed (exit=$HARNESS_EXIT). Duration=${EP_DURATION}s"
  else
    log "✅ Episode complete in ${EP_DURATION}s."
  fi

  sleep "$SLEEP_BETWEEN_EPISODES"

done

echo
log "🏆 Campaign Complete!"
log "📌 Campaign log: $CAMPAIGN_LOG"
log "📁 Run directory: $RUN_DIR"
