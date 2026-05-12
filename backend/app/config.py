"""Configuration and path resolution for the FastAPI backend.

The backend imports the existing Python modules at the repo root (nba_agent,
nba_multi_agent, nba_cot_baseline) without modifying them. Those modules read
CSVs from a relative `data/` directory and write logs back there, so we
prepend the repo root to sys.path and chdir into it on import.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# backend/app/config.py -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
CHROMA_DIR = REPO_ROOT / "chroma_db"

# Make the Streamlit-era Python files importable.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Several existing tools open CSVs with relative paths like `data/foo.csv`.
# Switch the process cwd to the repo root once on import so those calls
# resolve regardless of where uvicorn was launched.
os.chdir(REPO_ROOT)

# Load .env from the repo root (where the user already keeps their keys).
load_dotenv(REPO_ROOT / ".env")


def resolve_api_key(name: str) -> str:
    """Find an API key from env or .env file."""
    val = os.environ.get(name, "").strip()
    if val:
        return val
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith(f"{name}="):
                    parsed = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if parsed:
                        os.environ[name] = parsed
                        return parsed
        except Exception:
            pass
    return ""


def has_anthropic_key() -> bool:
    return bool(resolve_api_key("ANTHROPIC_API_KEY"))


def has_openai_key() -> bool:
    return bool(resolve_api_key("OPENAI_API_KEY"))


def llm_label() -> str:
    if has_anthropic_key():
        return "Claude Haiku 4.5"
    if has_openai_key():
        return "GPT-4o"
    return "No model configured"
