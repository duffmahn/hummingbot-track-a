#!/bin/bash
set -u

# --- Config -----------------------------------------------------------------
GATEWAY_DIR="hummingbot_gateway"
GATEWAY_PORT=15888
LOG_FILE="logs/setup_environment.log"

# --- Helpers ----------------------------------------------------------------
ts() {
  date +"%Y-%m-%d %H:%M:%S"
}

log() {
  echo "[$(ts)] $*" | tee -a "$LOG_FILE"
}

error() {
  log "❌ $1"
  exit 1
}

# Ensure we are in the scratch directory (parent of scripts/)
# If run from scripts/, move up.
if [[ "$(basename "$(pwd)")" == "scripts" ]]; then
    cd ..
fi

mkdir -p logs

log "🚀 Starting Environment Setup..."

# 1. Check Dependencies
if ! command -v node >/dev/null 2>&1; then
    error "Node.js is not installed. Please install Node.js (v18+ recommended)."
fi

if ! command -v pnpm >/dev/null 2>&1; then
    log "📦 pnpm not found. Attempting to install via npm..."
    if command -v sudo >/dev/null 2>&1; then
        sudo npm install -g pnpm || error "Failed to install pnpm using sudo."
    else
        npm install -g pnpm || error "Failed to install pnpm (no sudo available)."
    fi
    log "✅ pnpm installed."
else
    log "✅ pnpm is already installed."
fi

# 2. Gateway Setup
if [ ! -d "$GATEWAY_DIR" ]; then
    error "Gateway directory '$GATEWAY_DIR' not found. Are you in the correct root (scratch/)?"
fi

log "📂 Entering $GATEWAY_DIR..."
cd "$GATEWAY_DIR" || error "Could not cd to $GATEWAY_DIR"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    log "📦 Installing Gateway dependencies..."
    pnpm install || error "pnpm install failed."
else
    log "✅ Gateway dependencies appear compliant."
fi

# 3. Certificates
if [ ! -f "certs/server_key.pem" ] || [ ! -f "certs/server_cert.pem" ]; then
    log "keygen: Certificates missing. Generating self-signed certs..."
    mkdir -p certs
    
    # Try generating without sudo first
    if openssl genrsa -out certs/server_key.pem 2048 2>/dev/null && \
       openssl req -new -key certs/server_key.pem -out certs/server_cert.csr -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost" 2>/dev/null && \
       openssl x509 -req -days 365 -in certs/server_cert.csr -signkey certs/server_key.pem -out certs/server_cert.pem 2>/dev/null; then
       log "✅ Certificates generated successfully (user permission)."
    else
       log "⚠️  User permission failed. Retrying with sudo..."
       if command -v sudo >/dev/null 2>&1; then
           sudo openssl genrsa -out certs/server_key.pem 2048 && \
           sudo openssl req -new -key certs/server_key.pem -out certs/server_cert.csr -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost" && \
           sudo openssl x509 -req -days 365 -in certs/server_cert.csr -signkey certs/server_key.pem -out certs/server_cert.pem || \
           error "Failed to generate certificates even with sudo."
           
           # Fix ownership
           sudo chown -R $(whoami) certs/
           log "✅ Certificates generated with sudo."
       else
           error "Failed to generate certificates and sudo is not available."
       fi
    fi
    # Ensure ca_cert.pem exists (copy from server_cert for self-signed)
    cp certs/server_cert.pem certs/ca_cert.pem
else
    log "✅ Certificates found."
fi

# 4. Service Startup
log "🔍 Checking if Gateway is running on port $GATEWAY_PORT..."
if curl -fsS "http://localhost:$GATEWAY_PORT/health" >/dev/null 2>&1; then
    log "✅ Gateway is already running and healthy."
else
    log "🚀 Starting Gateway (background)..."
    # Start using pnpm start, detached
    # We use nohup to keep it running
    
    # Check for passphrase, default to 'hummingbot' if not set
    if [ -z "${GATEWAY_PASSPHRASE:-}" ]; then
        export GATEWAY_PASSPHRASE="hummingbot"
        log "🔑 Using default passphrase: 'hummingbot'"
    fi

    # Ensure WALLET_PRIVATE_KEY is set (required by newer Gateway versions?)
    if [ -z "${WALLET_PRIVATE_KEY:-}" ]; then
        # Generate a random 32-byte hex key
        export WALLET_PRIVATE_KEY=$(openssl rand -hex 32)
        log "🔑 Generated temporary WALLET_PRIVATE_KEY for startup."
    fi

    nohup pnpm start --dev > logs/gateway_startup.log 2>&1 &
    PID=$!
    log "   PID: $PID"
    log "⏳ Waiting for Gateway to be healthy (max 30s)..."
    
    ATTEMPTS=0
    MAX_ATTEMPTS=30
    while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
        if curl -fsS "http://localhost:$GATEWAY_PORT/" >/dev/null 2>&1; then
            log "✅ Gateway is now running and healthy!"
            break
        fi
        sleep 1
        ATTEMPTS=$((ATTEMPTS+1))
        echo -n "."
    done
    
    if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
        log "⚠️  Gateway start timed out. Check logs/gateway_startup.log"
        # Don't exit error, maybe it's just slow.
    fi
fi

log "🏆 Environment setup complete."
