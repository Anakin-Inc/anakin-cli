# Changelog

## 0.3.0 - unreleased

Rebuilt on the official [`anakin-sdk`](https://github.com/Anakin-Inc/anakin-py) (`>=0.2.0`), replacing the CLI's own HTTP client.

### Added
- `wire discover | catalogs | catalog | run | download | identities | login | build | build-status`.
- `map`, `crawl`, and `job get <type> <id>` for any async job.
- `monitor create | list | pause | resume | run | changes | snapshots | deliveries | test-alert | delete`.
- `ai-visibility search | sources | list`, `webhooks ...`, `sessions list | delete`.
- `scrape`: `--schema`, `--actions`, `--screenshot FILE`, `--session-name`, `--fresh`, and the `html`, `links`, `summary` formats.
- `research --schema`; `agentic-search` alias.
- Keyless mode: `scrape` and Wire discovery work without an API key on the free tier.
- Retries with backoff on 429/5xx/network errors (from the SDK); actionable error hints (signup link, Wire connect URL, job ID to resume).

### Changed
- `--format raw` and other JSON output use the SDK's snake_case field names (e.g. `duration_ms` instead of `durationMs`).
- Bad arguments or unreadable files exit with code 2 (API errors still exit 1).
- Self-hosted detection: any non-`anakin.io` API URL is treated as self-hosted.

### Fixed
- A global `--api-url` given before the subcommand is no longer overwritten by the subcommand's default.

### Removed
- The `requests` dependency and the internal `AnakinClient` / `poll_job` helpers.

## 0.2.0

Unified CLI with self-hosted support.
