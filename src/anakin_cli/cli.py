"""Anakin CLI: one command for the whole Anakin API, built on the anakin-sdk.

Examples:
    anakin scrape "https://example.com"                    # works without a key
    anakin wire discover "top phones on walmart"
    anakin wire run walmart_search -p query=phones
    anakin crawl "https://docs.example.com" --max-pages 50 -o site.json
    anakin research "compare vector databases" -o report.json
    anakin monitor create "https://example.com/pricing" --interval 60
    anakin ai-visibility search "best web scraping api"

Run `anakin <command> --help` for every option.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anakin
from anakin import Anakin

from anakin_cli import __version__
from anakin_cli.auth import get_api_key, load_config, require_api_key, save_api_key
from anakin_cli.utils import (
    CLIError,
    console,
    describe_error,
    log,
    log_error,
    log_success,
    log_warning,
    output_bytes,
    output_result,
    spinner,
)

DEFAULT_API_URL = "https://api.anakin.io/v1"

# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def resolve_api_url(args: argparse.Namespace) -> str:
    """Resolve API URL: --api-url flag > ANAKIN_API_URL env > config > default."""
    url = (
        getattr(args, "api_url", None)
        or os.environ.get("ANAKIN_API_URL")
        or load_config().get("api_url")
        or DEFAULT_API_URL
    )
    url = str(url).rstrip("/")
    return url if url.endswith("/v1") else f"{url}/v1"


def is_self_hosted(api_url: str) -> bool:
    """True when the API URL points at a self-hosted AnakinScraper instance."""
    from urllib.parse import urlsplit

    host = urlsplit(api_url).hostname or ""
    return not (host == "anakin.io" or host.endswith(".anakin.io"))


def make_client(args: argparse.Namespace, *, needs_key: bool = True, timeout: float | None = None) -> Anakin:
    """
    Build an SDK client.

    needs_key=False lets the command run keyless on the hosted API (Zero Touch:
    scrape and Wire discovery). Self-hosted instances never need a key.
    """
    api_url = resolve_api_url(args)
    keyless_ok = is_self_hosted(api_url) or not needs_key
    api_key = get_api_key() if keyless_ok else require_api_key()
    kwargs: dict[str, Any] = {"api_key": api_key, "base_url": api_url}
    if timeout is not None:
        kwargs["poll_timeout"] = timeout
    if api_key is None and not is_self_hosted(api_url):
        log("[dim]No API key: using the free keyless tier.[/dim]")
    return Anakin(**kwargs)


def hosted_only(args: argparse.Namespace, feature: str) -> None:
    """Exit with a helpful message if *feature* is used against a self-hosted URL."""
    if is_self_hosted(resolve_api_url(args)):
        log_warning(f"{feature} requires the Anakin hosted API.")
        log("Get a free API key at [bold]https://anakin.io/signup[/bold]")
        log("Then run: [bold]anakin login --api-key 'ak-xxx'[/bold]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argument value helpers
# ---------------------------------------------------------------------------


def load_json_arg(value: str | None, flag: str) -> Any:
    """Parse a JSON flag value given inline or as @file.json."""
    if value is None:
        return None
    text = value
    if value.startswith("@"):
        try:
            text = Path(value[1:]).read_text(encoding="utf-8")
        except OSError as exc:
            raise CLIError(f"{flag}: cannot read {value[1:]}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CLIError(f"{flag}: invalid JSON ({exc.msg})") from exc


def parse_params(pairs: list[str] | None, raw: str | None) -> dict[str, Any]:
    """Merge --params JSON with repeated -p key=value (values parsed as JSON when possible)."""
    params: dict[str, Any] = {}
    loaded = load_json_arg(raw, "--params")
    if loaded is not None:
        if not isinstance(loaded, dict):
            raise CLIError("--params must be a JSON object")
        params.update(loaded)
    for pair in pairs or []:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise CLIError(f"-p expects key=value, got {pair!r}")
        try:
            params[key] = json.loads(value)
        except json.JSONDecodeError:
            params[key] = value
    return params


def split_csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


# ---------------------------------------------------------------------------
# Scrape / map / crawl / search / research
# ---------------------------------------------------------------------------

SCRAPE_FORMATS = {
    "markdown": ["markdown"],
    "html": ["html"],
    "json": ["markdown"],
    "links": ["links"],
    "summary": ["summary"],
    "raw": ["markdown", "html", "cleanedHtml", "links", "images"],
}


def cmd_scrape(args: argparse.Namespace) -> None:
    """Scrape a single URL."""
    client = make_client(args, needs_key=False, timeout=args.timeout)
    schema = load_json_arg(args.schema, "--schema")
    formats = list(SCRAPE_FORMATS[args.format])
    if args.screenshot:
        formats.append("screenshot")
    actions = load_json_arg(args.actions, "--actions")
    with spinner(f"Scraping {args.url}"):
        doc = client.scrape(
            args.url,
            formats=formats,  # type: ignore[arg-type]
            country=args.country,
            use_browser=args.browser,
            generate_json=args.format == "json" or schema is not None,
            output_schema=schema,
            actions=actions,
            force_fresh=args.fresh,
            session_id=args.session_id,
            session_name=args.session_name,
        )
    if doc.trial and doc.trial.remaining_credits is not None:
        log(f"[dim]Free credits left: {doc.trial.remaining_credits}[/dim]")

    if args.format == "markdown":
        output_result(doc.markdown or "", args.output, fmt="text")
    elif args.format == "html":
        output_result(doc.html or "", args.output, fmt="text")
    elif args.format == "summary":
        output_result(doc.summary or "", args.output, fmt="text")
    elif args.format == "json":
        output_result(doc.generated_json or {}, args.output)
    elif args.format == "links":
        output_result(doc.links or [], args.output)
    else:
        output_result(doc, args.output)

    if args.screenshot:
        output_bytes(client.download_screenshot(doc.id), args.screenshot)


def cmd_scrape_batch(args: argparse.Namespace) -> None:
    """Scrape up to 10 URLs in one job."""
    client = make_client(args, timeout=args.timeout)
    urls = args.urls
    if len(urls) > 10:
        log_warning("Batch scraping supports max 10 URLs. Truncating.")
        urls = urls[:10]
    with spinner(f"Scraping {len(urls)} URLs"):
        result = client.scrape_batch(
            urls,
            country=args.country,
            use_browser=args.browser,
            generate_json=args.json,
            session_id=args.session_id,
        )
    failed = [r for r in result.results if r.status != "completed"]
    if failed:
        log_warning(f"{len(failed)} of {len(result.results)} URLs failed")
    output_result(result, args.output)


def cmd_map(args: argparse.Namespace) -> None:
    """Discover URLs on a site."""
    client = make_client(args, timeout=args.timeout)
    with spinner(f"Mapping {args.url}"):
        result = client.map(
            args.url,
            limit=args.limit,
            depth=args.depth,
            search=args.search,
            include_subdomains=args.subdomains,
            include_external_links=args.external,
            use_browser=args.browser,
            session_id=args.session_id,
        )
    if args.links_only:
        output_result("\n".join(result.links), args.output, fmt="text")
    else:
        output_result(result, args.output)


def cmd_crawl(args: argparse.Namespace) -> None:
    """Crawl a site and return each page's markdown."""
    client = make_client(args, timeout=args.timeout)
    with spinner(f"Crawling {args.url}"):
        result = client.crawl(
            args.url,
            max_pages=args.max_pages,
            depth=args.depth,
            include_patterns=args.include or (),
            exclude_patterns=args.exclude or (),
            country=args.country,
            use_browser=args.browser,
            session_id=args.session_id,
            session_name=args.session_name,
        )
    log_success(f"Crawled {result.completed_pages}/{result.total_pages} pages")
    output_result(result, args.output)


