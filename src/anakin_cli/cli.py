#!/usr/bin/env python3
"""Anakin CLI — single entry point for all Anakin API commands.

Usage:
    anakin search "query" [-l LIMIT] [-o OUTPUT]
    anakin scrape <url> [--format markdown|json|raw] [--browser] [--country CC] [--session-id ID] [-o OUTPUT]
    anakin scrape-batch <url1> <url2> ... [--browser] [-o OUTPUT]
    anakin research "query" [-o OUTPUT] [--timeout SECS]
    anakin login --api-key KEY
    anakin status
"""

import argparse
import sys

from anakin_cli import __version__
from anakin_cli.auth import get_api_key, require_api_key, save_api_key
from anakin_cli.client import AnakinClient
from anakin_cli.poller import poll_job
from anakin_cli.utils import AnakinError, log, log_error, log_success, log_warning, output_result


# ---------------------------------------------------------------------------
# API URL resolution helpers
# ---------------------------------------------------------------------------

def resolve_api_url(args) -> str:
    """Resolve API URL: --api-url flag > ANAKIN_API_URL env > config > default."""
    import os
    if args.api_url:
        url = args.api_url
        # Ensure /v1 suffix
        if not url.rstrip("/").endswith("/v1"):
            url = url.rstrip("/") + "/v1"
        return url
    env_url = os.environ.get("ANAKIN_API_URL")
    if env_url:
        if not env_url.rstrip("/").endswith("/v1"):
            env_url = env_url.rstrip("/") + "/v1"
        return env_url
    from anakin_cli.auth import load_config
    config = load_config()
    config_url = config.get("api_url")
    if config_url:
        if not config_url.rstrip("/").endswith("/v1"):
            config_url = config_url.rstrip("/") + "/v1"
        return config_url
    return "https://api.anakin.io/v1"


def is_self_hosted(api_url: str) -> bool:
    """Check if the API URL points to a self-hosted instance."""
    return "localhost" in api_url or "127.0.0.1" in api_url or "0.0.0.0" in api_url


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_search(args):
    """Synchronous AI web search."""
    api_url = resolve_api_url(args)
    if is_self_hosted(api_url):
        log_warning("Search requires the Anakin hosted API.")
        log("Get a free API key at [bold]https://anakin.io/dashboard[/bold]")
        log("Then run: [bold]anakin login --api-key 'ak-xxx'[/bold]")
        sys.exit(0)
    client = AnakinClient(require_api_key(), base_url=api_url)
    result = client.search(args.query, limit=args.limit)
    output_result(result, args.output)


def cmd_scrape(args):
    """Scrape a single URL (async with polling)."""
    api_url = resolve_api_url(args)
    if is_self_hosted(api_url):
        api_key = get_api_key()  # None is OK for self-hosted
    else:
        api_key = require_api_key()
    client = AnakinClient(api_key, base_url=api_url)
    use_extract = args.format == "json"
    job = client.start_url_scrape(
        args.url,
        country=args.country,
        use_browser=args.browser,
        generate_json=use_extract,
        session_id=args.session_id,
    )
    job_id = job.get("jobId") or job.get("job_id") or job.get("id")
    result = poll_job(
        client.get_url_scrape_result,
        job_id,
        poll_interval=3.0,
        timeout=args.timeout,
    )

    if args.format == "markdown":
        # Clean page text only
        output_result(result.get("markdown", ""), args.output, fmt="text")
    elif args.format == "json":
        # AI-extracted structured data only
        extracted = result.get("generatedJson") or result.get("generated_json") or {}
        output_result(extracted, args.output)
    elif args.format == "raw":
        # Full API response as-is
        output_result(result, args.output)


def cmd_scrape_batch(args):
    """Scrape multiple URLs at once (async with polling)."""
    api_url = resolve_api_url(args)
    if is_self_hosted(api_url):
        api_key = get_api_key()  # None is OK for self-hosted
    else:
        api_key = require_api_key()
    client = AnakinClient(api_key, base_url=api_url)
    if len(args.urls) > 10:
        log_warning("Batch endpoint supports max 10 URLs. Truncating.")
        args.urls = args.urls[:10]
    job = client.start_batch_scrape(
        args.urls,
        country=args.country,
        use_browser=args.browser,
    )
    job_id = job.get("jobId") or job.get("job_id") or job.get("id")
    result = poll_job(
        client.get_url_scrape_result,
        job_id,
        poll_interval=3.0,
        timeout=args.timeout,
    )
    output_result(result, args.output)


