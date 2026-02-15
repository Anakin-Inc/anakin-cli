"""Generic async job polling logic for Anakin API."""

import time
from typing import Callable

from anakin_cli.utils import (
    AnakinJobFailedError,
    AnakinTimeoutError,
    console,
    log_success,
)

TERMINAL_STATUSES = {"completed", "failed"}


def poll_job(
    fetch_fn: Callable[[str], dict],
    job_id: str,
    *,
    poll_interval: float = 3.0,
    timeout: float = 120.0,
    show_progress: bool = True,
) -> dict:
    """Poll an async job until it reaches a terminal status.

    Parameters
    ----------
    fetch_fn :
        Callable that takes a *job_id* and returns the job dict
        (e.g. ``client.get_url_scrape_result``).
    job_id :
        The job identifier returned by the start endpoint.
    poll_interval :
        Seconds between poll requests.
    timeout :
        Maximum seconds to wait before raising ``AnakinTimeoutError``.
    show_progress :
        If ``True``, show a spinner on stderr.

    Returns
    -------
    dict
        The final job payload (status == "completed").

    Raises
    ------
    AnakinJobFailedError
        If the job finishes with ``status == "failed"``.
    AnakinTimeoutError
        If *timeout* is exceeded.
    """
    start = time.monotonic()

    if show_progress:
        with console.status(
            f"[bold blue]Polling job {job_id}[/bold blue]",
            spinner="dots",
        ) as status:
            return _poll_loop(fetch_fn, job_id, poll_interval, timeout, start, status)
    else:
        return _poll_loop(fetch_fn, job_id, poll_interval, timeout, start, None)


def _poll_loop(fetch_fn, job_id, poll_interval, timeout, start, status):
    """Internal polling loop shared by spinner and non-spinner paths."""
    while True:
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            raise AnakinTimeoutError(
                f"Job {job_id} did not complete within {timeout}s"
            )

        result = fetch_fn(job_id)
        job_status = result.get("status", "unknown")

        if status is not None:
            status.update(
                f"[bold blue]Polling job {job_id}[/bold blue]  "
                f"[dim]{elapsed:.0f}s elapsed — status: {job_status}[/dim]"
            )

        if job_status == "completed":
            if status is not None:
                log_success(f"Job {job_id} completed in {elapsed:.1f}s")
            return result

        if job_status == "failed":
            error_msg = result.get("error", "No error details provided")
            raise AnakinJobFailedError(
                f"Job {job_id} failed: {error_msg}"
            )

        if job_status not in TERMINAL_STATUSES:
            time.sleep(poll_interval)
