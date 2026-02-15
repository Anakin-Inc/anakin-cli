"""API key management for Anakin CLI.

Resolution order:
  1. ANAKIN_API_KEY environment variable (takes precedence)
  2. ~/.anakin/config.json file
  3. Interactive prompt (if running in a terminal)
"""

import json
import os
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".anakin"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """Load the config file, returning an empty dict if it doesn't exist."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_api_key(api_key: str) -> None:
    """Persist *api_key* to ~/.anakin/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config()
    config["api_key"] = api_key
    CONFIG_FILE.write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    # Restrict permissions to owner-only (no-op on Windows)
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass


def get_api_key() -> str | None:
    """Return the API key (env var first, then config file), or None."""
    key = os.environ.get("ANAKIN_API_KEY")
    if key:
        return key
    config = load_config()
    return config.get("api_key")


def require_api_key() -> str:
    """Return the API key, prompting interactively if missing."""
    key = get_api_key()
    if key:
        return key

    # If stdin is a terminal, prompt the user interactively
    if sys.stdin.isatty():
        from anakin_cli.utils import console, log_success

        console.print(
            "[yellow]No API key configured.[/yellow]\n"
            "Get your key at [bold]https://anakin.io/dashboard[/bold]\n"
        )
        key = console.input("[bold]Enter your API key:[/bold] ").strip()
        if key:
            save_api_key(key)
            log_success("API key saved to ~/.anakin/config.json")
            return key

    # Non-interactive or empty input — exit with help
    print(
        "Error: No API key configured.\n"
        "\n"
        "Set your Anakin API key using one of:\n"
        "  1. anakin login --api-key 'ak-xxx'\n"
        "  2. export ANAKIN_API_KEY='ak-xxx'\n"
        "\n"
        "Get your key at https://anakin.io/dashboard",
        file=sys.stderr,
    )
    sys.exit(1)