def cmd_search(args: argparse.Namespace) -> None:
    """Synchronous AI web search."""
    hosted_only(args, "Search")
    client = make_client(args)
    with spinner("Searching"):
        result = client.search(args.query, limit=args.limit)
    output_result(result, args.output)


def cmd_research(args: argparse.Namespace) -> None:
    """Deep agentic research (1-5 minutes)."""
    hosted_only(args, "Research")
    client = make_client(args, timeout=args.timeout)
    schema = load_json_arg(args.schema, "--schema")
    log("Starting agentic search (this may take 1-5 minutes)...")
    with spinner("Researching"):
        result = client.agentic_search(args.query, schema=schema, use_browser=not args.no_browser)
    output_result(result, args.output)


JOB_GETTERS: dict[str, Callable[[Anakin, str], Any]] = {
    "scrape": lambda c, i: c.get_scrape(i),
    "batch": lambda c, i: c.get_scrape_batch(i),
    "map": lambda c, i: c.get_map(i),
    "crawl": lambda c, i: c.get_crawl(i),
    "research": lambda c, i: c.get_agentic_search(i),
    "wire": lambda c, i: c.wire.get_job(i),
    "ai-visibility": lambda c, i: c.ai_visibility.get(i),
}


def cmd_job_get(args: argparse.Namespace) -> None:
    """Fetch any async job by type and ID."""
    client = make_client(args)
    output_result(JOB_GETTERS[args.type](client, args.job_id), args.output)