def cmd_research(args):
    """Deep agentic research (async, may take 1-5 minutes)."""
    api_url = resolve_api_url(args)
    if is_self_hosted(api_url):
        log_warning("Research requires the Anakin hosted API.")
        log("Get a free API key at [bold]https://anakin.io/dashboard[/bold]")
        log("Then run: [bold]anakin login --api-key 'ak-xxx'[/bold]")
        sys.exit(0)
    client = AnakinClient(require_api_key(), base_url=api_url)
    log("Starting agentic search (this may take 1-5 minutes)...")
    job = client.start_agentic_search(args.query)
    job_id = job.get("job_id") or job.get("jobId") or job.get("id")
    result = poll_job(
        client.get_agentic_search_result,
        job_id,
        poll_interval=10.0,
        timeout=args.timeout,
    )
    output_result(result, args.output)


def cmd_login(args):
    """Save API key to ~/.anakin/config.json."""
    save_api_key(args.api_key)
    log_success("API key saved to ~/.anakin/config.json")
    log("You can now run: [bold]anakin status[/bold]")


def cmd_status(_args):
    """Print version and authentication status."""
    import os
    from anakin_cli.utils import console

    console.print(f"[bold]anakin-cli[/bold] v{__version__}")
    key = get_api_key()
    if key:
        source = "ANAKIN_API_KEY env var" if os.environ.get("ANAKIN_API_KEY") else "~/.anakin/config.json"
        masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
        log_success(f"Authenticated: {masked} (from {source})")
    else:
        log_warning("Not authenticated. Run: [bold]anakin login --api-key 'ak-xxx'[/bold]")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anakin",
        description="Anakin.io web scraping, search, and research CLI",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--api-url", default=None, help="API base URL (default: https://api.anakin.io/v1). Use http://localhost:8080/v1 for self-hosted.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _api_url_help = "API base URL (default: https://api.anakin.io/v1). Use http://localhost:8080 for self-hosted."

    # --- search ---
    p_search = subparsers.add_parser("search", help="AI web search (sync)")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("-l", "--limit", type=int, default=5, help="Max results (default: 5)")
    p_search.add_argument("-o", "--output", help="Output file path")
    p_search.add_argument("--api-url", default=None, help=_api_url_help)
    p_search.set_defaults(func=cmd_search)

    # --- scrape ---
    p_scrape = subparsers.add_parser("scrape", help="Scrape a single URL")
    p_scrape.add_argument("url", help="URL to scrape")
    p_scrape.add_argument("--browser", action="store_true", help="Use headless browser")
    p_scrape.add_argument("--country", default="us", help="Country code (default: us)")
    p_scrape.add_argument("--session-id", default=None, help="Session ID for authenticated scraping")
    p_scrape.add_argument("--format", choices=["markdown", "json", "raw"], default="markdown", help="markdown=page text, json=AI-extracted data, raw=full API response (default: markdown)")
    p_scrape.add_argument("--timeout", type=float, default=120, help="Polling timeout in seconds (default: 120)")
    p_scrape.add_argument("-o", "--output", help="Output file path")
    p_scrape.add_argument("--api-url", default=None, help=_api_url_help)
    p_scrape.set_defaults(func=cmd_scrape)

    # --- scrape-batch ---
    p_batch = subparsers.add_parser("scrape-batch", help="Scrape multiple URLs")
    p_batch.add_argument("urls", nargs="+", help="URLs to scrape (max 10)")
    p_batch.add_argument("--browser", action="store_true", help="Use headless browser")
    p_batch.add_argument("--country", default="us", help="Country code (default: us)")
    p_batch.add_argument("--timeout", type=float, default=180, help="Polling timeout in seconds (default: 180)")
    p_batch.add_argument("-o", "--output", help="Output file path")
    p_batch.add_argument("--api-url", default=None, help=_api_url_help)
    p_batch.set_defaults(func=cmd_scrape_batch)

    # --- research ---
    p_research = subparsers.add_parser("research", help="Deep agentic research (1-5 min)")
    p_research.add_argument("query", help="Research query/topic")
    p_research.add_argument("--timeout", type=float, default=600, help="Polling timeout in seconds (default: 600)")
    p_research.add_argument("-o", "--output", help="Output file path")
    p_research.add_argument("--api-url", default=None, help=_api_url_help)
    p_research.set_defaults(func=cmd_research)

    # --- login ---
    p_login = subparsers.add_parser("login", help="Save API key")
    p_login.add_argument("--api-key", required=True, help="Anakin API key (ak-xxx)")
    p_login.set_defaults(func=cmd_login)

    # --- status ---
    p_status = subparsers.add_parser("status", help="Show version and auth status")
    p_status.set_defaults(func=cmd_status)

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except AnakinError as exc:
        log_error(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        log("\n[dim]Aborted.[/dim]")
        sys.exit(130)


if __name__ == "__main__":
    main()
