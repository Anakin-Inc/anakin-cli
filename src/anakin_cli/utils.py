"""Output formatting and error classes for Anakin CLI."""

import json
import os
from pathlib import Path

from rich.console import Console

# Respect NO_COLOR (https://no-color.org/) and dumb terminals
_no_color = os.environ.get("NO_COLOR") is not None or os.environ.get("TERM") == "dumb"
console = Console(stderr=True, no_color=_no_color)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class AnakinError(Exception):
    """Base exception for all Anakin errors."""


class AnakinAuthError(AnakinError):
    """401 — missing or invalid API key."""


class AnakinUpgradeError(AnakinError):
    """402 — plan upgrade required."""


class AnakinRateLimitError(AnakinError):
    """429 — rate limit exceeded."""


class AnakinAPIError(AnakinError):
    """Generic API error (500, 503, unexpected status codes)."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class AnakinTimeoutError(AnakinError):
    """Polling timed out waiting for a job to complete."""


class AnakinJobFailedError(AnakinError):
    """Job finished with status 'failed'."""


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def output_result(data, output_path: str | None = None, fmt: str = "json"):
    """Write *data* to *output_path* (or stdout) in the requested format.

    Parameters
    ----------
    data : dict | list | str
        The result payload.
    output_path : str | None
        File path to write to.  ``None`` → stdout.
    fmt : str
        ``"json"`` (default) or ``"text"``.
    """
    if fmt == "text" and isinstance(data, str):
        content = data
    else:
        content = json.dumps(data, indent=2, ensure_ascii=False)

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        log_success(f"Output written to {output_path}")
    else:
        print(content)


def log(msg: str):
    """Print a progress/status message to stderr."""
    console.print(msg)


def log_success(msg: str):
    """Print a success message in green to stderr."""
    console.print(f"[green]✔[/green] {msg}")


def log_warning(msg: str):
    """Print a warning message in yellow to stderr."""
    console.print(f"[yellow]⚠[/yellow] {msg}")


def log_error(msg: str):
    """Print an error message in red to stderr."""
    console.print(f"[red]✘[/red] {msg}")
