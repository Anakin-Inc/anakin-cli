"""Output formatting and error reporting for Anakin CLI."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import anakin
from pydantic import BaseModel
from rich.console import Console

# Respect NO_COLOR (https://no-color.org/) and dumb terminals
_no_color = os.environ.get("NO_COLOR") is not None or os.environ.get("TERM") == "dumb"
console = Console(stderr=True, no_color=_no_color)


class CLIError(Exception):
    """A user-facing error raised by the CLI itself (bad flags, unreadable files)."""


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def to_jsonable(data: Any) -> Any:
    """Convert SDK models (and lists of them) into plain JSON-serialisable data."""
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json", exclude_none=True)
    if isinstance(data, list):
        return [to_jsonable(item) for item in data]
    if isinstance(data, dict):
        return {key: to_jsonable(value) for key, value in data.items()}
    return data


def output_result(data: Any, output_path: str | None = None, fmt: str = "json") -> None:
    """Write *data* to *output_path* (or stdout).

    ``fmt="text"`` writes strings as-is; everything else is pretty JSON.
    """
    if fmt == "text" and isinstance(data, str):
        content = data
    else:
        content = json.dumps(to_jsonable(data), indent=2, ensure_ascii=False)

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        log_success(f"Output written to {output_path}")
    else:
        print(content)


def output_bytes(data: bytes, output_path: str | None) -> None:
    """Write binary *data* (screenshots, Wire files) to a file, or raw to stdout."""
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        log_success(f"Wrote {len(data)} bytes to {output_path}")
    elif sys.stdout.isatty():
        raise CLIError("Refusing to print binary data to a terminal; pass -o FILE.")
    else:
        sys.stdout.buffer.write(data)


@contextmanager
def spinner(message: str) -> Iterator[None]:
    """Show a spinner on stderr while a blocking SDK call runs (TTY only)."""
    if console.is_terminal:
        with console.status(f"[bold blue]{message}[/bold blue]", spinner="dots"):
            yield
    else:
        yield


def log(msg: str) -> None:
    """Print a progress/status message to stderr."""
    console.print(msg)


def log_success(msg: str) -> None:
    console.print(f"[green]✔[/green] {msg}")


def log_warning(msg: str) -> None:
    console.print(f"[yellow]⚠[/yellow] {msg}")


def log_error(msg: str) -> None:
    console.print(f"[red]✘[/red] {msg}")


# ---------------------------------------------------------------------------
# Error reporting
# ---------------------------------------------------------------------------


def describe_error(exc: anakin.AnakinError) -> list[str]:
    """Turn an SDK error into one headline plus optional hint lines."""
    lines = [str(exc)]
    if isinstance(exc, anakin.WireAuthRequiredError):
        lines.append(f"Connect the account first: {exc.connect_url}")
    elif isinstance(exc, anakin.WireAuthExpiredError):
        lines.append("The saved site login expired. Run: anakin wire login <catalog> ...")
    elif isinstance(exc, anakin.AuthenticationError):
        lines.append("Check your key: anakin login --api-key 'ak-xxx' (or set ANAKIN_API_KEY)")
    elif isinstance(exc, anakin.InsufficientCreditsError):
        if exc.signup_url:
            lines.append(f"Get 300 free credits and your own key: {exc.signup_url}")
        else:
            lines.append("Top up credits: https://anakin.io/pricing")
    elif isinstance(exc, anakin.RateLimitError):
        wait = f" {exc.retry_after:g}s" if exc.retry_after else " a few seconds"
        lines.append(f"Rate limited. Wait{wait} and retry.")
    elif isinstance(exc, anakin.JobTimeoutError) and exc.job_id:
        lines.append(
            f"The job is still running. Increase --timeout, or fetch it later: "
            f"anakin job get <type> {exc.job_id}"
        )
    elif isinstance(exc, anakin.JobFailedError) and exc.job_id:
        lines.append(f"Job ID: {exc.job_id}")
    return lines