# ---------------------------------------------------------------------------
# Wire
# ---------------------------------------------------------------------------


def cmd_wire_discover(args: argparse.Namespace) -> None:
    hosted_only(args, "Wire")
    client = make_client(args, needs_key=False)
    matches = client.wire.discover(
        args.query,
        catalog=args.catalog,
        category=args.category,
        auth_mode=args.auth_mode,
        limit=args.limit,
    )
    output_result(matches, args.output)


def cmd_wire_catalogs(args: argparse.Namespace) -> None:
    hosted_only(args, "Wire")
    client = make_client(args, needs_key=False)
    catalogs = client.wire.catalogs(scope=args.scope)
    if args.category:
        catalogs = [c for c in catalogs if c.category == args.category]
    output_result(catalogs, args.output)


def cmd_wire_catalog(args: argparse.Namespace) -> None:
    hosted_only(args, "Wire")
    client = make_client(args, needs_key=False)
    output_result(client.wire.catalog(args.slug), args.output)


def cmd_wire_run(args: argparse.Namespace) -> None:
    hosted_only(args, "Wire")
    params = parse_params(args.param, args.params)
    if args.zero_touch:
        client = make_client(args, needs_key=False)
        with spinner(f"Running {args.action_id}"):
            result = client.wire.zero_touch(args.action_id, params)
    else:
        client = make_client(args, timeout=args.timeout)
        with spinner(f"Running {args.action_id}"):
            result = client.wire.run(
                args.action_id,
                params,
                credential_id=args.credential_id,
                identity_id=args.identity_id,
                webhook_url=args.webhook_url,
                wait=not args.no_wait,
            )
    if result.credits_used:
        log(f"[dim]credits used: {result.credits_used}[/dim]")
    if result.files:
        names = ", ".join(f.name for f in result.files)
        log(f"Files: {names}. Download with: anakin wire download {result.job_id} -o FILE")
    output_result(result if args.full else result.data, args.output)


def cmd_wire_download(args: argparse.Namespace) -> None:
    client = make_client(args)
    output_bytes(client.wire.download(args.job_id, file=args.file), args.output)


def cmd_wire_identities(args: argparse.Namespace) -> None:
    client = make_client(args)
    output_result(client.wire.identities(catalog_id=args.catalog_id), args.output)


def cmd_wire_login(args: argparse.Namespace) -> None:
    client = make_client(args)
    params = parse_params(args.param, args.params)
    if "password" not in params and sys.stdin.isatty() and not args.source_id:
        params["password"] = console.input("[bold]Password:[/bold] ", password=True)
    result = client.wire.login(
        args.catalog_slug,
        params or None,
        identity_name=args.identity_name,
        source_id=args.source_id,
        source_ref=load_json_arg(args.source_ref, "--source-ref"),
    )
    log_success(f"Signed in. credential_id={result.credential_id}")
    output_result(result, args.output)


