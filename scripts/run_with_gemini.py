#!/usr/bin/env python3
import os
import sys
import subprocess
import time
from pathlib import Path

# Try to import google-generativeai
try:
    import google.generativeai as genai
    import google.generativeai as genai
    from google.generativeai.types import FunctionDeclaration, Tool
except ImportError:
    print("❌ google-generativeai not found. Please install it:")
    print("   pip install --user google-generativeai")
    sys.exit(1)

import json # Added for logging

def load_env():
    """Simple .env loader to avoid dependencies."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        print(f"📄 Loading .env from {env_path}")
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.replace("export", "").strip()
                    value = value.strip().strip("'").strip('"')
                    if key and not os.getenv(key): # Don't overwrite existing
                        os.environ[key] = value

# Load env vars first
load_env()

# Configuration
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = "gemini-2.0-flash" # or gemini-2.5-pro for reasoning
PROMPT_PATH = Path(__file__).parent.parent / "quants-lab" / "AGENT_ORCHESTRATOR_PROMPT.md"

def run_shell_command(command: str, timeout: int = 300) -> dict:
    """
    Executes a shell command and returns the output.
    Only certain safe commands are allowed.
    """
    allowed_prefixes = [
        "python3 quants-lab/",
        "python3 hummingbot/scripts/",
        "python3 scripts/",
        "python3 test/",
        "./start_training_campaign.sh",
        "cat ",
        "ls ",
        "grep ",
        "head ",
        "tail ",
        "curl "
    ]
    
    clean_cmd = command.strip()
    is_allowed = False
    for prefix in allowed_prefixes:
        if clean_cmd.startswith(prefix):
            is_allowed = True
            break
            
    if not is_allowed:
        return {"error": f"Command not allowed: {command}", "success": False}
        
    print(f"💻 Executing: {command} (timeout={timeout}s)")
    try:
        # Run in project root
        cwd = Path(__file__).parent.parent
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "success": result.returncode == 0
        }
    except Exception as e:
        return {"error": str(e), "success": False}

def read_file(path: str) -> dict:
    """Reads a file from the filesystem."""
    print(f"📄 Reading file: {path}")
    try:
        file_path = Path(__file__).parent.parent / path
        if not file_path.exists():
            return {"error": f"File not found: {path}", "success": False}
        with open(file_path, "r") as f:
            content = f.read()
        return {"content": content, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}

def write_file(path: str, content: str) -> dict:
    """Writes content to a file."""
    print(f"💾 Writing file: {path}")
    try:
        file_path = Path(__file__).parent.parent / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        return {"success": True, "path": str(file_path)}
    except Exception as e:
        return {"error": str(e), "success": False}

def list_dir(path: str) -> dict:
    """Lists files in a directory."""
    print(f"📂 Listing directory: {path}")
    try:
        dir_path = Path(__file__).parent.parent / path
        if not dir_path.exists():
             return {"error": f"Directory not found: {path}", "success": False}
        files = [f.name for f in dir_path.iterdir()]
        return {"files": files, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}

def http_get(url: str) -> dict:
    """Performs an HTTP GET request."""
    print(f"🌐 HTTP GET: {url}")
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return {"status": response.status, "body": response.read().decode('utf-8'), "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}

def to_python_types(obj):
    """Recursively converts protobuf types (MapComposite, RepeatedComposite) to native dicts/lists."""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, dict):
        return {k: to_python_types(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_python_types(v) for v in obj]
    # Handle Protobuf MapComposite/RepeatedComposite by duck typing
    if hasattr(obj, "items"): # Map-like
        return {k: to_python_types(v) for k, v in obj.items()}
    if hasattr(obj, "__iter__"): # List-like
        return [to_python_types(v) for v in obj]
    return obj

def http_post(url: str, data: dict) -> dict:
    """Performs an HTTP POST request with a JSON object body (data)."""
    # Convert protobuf types to native types first
    data = to_python_types(data)
    
    print(f"🌐 HTTP POST: {url}")
    print(f"📦 Request Body: {json.dumps(data)}")
    import urllib.request
    # json is already imported at top level
    try:
        json_bytes = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=json_bytes, method='POST')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=10) as response:
            resp_body = response.read().decode('utf-8')
            print(f"📥 Response: {resp_body[:200]}...") # Truncate for sanity
            return {"status": response.status, "body": resp_body, "success": True}
    except Exception as e:
        # Handle HTTP errors nicely
        if hasattr(e, 'code') and hasattr(e, 'read'):
             err_body = e.read().decode('utf-8')
             print(f"❌ HTTP Error {e.code}: {err_body}")
             return {"status": e.code, "body": err_body, "error": str(e), "success": False}
        print(f"❌ Error: {str(e)}")
        return {"error": str(e), "success": False}

def main():
    if not API_KEY:
        print("❌ GOOGLE_API_KEY environment variable not set.")
        print("   Please run: export GOOGLE_API_KEY='your_key_here'")
        sys.exit(1)

    if not PROMPT_PATH.exists():
        print(f"❌ System prompt not found at {PROMPT_PATH}")
        sys.exit(1)

    print(f"🧠 Loading system prompt from {PROMPT_PATH.name}...")
    with open(PROMPT_PATH, "r") as f:
        system_instruction = f.read()

    # Configure GenAI
    genai.configure(api_key=API_KEY)
    
    # Define Tools
    tools = [run_shell_command, read_file, write_file, list_dir, http_get, http_post]
    
    # Create Model
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=system_instruction,
        tools=tools
    )
    
    # Start Chat
    chat = model.start_chat(enable_automatic_function_calling=True)
    
    print("\n🤖 Agent Orchestrator Ready.")
    print("   Type 'Run episode <ID>' to start a training loop.")
    print("   Type 'exit' or 'quit' to stop.\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            if user_input.lower() in ['exit', 'quit']:
                break
            if not user_input:
                continue
                
            print("🤖 Agent thinking...")
            response = chat.send_message(user_input)
            print(f"🤖 Agent: {response.text}")
            
        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
