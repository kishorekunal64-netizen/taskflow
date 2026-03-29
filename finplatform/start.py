"""
Start the FinIntelligence FastAPI server.
Loads .env from finplatform/.env before starting uvicorn.

Run from C:\taskflow:
    python finplatform/start.py
"""

import os
import sys

# Ensure C:\taskflow is on sys.path so 'finplatform' and 'finintelligence' are importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Also set PYTHONPATH env var so uvicorn worker processes inherit it
os.environ["PYTHONPATH"] = ROOT

# Load .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())
    print(f"Loaded env from {env_path}")

import uvicorn

if __name__ == "__main__":
    print("Starting FinIntelligence API on http://localhost:8000")
    print("Docs: http://localhost:8000/docs")
    uvicorn.run(
        "finplatform.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["finplatform"],
    )
