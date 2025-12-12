"""
Agentic Coder Tool Service

A thin HTTP service that exposes the tools defined in agentic_coder_tool_spec.json
for use by an LLM-based agentic coder.

This service provides:
- File read/write with safety restrictions
- Shell command execution with allowlist
- Domain-specific high-level tools
- Secret validation without exposure

Usage:
    python3 agentic_coder_service.py --port 8100
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Any
from datetime import datetime

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

# Load tool spec
TOOL_SPEC_PATH = Path(__file__).parent / "agentic_coder_tool_spec.json"

# Safety: Whitelisted directories (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent
WHITELISTED_DIRS = [
    PROJECT_ROOT / "quants-lab",
    PROJECT_ROOT / "hummingbot" / "scripts",
    PROJECT_ROOT / "hummingbot_gateway" / "src" / "connectors" / "uniswap_v4",
    PROJECT_ROOT / "conf",
    PROJECT_ROOT / "test",
    PROJECT_ROOT / "data",
]

# Safety: Blocked file patterns
BLOCKED_PATTERNS = [
    ".env",
    ".env.",
    ".pem",
    ".key",
    "wallets",
    "certs",
    ".secret",
    "private_key",
]

# Safety: Allowed shell commands (prefixes)
ALLOWED_COMMANDS = [
    "python3 -m pytest",
    "python3 quants-lab/",
    "python3 hummingbot/scripts/",
    "python3 scripts/",
    "python3 test/",
    "./start_training_campaign.sh",
    "cat ",
    "ls ",
    "head ",
    "tail ",
    "wc ",
]


def load_tool_spec() -> dict:
    """Load the tool specification."""
    if TOOL_SPEC_PATH.exists():
        with open(TOOL_SPEC_PATH, 'r') as f:
            return json.load(f)
    return {}


def is_path_allowed(path: str) -> bool:
    """Check if a path is within whitelisted directories."""
    try:
        resolved = Path(path).resolve()
        for allowed in WHITELISTED_DIRS:
            if str(resolved).startswith(str(allowed.resolve())):
                return True
        return False
    except:
        return False


def is_path_blocked(path: str) -> bool:
    """Check if a path matches blocked patterns."""
    path_lower = path.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in path_lower:
            return True
    return False


def is_command_allowed(cmd: str) -> bool:
    """Check if a command is in the allowlist."""
    cmd_stripped = cmd.strip()
    for allowed in ALLOWED_COMMANDS:
        if cmd_stripped.startswith(allowed):
            return True
    return False


class AgenticCoderHandler(BaseHTTPRequestHandler):
    """HTTP handler for agentic coder tools."""
    
    def _send_json(self, data: dict, status: int = 200):
        """Send a JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def _read_json_body(self) -> Optional[dict]:
        """Read JSON body from request."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            return json.loads(body) if body else {}
        except:
            return None
    
    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            self._send_json({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})
        
        elif self.path == "/tools":
            spec = load_tool_spec()
            self._send_json({"tools": spec.get("tools", {})})
        
        elif self.path == "/secrets/check":
            # Check if required secrets are configured (without exposing values)
            result = {
                "WALLET_PRIVATE_KEY": os.getenv("WALLET_PRIVATE_KEY") is not None,
                "DUNE_API_KEY": os.getenv("DUNE_API_KEY") is not None,
                "GATEWAY_PASSPHRASE": os.getenv("GATEWAY_PASSPHRASE") is not None,
            }
            self._send_json(result)
        
        else:
            self._send_json({"error": "Not found"}, 404)
    
    def do_POST(self):
        """Handle POST requests."""
        body = self._read_json_body()
        if body is None:
            self._send_json({"error": "Invalid JSON body"}, 400)
            return
        
        # ===== FILE TOOLS =====
        if self.path == "/tools/read_file":
            path = body.get("path")
            if not path:
                return self._send_json({"error": "Missing 'path' parameter"}, 400)
            
            if is_path_blocked(path):
                return self._send_json({"error": "Access to this file is blocked for security"}, 403)
            
            if not is_path_allowed(path):
                return self._send_json({"error": f"Path not in whitelisted directories"}, 403)
            
            try:
                with open(path, 'r') as f:
                    content = f.read()
                self._send_json({"success": True, "content": content})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
        
        elif self.path == "/tools/write_file":
            path = body.get("path")
            content = body.get("content")
            
            if not path or content is None:
                return self._send_json({"error": "Missing 'path' or 'content'"}, 400)
            
            if is_path_blocked(path):
                return self._send_json({"error": "Writing to this file is blocked for security"}, 403)
            
            if not is_path_allowed(path):
                return self._send_json({"error": f"Path not in whitelisted directories"}, 403)
            
            try:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                with open(path, 'w') as f:
                    f.write(content)
                self._send_json({"success": True, "path": path})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
        
        # ===== SHELL TOOLS =====
        elif self.path == "/tools/run_cmd":
            cmd = body.get("cmd")
            cwd = body.get("cwd", str(PROJECT_ROOT))
            timeout = body.get("timeout_seconds", 120)
            
            if not cmd:
                return self._send_json({"error": "Missing 'cmd' parameter"}, 400)
            
            if not is_command_allowed(cmd):
                return self._send_json({
                    "error": f"Command not in allowlist. Allowed prefixes: {ALLOWED_COMMANDS}"
                }, 403)
            
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                self._send_json({
                    "success": result.returncode == 0,
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                })
            except subprocess.TimeoutExpired:
                self._send_json({"success": False, "error": f"Command timed out after {timeout}s"}, 500)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
        
        # ===== DOMAIN TOOLS =====
        elif self.path == "/tools/load_experiments":
            try:
                from uv4_experiments import UV4ExperimentStore
                min_version = body.get("min_version", "v1_realtime")
                quality_filter = body.get("quality_filter", ("good",))
                if isinstance(quality_filter, str):
                    quality_filter = (quality_filter,)
                
                store = UV4ExperimentStore()
                df = store.to_dataframe(min_version=min_version, intel_quality_whitelist=quality_filter)
                
                self._send_json({
                    "success": True,
                    "count": len(df),
                    "runs": df.to_dict(orient="records") if len(df) <= 100 else df.head(100).to_dict(orient="records"),
                    "truncated": len(df) > 100
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
        
        elif self.path == "/tools/propose_config":
            try:
                sys.path.insert(0, str(Path(__file__).parent / "controllers"))
                from uniswap_v4_param_controller import UniswapV4ParamController
                
                market_intel = body.get("market_intel", {})
                controller = UniswapV4ParamController()
                config = controller.propose_config(market_intel)
                validation = controller.validate_config(config)
                
                self._send_json({
                    "success": True,
                    "config": config.__dict__,
                    "validation": validation,
                    "yaml": controller.to_yaml(config)
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
        
        elif self.path == "/tools/run_learning_campaign":
            episodes = body.get("episodes", 5)
            try:
                result = subprocess.run(
                    f"EPISODES={episodes} ./start_training_campaign.sh",
                    shell=True,
                    cwd=str(PROJECT_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 min max for campaigns
                )
                self._send_json({
                    "success": result.returncode == 0,
                    "episodes": episodes,
                    "exit_code": result.returncode,
                    "stdout_tail": result.stdout[-2000:] if result.stdout else "",
                    "stderr_tail": result.stderr[-1000:] if result.stderr else ""
                })
            except subprocess.TimeoutExpired:
                self._send_json({"success": False, "error": "Campaign timed out"}, 500)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
        
        else:
            self._send_json({"error": f"Unknown tool: {self.path}"}, 404)
    
    def log_message(self, format, *args):
        """Custom logging."""
        print(f"[AgenticCoder] {args[0]} {args[1]}")


def main():
    parser = argparse.ArgumentParser(description="Agentic Coder Tool Service")
    parser.add_argument("--port", type=int, default=8100, help="Port to listen on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()
    
    print(f"🤖 Agentic Coder Tool Service")
    print(f"   Listening on: http://{args.host}:{args.port}")
    print(f"   Tool spec: {TOOL_SPEC_PATH}")
    print(f"   Project root: {PROJECT_ROOT}")
    print(f"\n📚 Available endpoints:")
    print(f"   GET  /health           - Health check")
    print(f"   GET  /tools            - List available tools")
    print(f"   GET  /secrets/check    - Check if secrets are configured")
    print(f"   POST /tools/read_file  - Read a file")
    print(f"   POST /tools/write_file - Write to a file")
    print(f"   POST /tools/run_cmd    - Run a shell command")
    print(f"   POST /tools/load_experiments    - Load experiment data")
    print(f"   POST /tools/propose_config      - Generate controller config")
    print(f"   POST /tools/run_learning_campaign - Run training campaign")
    print()
    
    server = HTTPServer((args.host, args.port), AgenticCoderHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
