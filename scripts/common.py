"""Helpers shared by the setup scripts: reading and writing config.json.

config.json lives at the repo root. The scripts fill it in as resources are
created, so each step knows what the previous step built. The Todoist token is
never stored here (it lives in AWS Secrets Manager).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"

# Lets scripts reuse lambda/todoist_client.py (e.g. to check a token).
sys.path.insert(0, str(ROOT / "lambda"))


def load_config() -> dict:
    """Read config.json, creating it from config.example.json the first time."""
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        print("Created config.json from config.example.json")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def check_todoist_token(token: str) -> tuple[bool, str]:
    """Ask Todoist for one task. Returns (ok, message)."""
    import todoist_client

    todoist_client._cached_token = token
    try:
        todoist_client.request("GET", "tasks", query={"limit": 1})
    except todoist_client.TodoistError as error:
        return False, str(error)
    return True, "Todoist token works."