def cmd_wire_build(args: argparse.Namespace) -> None:
    client = make_client(args)
    build = client.wire.build(
        args.website_url,
        args.goal,
        actions=split_csv(args.actions),
        country=args.country,
        visibility=args.visibility,
        force=args.force,
    )
    log_success(
        f"Build requested ({build.credits_charged} credits held). Track: anakin wire build-status {build.id}"
    )
    output_result(build, args.output)


def cmd_wire_build_status(args: argparse.Namespace) -> None:
    client = make_client(args)
    if args.build_id:
        output_result(client.wire.get_build(args.build_id), args.output)
    else:
        output_result(client.wire.builds(status=args.status, limit=args.limit), args.output)


# ---------------------------------------------------------------------------
# Monitors
# ---------------------------------------------------------------------------


def _monitor_options(args: argparse.Namespace) -> dict[str, Any]:
    options: dict[str, Any] = {
        "scope": args.scope,
        "watch_mode": "specific_data" if args.schema else None,
        "output_schema": load_json_arg(args.schema, "--schema"),
        "watch_format": args.watch_format,
        "ai_mode": True if args.ai else None,
        "ai_goal": args.ai_goal,
        "use_browser": True if args.browser else None,
        "country": args.country,
        "session_id": args.session_id,
        "expires_at": args.expires_at,
        "alert_webhook_url": args.webhook_url,
        "alert_emails": args.emails,
        "max_pages": args.max_pages,
        "include_patterns": args.include,
        "exclude_patterns": args.exclude,
        "wire_action_id": args.wire_action_id,
        "wire_params": parse_params(args.param, None) or None,
        "is_active": False if args.paused else None,
    }
    return {k: v for k, v in options.items() if v is not None}


def cmd_monitor_create(args: argparse.Namespace) -> None:
    client = make_client(args)
    monitor = client.monitors.create(args.url, args.interval, **_monitor_options(args))
    log_success(f"Monitor {monitor.id} created ({monitor.credit_cost_per_run} credits/check)")
    if monitor.alert_webhook_secret:
        log_warning(f"Store this webhook secret now: {monitor.alert_webhook_secret}")
    output_result(monitor, args.output)


def cmd_monitor_list(args: argparse.Namespace) -> None:
    client = make_client(args)
    if args.monitor_id:
        output_result(client.monitors.get(args.monitor_id), args.output)
    else:
        output_result(client.monitors.list(), args.output)


def cmd_monitor_control(args: argparse.Namespace) -> None:
    client = make_client(args)
    actions: dict[str, Callable[[str], Any]] = {
        "pause": client.monitors.pause,
        "resume": client.monitors.resume,
        "run": client.monitors.run_now,
        "changes": client.monitors.changes,
        "snapshots": client.monitors.snapshots,
        "deliveries": client.monitors.deliveries,
        "test-alert": client.monitors.test_alert,
    }
    output_result(actions[args.monitor_command](args.monitor_id), args.output)


def cmd_monitor_delete(args: argparse.Namespace) -> None:
    client = make_client(args)
    if not args.yes and sys.stdin.isatty():
        answer = console.input(f"Delete monitor {args.monitor_id} and all its history? [y/N] ")
        if answer.strip().lower() != "y":
            log("Aborted.")
            return
    client.monitors.delete(args.monitor_id)
    log_success(f"Deleted monitor {args.monitor_id}")


# ---------------------------------------------------------------------------
# AI visibility, webhooks, sessions
# ---------------------------------------------------------------------------


def cmd_ai_search(args: argparse.Namespace) -> None:
    hosted_only(args, "AI Visibility")
    client = make_client(args, timeout=args.timeout)
    with spinner("Asking AI engines"):
        result = client.ai_visibility.search(
            args.query, sources=split_csv(args.sources), country=args.country
        )
    if not args.full_content:
        for r in result.results:
            r.full_content = None
    output_result(result, args.output)


def cmd_ai_sources(args: argparse.Namespace) -> None:
    output_result(make_client(args).ai_visibility.sources(), args.output)


