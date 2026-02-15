# Anakin CLI

[![PyPI version](https://img.shields.io/pypi/v/anakin-cli)](https://pypi.org/project/anakin-cli/)
[![Python](https://img.shields.io/pypi/pyversions/anakin-cli)](https://pypi.org/project/anakin-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Command-line interface for [Anakin.io](https://anakin.io)'s web scraping, search, and research API.

## Requirements

- Python 3.10 or higher
- An Anakin API key ([get one here](https://anakin.io/dashboard))

## Install

```bash
pip install anakin-cli
```

## Quick Start

```bash
# Authenticate
anakin login --api-key "ak-your-key-here"

# Verify
anakin status

# Search the web
anakin search "python async best practices"

# Scrape a page to markdown
anakin scrape "https://example.com" -o page.md

# Extract structured data (AI-powered)
anakin scrape "https://example.com/product" --format json -o product.json

# Batch scrape multiple URLs
anakin scrape-batch "https://a.com" "https://b.com" -o batch.json

# Deep research (1-5 minutes)
anakin research "comparison of web frameworks 2025" -o report.json
```

## Commands

| Command | Description |
|---------|-------------|
| `search` | AI-powered web search (instant) |
| `scrape` | Scrape a single URL — markdown, JSON, or raw |
| `scrape-batch` | Scrape up to 10 URLs at once |
| `research` | Deep agentic research (1-5 min) |
| `login` | Save your API key |
| `status` | Check version and auth status |

## Scrape Formats

The `scrape` command supports three output formats via `--format`:

```bash
# Default — clean page text
anakin scrape "https://example.com"

# AI-extracted structured data
anakin scrape "https://example.com/product" --format json -o data.json

# Full API response (for debugging)
anakin scrape "https://example.com" --format raw -o debug.json
```

| Format | What you get | Size |
|--------|-------------|------|
| `markdown` (default) | Clean readable page text | Small |
| `json` | AI-extracted structured data only | Small |
| `raw` | Full API response (html, metadata, everything) | Large |

### Other scrape options

```bash
--browser          # Use headless browser (for JS-heavy sites)
--country CC       # Country code (default: us)
--session-id ID    # Session ID for authenticated scraping
--timeout SECS     # Polling timeout in seconds (default: 120)
-o, --output FILE  # Save output to file
```

## Authentication

Get your API key at [anakin.io/dashboard](https://anakin.io/dashboard).

**Option A** — Login command (recommended):
```bash
anakin login --api-key "ak-your-key-here"
```

**Option B** — Environment variable:
```bash
export ANAKIN_API_KEY="ak-your-key-here"
```

If no key is configured, the CLI will prompt you to enter one interactively.

## Error Handling

The CLI provides clear error messages for common issues:

| Error | Cause | Fix |
|-------|-------|-----|
| `Authentication failed (401)` | Invalid or missing API key | Run `anakin login --api-key "ak-xxx"` |
| `Plan upgrade required (402)` | Feature not available on your plan | Visit [anakin.io/pricing](https://anakin.io/pricing) |
| `Rate limit exceeded (429)` | Too many requests | Wait a few seconds and retry |
| `Job did not complete within Xs` | Scrape/research timed out | Increase with `--timeout 300` |
| `Job failed` | Server could not process the URL | Check if the URL is accessible |

All errors exit with code `1`. Success exits with code `0`.

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
  anakin scrape "https://example.com" | jq '.title'
  ```

## Documentation

- [API Docs](https://anakin.io/docs) — full endpoint reference
- [LLM-friendly docs](https://anakin.io/llms-full.txt) — plain text docs optimized for AI/LLM consumption

## Support

- Discord: [discord.gg/gP2YCJKH](https://discord.gg/gP2YCJKH)
- Email: [support@anakin.io](mailto:support@anakin.io)

## License

MIT
