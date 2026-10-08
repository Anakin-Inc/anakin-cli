# Anakin CLI

[![PyPI version](https://img.shields.io/pypi/v/anakin-cli)](https://pypi.org/project/anakin-cli/)
[![Python](https://img.shields.io/pypi/pyversions/anakin-cli)](https://pypi.org/project/anakin-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Command-line interface for [Anakin.io](https://anakin.io): scrape and crawl websites, run pre-built **Wire** actions on hundreds of sites, search, research, monitor pages for changes, and compare what AI engines say. Built on the official [`anakin-sdk`](https://github.com/Anakin-Inc/anakin-py).

## Requirements

- Python 3.10 or higher
- An Anakin API key for most commands ([get one free, 300 credits](https://anakin.io/signup)). `scrape` and `wire discover` also work without one.

## Install

```bash
pip install anakin-cli
```

## Quick Start

```bash
# No key needed: scrape a page, find a Wire action
anakin scrape "https://example.com"
anakin wire discover "top phones on walmart"

# Authenticate for everything else
anakin login --api-key "ak-your-key-here"
anakin status

# Wire: structured data from a known site
anakin wire catalog walmart
anakin wire run walmart_search -p query=phones -p limit=5

# Scrape, batch, map, crawl
anakin scrape "https://example.com/product" --format json -o product.json
anakin scrape-batch "https://a.com" "https://b.com" -o batch.json
anakin map "https://docs.example.com" --links-only
anakin crawl "https://docs.example.com" --max-pages 50 --include "/guides/*" -o site.json

# Search and deep research (1-5 minutes)
anakin search "python async best practices"
anakin research "comparison of vector databases" -o report.json

# Monitor a page; compare AI engine answers
anakin monitor create "https://example.com/pricing" --interval 60 --ai
anakin ai-visibility search "best web scraping api"
```

Every command prints JSON (or plain text for page content) to stdout, and progress to stderr, so piping works:

```bash
anakin wire run hn_stories -p limit=5 | jq '.[0].title'
```

## Commands

| Command | Description |
|---------|-------------|
| `scrape` | Scrape one URL: markdown, html, AI-extracted JSON, links, summary or raw. `--schema`, `--actions`, `--screenshot FILE`. Works without a key. |
| `scrape-batch` | Scrape up to 10 URLs at once |
| `map` | Discover URLs on a site |
| `crawl` | Crawl a site and return each page's markdown |
| `search` | AI web search (instant) |
| `research` | Deep agentic research (1-5 min), optional `--schema` |
| `job get <type> <id>` | Fetch any async job (scrape, batch, map, crawl, research, wire, ai-visibility) |
| `wire discover / catalogs / catalog` | Find Wire actions (no key needed) |
| `wire run <action_id>` | Run an action: `-p key=value`, `--params @file.json`, `--credential-id`, `--zero-touch` |
| `wire identities / login / download` | Site accounts, sign-in (password prompted, never stored), file results |
| `wire build / build-status` | Request actions for a site not in the catalog |
| `monitor create / list / pause / resume / run / changes / snapshots / deliveries / test-alert / delete` | Website monitoring (page, site or Wire scope) |
| `ai-visibility search / sources / list` | Ask ChatGPT, Gemini and Google AI Overview the same question |
| `webhooks list / create / delete / test / deliveries / events / secret` | Webhook endpoints and delivery log |
| `sessions list / delete` | Saved browser login sessions |
| `login` / `status` | Save your key; show version, API URL and auth status |

Run `anakin <command> --help` for every option.

## Scrape Formats

| `--format` | What you get |
|--------|-------------|
| `markdown` (default) | Clean readable page text |
| `json` | AI-extracted structured data (add `--schema` to choose the fields) |
| `html` | Raw HTML |
| `links` | `[{href, text}]` |
| `summary` | AI summary of the page |
| `raw` | The full result object |

```bash
--browser            # Headless browser (JS-heavy sites)
--country CC         # Proxy country (default: us)
--session-id ID      # Saved browser session (login-protected pages)
--actions JSON       # Click/scroll/type before capture
--screenshot FILE    # Also save a PNG
--fresh              # Skip the cache
--timeout SECS       # Max wait (default: 120)
-o, --output FILE    # Save output to a file
```

## Self-Hosted Mode

Point the CLI at a self-hosted AnakinScraper instance (no API key needed):

```bash
anakin scrape "https://example.com" --api-url http://localhost:8080
# or
export ANAKIN_API_URL="http://localhost:8080"
```

Self-hosted mode supports `scrape`, `scrape-batch`, `map` and `crawl`. Search, research, Wire and AI visibility need the hosted API.

## Authentication

Get a free API key (300 credits) at [anakin.io/signup](https://anakin.io/signup).

**Option A** — Login command (recommended):
```bash
anakin login --api-key "ak-your-key-here"
```

**Option B** — Environment variable:
```bash
export ANAKIN_API_KEY="ak-your-key-here"
```

Without a key, `scrape` and `wire discover`/`catalogs`/`catalog` use the free keyless tier. Other commands prompt for a key when run in a terminal.

## Error Handling

Errors print a one-line reason plus a hint, and exit non-zero:

| Error | Fix shown |
|-------|-----|
| `401` invalid key | `anakin login --api-key ...` |
| `402` out of credits / keyless tier unavailable | Top-up or signup link |
| Wire `AUTH_REQUIRED` | The URL to connect the site account |
| Wire `AUTH_EXPIRED` | Run `anakin wire login` again |
| `429` rate limited | How long to wait |
| Job timed out | Raise `--timeout`, or `anakin job get <type> <id>` later |

Exit codes: `0` success, `1` API/job error, `2` bad arguments or input files, `130` interrupted.

## Tips

- **Always quote URLs** that contain `?`, `&`, or `#` — shells like zsh interpret these as special characters:
  ```bash
  # Wrong — zsh will fail with "no matches found"
  anakin scrape https://example.com/page?id=123

  # Correct
  anakin scrape "https://example.com/page?id=123"
  ```
- Use `--browser` for JavaScript-heavy sites (SPAs, dynamic content).
- Use `-o` to save output to a file. Without it, output goes to stdout.
- All progress/status messages go to stderr, so piping works cleanly:
  ```bash
  anakin scrape "https://example.com" --format raw | jq '.links'
  ```

## Documentation

- [API Docs](https://anakin.io/docs) — full endpoint reference
- [LLM-friendly docs](https://anakin.io/llms-full.txt) — plain text docs optimized for AI/LLM consumption

## Support

- Discord: [discord.gg/gP2YCJKH](https://discord.gg/gP2YCJKH)
- Email: [support@anakin.io](mailto:support@anakin.io)

## License

MIT