def cmd_ai_list(args: argparse.Namespace) -> None:
    output_result(make_client(args).ai_visibility.list(), args.output)


def cmd_webhooks(args: argparse.Namespace) -> None:
    client = make_client(args)
    sub = args.webhooks_command
    if sub == "list":
        output_result(client.webhooks.list(), args.output)
    elif sub == "create":
        endpoint = client.webhooks.create(
            args.url, description=args.description, events=split_csv(args.events)
        )
        log_warning(f"Store this signing secret now: {endpoint.secret}")
        output_result(endpoint, args.output)
    elif sub == "delete":
        client.webhooks.delete(args.endpoint_id)
        log_success(f"Deleted endpoint {args.endpoint_id}")
    elif sub == "test":
        output_result(client.webhooks.test(args.endpoint_id), args.output)
    elif sub == "deliveries":
        output_result(
            client.webhooks.deliveries(
                endpoint_id=args.endpoint_id, status=args.status, job_id=args.job_id, limit=args.limit
            ),
            args.output,
        )
    elif sub == "events":
        output_result(client.webhooks.events(), args.output)
    elif sub == "secret":
        output_result({"secret": client.webhooks.signing_secret()}, args.output)


def cmd_sessions(args: argparse.Namespace) -> None:
    client = make_client(args)
    if args.sessions_command == "list":
        output_result(client.sessions.list(domain=args.domain), args.output)
    else:
        client.sessions.delete(args.session_id)
        log_success(f"Deleted session {args.session_id}")


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


def cmd_login(args: argparse.Namespace) -> None:
    """Save API key to ~/.anakin/config.json."""
    save_api_key(args.api_key)
    log_success("API key saved to ~/.anakin/config.json")
    log("You can now run: [bold]anakin status[/bold]")


