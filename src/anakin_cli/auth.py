"""API key management for Anakin CLI.

Resolution order:
  1. ANAKIN_API_KEY environment variable (takes precedence)
  2. ~/.anakin/config.json file
  3. Interactive prompt (if running in a terminal), only for commands that
     need a key. `scrape` and Wire discovery work without one (Zero Touch).
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".anakin"
CONFIG_FILE = CONFIG_DIR / "config.json"
SIGNUP_URL = "https://anakin.io/signup"


def load_config() -> dict[str, Any]:
    """Load the config file, returning an empty dict if it doesn't exist."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_api_key(api_key: str) -> None:
    """Persist *api_key* to ~/.anakin/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config()
    config["api_key"] = api_key
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    # Restrict permissions to owner-only (no-op on Windows)
    with contextlib.suppress(OSError):
        CONFIG_FILE.chmod(0o600)


def get_api_key() -> str | None:
    """Return the API key (env var first, then config file), or None."""
    key = os.environ.get("ANAKIN_API_KEY")
    if key:
        return key
    key = load_config().get("api_key")
    return key if isinstance(key, str) and key else None


def require_api_key() -> str:
    """Return the API key, prompting interactively if missing."""
    key = get_api_key()
    if key:
        return key

    if sys.stdin.isatty():
        from anakin_cli.utils import console, log_success

        console.print(
            "[yellow]This command needs an API key.[/yellow]\n"
            f"Get one free (300 credits) at [bold]{SIGNUP_URL}[/bold]\n"
        )
        key = console.input("[bold]Enter your API key:[/bold] ").strip()
        if key:
            save_api_key(key)
            log_success("API key saved to ~/.anakin/config.json")
            return key

    print(
        "Error: No API key configured.\n"
        "\n"
        "Set your Anakin API key using one of:\n"
        "  1. anakin login --api-key 'ak-xxx'\n"
        "  2. export ANAKIN_API_KEY='ak-xxx'\n"
        "\n"
        f"Get a free key at {SIGNUP_URL}",
        file=sys.stderr,
    )
    sys.exit(1)