def cmd_status(args: argparse.Namespace) -> None:
    """Print version, API URL and authentication status."""
    console.print(f"[bold]anakin-cli[/bold] v{__version__} (anakin-sdk v{anakin.__version__})")
    api_url = resolve_api_url(args)
    mode = "self-hosted" if is_self_hosted(api_url) else "hosted"
    console.print(f"API: {api_url} ({mode})")
    key = get_api_key()
    if key:
        source = "ANAKIN_API_KEY env var" if os.environ.get("ANAKIN_API_KEY") else "~/.anakin/config.json"
        masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
        log_success(f"Authenticated: {masked} (from {source})")
    else:
        log_warning(
            "No API key: scrape and Wire discovery work on the free keyless tier. "
            "For everything else: [bold]anakin login --api-key 'ak-xxx'[/bold]"
        )


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _common() -> argparse.ArgumentParser:
    """Flags every leaf command accepts. SUPPRESS keeps a global --api-url intact."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--api-url",
        default=argparse.SUPPRESS,
        help="API base URL (default: https://api.anakin.io/v1). Use http://localhost:8080 for self-hosted.",
    )
    common.add_argument("-o", "--output", default=None, help="Write output to this file")
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common()
    parser = argparse.ArgumentParser(
        prog="anakin",
        description="Anakin: scrape, crawl, search, Wire actions, monitoring and AI visibility.",
        epilog="No API key? `anakin scrape` and `anakin wire discover` work on the free keyless tier.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--api-url", default=None, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def leaf(
        group: Any, name: str, func: Callable[[argparse.Namespace], None], help_: str, **kw: Any
    ) -> argparse.ArgumentParser:
        p: argparse.ArgumentParser = group.add_parser(
            name, parents=[common], help=help_, description=help_, **kw
        )
        p.set_defaults(func=func)
        return p

    # --- scrape ---
    p = leaf(sub, "scrape", cmd_scrape, "Scrape a single URL (works without an API key)")
    p.add_argument("url")
    p.add_argument(
        "--format",
        choices=list(SCRAPE_FORMATS),
        default="markdown",
        help="markdown (default), html, json (AI-extracted data), links, summary, raw (full result)",
    )
    p.add_argument("--schema", help="JSON Schema for AI extraction (inline JSON or @file.json)")
    p.add_argument(
        "--actions", help='Browser actions before capture, e.g. \'[{"type":"click","selector":".more"}]\''
    )
    p.add_argument("--screenshot", metavar="FILE", help="Also save a PNG screenshot to FILE")
    p.add_argument("--browser", action="store_true", help="Use a headless browser (JS-heavy sites)")
    p.add_argument("--country", default="us", help="Proxy country code (default: us)")
    p.add_argument("--session-id", help="Saved browser session ID (login-protected pages)")
    p.add_argument("--session-name", help="Saved browser session name")
    p.add_argument("--fresh", action="store_true", help="Skip the cache")
    p.add_argument("--timeout", type=float, default=120, help="Seconds to wait (default: 120)")

    # --- scrape-batch ---
    p = leaf(sub, "scrape-batch", cmd_scrape_batch, "Scrape up to 10 URLs at once")
    p.add_argument("urls", nargs="+")
    p.add_argument("--json", action="store_true", help="Also AI-extract structured JSON")
    p.add_argument("--browser", action="store_true")
    p.add_argument("--country", default="us")
    p.add_argument("--session-id")
    p.add_argument("--timeout", type=float, default=180)

    # --- map ---
    p = leaf(sub, "map", cmd_map, "Discover URLs on a website")
    p.add_argument("url")
    p.add_argument("--limit", type=int, default=100, help="Max URLs (default 100, max 5000)")
    p.add_argument("--depth", type=int, default=2, help="Link hops (default 2, max 5)")
    p.add_argument("--search", help="Only URLs containing this string")
    p.add_argument("--subdomains", action="store_true", help="Include subdomains")
    p.add_argument("--external", action="store_true", help="Also collect external links")
    p.add_argument("--browser", action="store_true")
    p.add_argument("--session-id")
    p.add_argument("--links-only", action="store_true", help="Print one URL per line")
    p.add_argument("--timeout", type=float, default=180)

    # --- crawl ---
    p = leaf(sub, "crawl", cmd_crawl, "Crawl a website and return each page's markdown")
    p.add_argument("url")
    p.add_argument("--max-pages", type=int, default=10, help="Default 10, max 100")
    p.add_argument("--depth", type=int, default=1)
    p.add_argument("--include", action="append", metavar="GLOB", help="Only crawl matching URLs (repeatable)")
    p.add_argument("--exclude", action="append", metavar="GLOB", help="Skip matching URLs (repeatable)")
    p.add_argument("--browser", action="store_true")
    p.add_argument("--country", default="us")
    p.add_argument("--session-id")
    p.add_argument("--session-name")
    p.add_argument("--timeout", type=float, default=300)

    # --- search ---
    p = leaf(sub, "search", cmd_search, "AI web search (instant)")
    p.add_argument("query")
    p.add_argument("-l", "--limit", type=int, default=5, help="Max results (default 5, max 20)")

    # --- research ---
    p = leaf(sub, "research", cmd_research, "Deep agentic research (1-5 min)", aliases=["agentic-search"])
    p.add_argument("query")
    p.add_argument("--schema", help="JSON Schema for structured_data (inline JSON or @file.json)")
    p.add_argument("--no-browser", action="store_true", help="Don't render cited pages in a browser")
    p.add_argument("--timeout", type=float, default=600)

    # --- job ---
    jobs = sub.add_parser("job", help="Fetch an async job by ID").add_subparsers(
        dest="job_command", required=True
    )
    p = leaf(jobs, "get", cmd_job_get, "Fetch a job's status/result")
    p.add_argument("type", choices=list(JOB_GETTERS))
    p.add_argument("job_id")

    # --- wire ---
    wire = sub.add_parser("wire", help="Pre-built actions on hundreds of sites").add_subparsers(
        dest="wire_command", required=True, metavar="<wire command>"
    )
    p = leaf(wire, "discover", cmd_wire_discover, "Find actions by intent (no key needed)")
    p.add_argument("query")
    p.add_argument("--catalog", help="Restrict to one site slug")
    p.add_argument("--category")
    p.add_argument("--auth-mode", choices=["none", "optional", "required"])
    p.add_argument("--limit", type=int, default=10)

    p = leaf(wire, "catalogs", cmd_wire_catalogs, "List supported sites (no key needed)")
    p.add_argument("--scope", choices=["my", "global"])
    p.add_argument("--category")

    p = leaf(wire, "catalog", cmd_wire_catalog, "One site's actions, params and credit costs")
    p.add_argument("slug")

    p = leaf(wire, "run", cmd_wire_run, "Run a Wire action")
    p.add_argument("action_id")
    p.add_argument(
        "-p", "--param", action="append", metavar="KEY=VALUE", help="Action parameter (repeatable)"
    )
    p.add_argument("--params", help="All parameters as JSON (inline or @file.json)")
    p.add_argument("--credential-id", help="Required for auth_mode=required actions")
    p.add_argument("--identity-id")
    p.add_argument("--webhook-url")
    p.add_argument("--no-wait", action="store_true", help="Return the job ID immediately")
    p.add_argument("--zero-touch", action="store_true", help="Run read-only without an API key")
    p.add_argument("--full", action="store_true", help="Print the full result, not just data")
    p.add_argument("--timeout", type=float, default=300)

    p = leaf(wire, "download", cmd_wire_download, "Download a file produced by a Wire job")
    p.add_argument("job_id")
    p.add_argument("--file", help="File name, for multi-file results")

    p = leaf(wire, "identities", cmd_wire_identities, "List saved site accounts and credential IDs")
    p.add_argument("--catalog-id")

    p = leaf(wire, "login", cmd_wire_login, "Sign in to a site; prints a credential_id")
    p.add_argument("catalog_slug")
    p.add_argument(
        "-p",
        "--param",
        action="append",
        metavar="KEY=VALUE",
        help="Login field, e.g. -p email=me@x.com (password is prompted)",
    )
    p.add_argument("--params")
    p.add_argument("--identity-name")
    p.add_argument("--source-id", help="Identity source (vault) ID")
    p.add_argument("--source-ref", help="Vault locator JSON")

    p = leaf(
        wire, "build", cmd_wire_build, "Request new actions for a site not in the catalog (charges credits)"
    )
    p.add_argument("website_url")
    p.add_argument("goal")
    p.add_argument("--actions", help="Comma-separated capabilities to build")
    p.add_argument("--country")
    p.add_argument("--visibility", choices=["private", "public"])
    p.add_argument("--force", action="store_true")

    p = leaf(wire, "build-status", cmd_wire_build_status, "Show a build request, or list recent ones")
    p.add_argument("build_id", nargs="?")
    p.add_argument("--status")
    p.add_argument("--limit", type=int, default=10)

    # --- monitor ---
    mon = sub.add_parser("monitor", help="Website monitoring").add_subparsers(
        dest="monitor_command", required=True, metavar="<monitor command>"
    )
    p = leaf(mon, "create", cmd_monitor_create, "Watch a page/site/Wire action for changes")
    p.add_argument("url")
    p.add_argument("--interval", type=int, required=True, help="Minutes between checks (min 15)")
    p.add_argument("--scope", choices=["page", "site", "wire"])
    p.add_argument("--schema", help="Track only these fields (JSON Schema; enables specific_data mode)")
    p.add_argument("--watch-format", choices=["markdown", "html", "cleaned_html"])
    p.add_argument("--ai", action="store_true", help="AI noise filtering + summaries (+1 credit/check)")
    p.add_argument("--ai-goal", help='e.g. "only when the price drops"')
    p.add_argument("--webhook-url")
    p.add_argument("--emails", help="Comma-separated alert recipients")
    p.add_argument("--browser", action="store_true")
    p.add_argument("--country")
    p.add_argument("--session-id")
    p.add_argument("--expires-at", help="End date (YYYY-MM-DD or ISO 8601)")
    p.add_argument("--max-pages", type=int, help="Site scope: pages per run")
    p.add_argument("--include", action="append", metavar="GLOB")
    p.add_argument("--exclude", action="append", metavar="GLOB")
    p.add_argument("--wire-action-id", help="Wire scope: action to run each check")
    p.add_argument("-p", "--param", action="append", metavar="KEY=VALUE", help="Wire scope: action parameter")
    p.add_argument("--paused", action="store_true", help="Create without starting")

    p = leaf(mon, "list", cmd_monitor_list, "List monitors, or show one")
    p.add_argument("monitor_id", nargs="?")
    for name, help_ in [
        ("pause", "Pause scheduled checks"),
        ("resume", "Resume a paused monitor"),
        ("run", "Run a check now (billed)"),
        ("changes", "Detected changes"),
        ("snapshots", "Captured snapshots"),
        ("deliveries", "Alert delivery attempts"),
        ("test-alert", "Send a sample alert"),
    ]:
        leaf(mon, name, cmd_monitor_control, help_).add_argument("monitor_id")
    p = leaf(mon, "delete", cmd_monitor_delete, "Delete a monitor and its history")
    p.add_argument("monitor_id")
    p.add_argument("-y", "--yes", action="store_true", help="Don't ask for confirmation")

    # --- ai-visibility ---
    ai = sub.add_parser("ai-visibility", help="Compare ChatGPT, Gemini and Google AI answers").add_subparsers(
        dest="ai_command", required=True, metavar="<ai-visibility command>"
    )
    p = leaf(ai, "search", cmd_ai_search, "Ask AI engines the same question")
    p.add_argument("query")
    p.add_argument("--sources", help="Comma-separated engine slugs (default: all)")
    p.add_argument("--country", default="us")
    p.add_argument("--full-content", action="store_true", help="Include each engine's raw answer (large)")
    p.add_argument("--timeout", type=float, default=300)
    leaf(ai, "sources", cmd_ai_sources, "List available AI engines")
    leaf(ai, "list", cmd_ai_list, "Your 20 most recent searches")

    # --- webhooks ---
    wh = sub.add_parser("webhooks", help="Webhook endpoints and delivery log").add_subparsers(
        dest="webhooks_command", required=True, metavar="<webhooks command>"
    )
    leaf(wh, "list", cmd_webhooks, "List registered endpoints")
    p = leaf(wh, "create", cmd_webhooks, "Register an endpoint")
    p.add_argument("url")
    p.add_argument("--description")
    p.add_argument("--events", help="Comma-separated event filter (default: all)")
    leaf(wh, "delete", cmd_webhooks, "Delete an endpoint").add_argument("endpoint_id")
    leaf(wh, "test", cmd_webhooks, "Send a webhook.test event").add_argument("endpoint_id")
    p = leaf(wh, "deliveries", cmd_webhooks, "Recent deliveries")
    p.add_argument("--endpoint-id")
    p.add_argument("--status", choices=["pending", "success", "failed", "exhausted"])
    p.add_argument("--job-id")
    p.add_argument("--limit", type=int)
    leaf(wh, "events", cmd_webhooks, "List subscribable event types")
    leaf(wh, "secret", cmd_webhooks, "Show the default signing secret")

    # --- sessions ---
    ss = sub.add_parser("sessions", help="Saved browser login sessions").add_subparsers(
        dest="sessions_command", required=True, metavar="<sessions command>"
    )
    leaf(ss, "list", cmd_sessions, "List saved sessions").add_argument("--domain")
    leaf(ss, "delete", cmd_sessions, "Delete a saved session").add_argument("session_id")

    # --- account ---
    p = sub.add_parser("login", help="Save your API key")
    p.add_argument("--api-key", required=True, help="Anakin API key")
    p.set_defaults(func=cmd_login)
    leaf(sub, "status", cmd_status, "Show version, API URL and auth status")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except anakin.AnakinError as exc:
        headline, *hints = describe_error(exc)
        log_error(headline)
        for hint in hints:
            log(f"  {hint}")
        sys.exit(1)
    except CLIError as exc:
        log_error(str(exc))
        sys.exit(2)
    except KeyboardInterrupt:
        log("\n[dim]Aborted.[/dim]")
        sys.exit(130)


if __name__ == "__main__":
    main()
