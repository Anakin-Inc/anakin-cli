"""CLI tests. HTTP is mocked with respx; nothing touches the network or ~/.anakin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from anakin_cli import auth, cli

BASE = "https://api.anakin.io/v1"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ANAKIN_API_KEY", raising=False)
    monkeypatch.delenv("ANAKIN_API_URL", raising=False)
    monkeypatch.setattr(auth, "CONFIG_DIR", tmp_path / ".anakin")
    monkeypatch.setattr(auth, "CONFIG_FILE", tmp_path / ".anakin" / "config.json")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANAKIN_API_KEY", "ak-test")


def run(argv: list[str]) -> int:
    try:
        cli.main(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def _json(request: httpx.Request) -> Any:
    return json.loads(request.content)


def _fast_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    import anakin._http as http

    monkeypatch.setattr(http, "DEFAULT_POLL_INTERVAL", 0.001)


# ─── scrape ───────────────────────────────────────────────────────────────────


@respx.mock
def test_scrape_markdown_to_stdout(key: None, capsys: pytest.CaptureFixture[str]) -> None:
    respx.post(f"{BASE}/url-scraper").mock(
        return_value=httpx.Response(202, json={"jobId": "j", "status": "pending"})
    )
    respx.get(f"{BASE}/url-scraper/j").mock(
        return_value=httpx.Response(200, json={"id": "j", "status": "completed", "markdown": "# Hi"})
    )
    assert run(["scrape", "https://e.com"]) == 0
    assert capsys.readouterr().out.strip() == "# Hi"


@respx.mock
def test_scrape_json_with_schema_file(key: None, tmp_path: Path) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type": "object"}')
    out = tmp_path / "out.json"
    sent: dict[str, Any] = {}

    def submit(request: httpx.Request) -> httpx.Response:
        sent.update(_json(request))
        return httpx.Response(202, json={"jobId": "j", "status": "pending"})

    respx.post(f"{BASE}/url-scraper").mock(side_effect=submit)
    respx.get(f"{BASE}/url-scraper/j").mock(
        return_value=httpx.Response(
            200, json={"id": "j", "status": "completed", "generatedJson": {"price": 9}}
        )
    )
    assert run(["scrape", "https://e.com", "--format", "json", "--schema", f"@{schema}", "-o", str(out)]) == 0
    assert sent["outputSchema"] == {"type": "object"}
    assert sent["generateJson"] is True
    assert json.loads(out.read_text()) == {"price": 9}


@respx.mock
def test_scrape_without_key_uses_keyless_tier(capsys: pytest.CaptureFixture[str]) -> None:
    route = respx.post(f"{BASE}/url-scraper/scrape").mock(
        return_value=httpx.Response(200, json={"markdown": "free", "trial": {"remaining_credits": 9}})
    )
    assert run(["scrape", "https://e.com"]) == 0
    assert "X-API-Key" not in route.calls.last.request.headers
    assert capsys.readouterr().out.strip() == "free"


@respx.mock
def test_keyless_402_prints_signup_hint(capsys: pytest.CaptureFixture[str]) -> None:
    respx.post(f"{BASE}/url-scraper/scrape").mock(
        return_value=httpx.Response(
            402,
            json={
                "error": "keyless_unavailable",
                "message": "The keyless free tier is at capacity right now.",
                "trial": {"signup_url": "https://anakin.io/signup?source=keyless"},
            },
        )
    )
    assert run(["scrape", "https://e.com"]) == 1
    err = capsys.readouterr().err
    assert "at capacity" in err
    assert "https://anakin.io/signup?source=keyless" in err


@respx.mock
def test_self_hosted_scrape_needs_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _fast_polls(monkeypatch)
    local = "http://localhost:8080/v1"
    submit = respx.post(f"{local}/url-scraper").mock(
        return_value=httpx.Response(202, json={"jobId": "j", "status": "pending"})
    )
    respx.get(f"{local}/url-scraper/j").mock(
        return_value=httpx.Response(200, json={"id": "j", "status": "completed", "markdown": "x"})
    )
    # --api-url works after the subcommand and without /v1
    assert run(["scrape", "https://e.com", "--api-url", "http://localhost:8080"]) == 0
    assert submit.called


@respx.mock
def test_global_api_url_before_subcommand_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    _fast_polls(monkeypatch)
    local = "http://localhost:8080/v1"
    submit = respx.post(f"{local}/url-scraper").mock(
        return_value=httpx.Response(202, json={"jobId": "j", "status": "pending"})
    )
    respx.get(f"{local}/url-scraper/j").mock(
        return_value=httpx.Response(200, json={"id": "j", "status": "completed", "markdown": "x"})
    )
    assert run(["--api-url", "http://localhost:8080", "scrape", "https://e.com"]) == 0
    assert submit.called


def test_search_on_self_hosted_exits_with_hint(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["search", "q", "--api-url", "http://localhost:8080"]) == 1
    assert "hosted API" in capsys.readouterr().err


def test_keyed_command_without_key_exits_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["crawl", "https://e.com"]) == 1
    assert "No API key configured" in capsys.readouterr().err


# ─── batch / crawl / map / research / job ─────────────────────────────────────


@respx.mock
def test_scrape_batch_truncates_to_ten(key: None, capsys: pytest.CaptureFixture[str]) -> None:
    sent: dict[str, Any] = {}

    def submit(request: httpx.Request) -> httpx.Response:
        sent.update(_json(request))
        return httpx.Response(202, json={"jobId": "b", "status": "pending"})

    respx.post(f"{BASE}/url-scraper/batch").mock(side_effect=submit)
    respx.get(f"{BASE}/url-scraper/b").mock(
        return_value=httpx.Response(200, json={"id": "b", "status": "completed", "results": []})
    )
    assert run(["scrape-batch", *[f"https://e.com/{i}" for i in range(12)]]) == 0
    assert len(sent["urls"]) == 10
    assert json.loads(capsys.readouterr().out)["id"] == "b"


@respx.mock
def test_crawl_patterns(key: None) -> None:
    sent: dict[str, Any] = {}

    def submit(request: httpx.Request) -> httpx.Response:
        sent.update(_json(request))
        return httpx.Response(202, json={"jobId": "c", "status": "pending"})

    respx.post(f"{BASE}/crawl").mock(side_effect=submit)
    respx.get(f"{BASE}/crawl/c").mock(
        return_value=httpx.Response(200, json={"id": "c", "status": "completed", "results": []})
    )
    assert (
        run(["crawl", "https://e.com", "--include", "/blog/*", "--include", "/docs/*", "--max-pages", "5"])
        == 0
    )
    assert sent["includePatterns"] == ["/blog/*", "/docs/*"]
    assert sent["maxPages"] == 5


@respx.mock
def test_map_links_only(key: None, capsys: pytest.CaptureFixture[str]) -> None:
    respx.post(f"{BASE}/map").mock(return_value=httpx.Response(202, json={"jobId": "m", "status": "pending"}))
    respx.get(f"{BASE}/map/m").mock(
        return_value=httpx.Response(
            200, json={"id": "m", "status": "completed", "links": ["https://e.com/a", "https://e.com/b"]}
        )
    )
    assert run(["map", "https://e.com", "--links-only"]) == 0
    assert capsys.readouterr().out.split() == ["https://e.com/a", "https://e.com/b"]


@respx.mock
def test_job_timeout_hint_includes_job_id(key: None, capsys: pytest.CaptureFixture[str]) -> None:
    respx.post(f"{BASE}/crawl").mock(
        return_value=httpx.Response(202, json={"jobId": "slow", "status": "pending"})
    )
    respx.get(f"{BASE}/crawl/slow").mock(
        return_value=httpx.Response(200, json={"id": "slow", "status": "processing"})
    )
    assert run(["crawl", "https://e.com", "--timeout", "0.01"]) == 1
    err = " ".join(capsys.readouterr().err.split())  # rich wraps at 80 columns
    assert "anakin job get <type> slow" in err


@respx.mock
def test_job_get(key: None, capsys: pytest.CaptureFixture[str]) -> None:
    respx.get(f"{BASE}/crawl/c1").mock(
        return_value=httpx.Response(200, json={"id": "c1", "status": "completed", "totalPages": 3})
    )
    assert run(["job", "get", "crawl", "c1"]) == 0
    assert json.loads(capsys.readouterr().out)["total_pages"] == 3


# ─── wire ─────────────────────────────────────────────────────────────────────


@respx.mock
def test_wire_discover_without_key(capsys: pytest.CaptureFixture[str]) -> None:
    respx.get(f"{BASE}/wire/resolve").mock(
        return_value=httpx.Response(
            200, json={"results": [{"action_id": "hn_stories", "catalog": "hackernews"}]}
        )
    )
    assert run(["wire", "discover", "hacker news", "--limit", "1"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["catalog_slug"] == "hackernews"


@respx.mock
def test_wire_run_params(key: None, capsys: pytest.CaptureFixture[str]) -> None:
    sent: dict[str, Any] = {}

    def submit(request: httpx.Request) -> httpx.Response:
        sent.update(_json(request))
        return httpx.Response(202, json={"status": "processing", "job_id": "w"})

    respx.post(f"{BASE}/wire/task").mock(side_effect=submit)
    respx.get(f"{BASE}/wire/jobs/w").mock(
        return_value=httpx.Response(
            200, json={"status": "completed", "data": {"ok": True}, "credits_used": 2}
        )
    )
    code = run(
        [
            "wire",
            "run",
            "walmart_search",
            "-p",
            "query=phones",
            "-p",
            "limit=5",
            "-p",
            "prime=true",
            "--credential-id",
            "cred-1",
        ]
    )
    assert code == 0
    assert sent["params"] == {"query": "phones", "limit": 5, "prime": True}
    assert sent["credential_id"] == "cred-1"
    assert json.loads(capsys.readouterr().out) == {"ok": True}


@respx.mock
def test_wire_auth_required_prints_connect_url(key: None, capsys: pytest.CaptureFixture[str]) -> None:
    respx.post(f"{BASE}/wire/task").mock(
        return_value=httpx.Response(
            401,
            json={
                "status": "error",
                "error": {
                    "code": "AUTH_REQUIRED",
                    "message": "Needs LinkedIn",
                    "connect_url": "/products/wire/linkedin/connect",
                },
            },
        )
    )
    assert run(["wire", "run", "li_profile"]) == 1
    assert "https://anakin.io/products/wire/linkedin/connect" in capsys.readouterr().err


def test_bad_param_syntax_exits_2(key: None, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["wire", "run", "x", "-p", "novalue"]) == 2
    assert "key=value" in capsys.readouterr().err


# ─── monitor / ai-visibility / webhooks / sessions / status ───────────────────


@respx.mock
def test_monitor_create(key: None) -> None:
    sent: dict[str, Any] = {}

    def create(request: httpx.Request) -> httpx.Response:
        sent.update(_json(request))
        return httpx.Response(201, json={"id": "m1", "url": "https://e.com", "creditCostPerRun": 4})

    respx.post(f"{BASE}/monitors").mock(side_effect=create)
    code = run(
        [
            "monitor",
            "create",
            "https://e.com",
            "--interval",
            "60",
            "--schema",
            '{"type":"object"}',
            "--ai",
            "--emails",
            "a@x.com",
        ]
    )
    assert code == 0
    assert sent == {
        "url": "https://e.com",
        "intervalMinutes": 60,
        "watchMode": "specific_data",
        "outputSchema": {"type": "object"},
        "aiMode": True,
        "alertEmails": "a@x.com",
    }


@respx.mock
def test_monitor_delete_with_yes(key: None) -> None:
    route = respx.delete(f"{BASE}/monitors/m1").mock(return_value=httpx.Response(200, json={"success": True}))
    assert run(["monitor", "delete", "m1", "-y"]) == 0
    assert route.called


@respx.mock
def test_ai_visibility_search_strips_full_content(key: None, capsys: pytest.CaptureFixture[str]) -> None:
    respx.post(f"{BASE}/ai-visibility/search").mock(
        return_value=httpx.Response(200, json={"search_id": "s", "status": "running", "results": []})
    )
    respx.get(f"{BASE}/ai-visibility/search/s").mock(
        return_value=httpx.Response(
            200,
            json={
                "search_id": "s",
                "status": "completed",
                "results": [
                    {"source": "chatgpt", "status": "completed", "summary": "A", "full_content": "HUGE"}
                ],
            },
        )
    )
    assert run(["ai-visibility", "search", "best scraper", "--sources", "chatgpt"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["results"][0]["summary"] == "A"
    assert "full_content" not in out["results"][0]


@respx.mock
def test_webhooks_and_sessions_list(key: None, capsys: pytest.CaptureFixture[str]) -> None:
    respx.get(f"{BASE}/webhooks/events").mock(
        return_value=httpx.Response(200, json={"events": ["job.completed"]})
    )
    respx.get(f"{BASE}/sessions").mock(return_value=httpx.Response(200, json={"sessions": None}))
    assert run(["webhooks", "events"]) == 0
    assert json.loads(capsys.readouterr().out) == ["job.completed"]
    assert run(["sessions", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_login_then_status(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["login", "--api-key", "ak-1234567890abcd"]) == 0
    assert auth.get_api_key() == "ak-1234567890abcd"
    assert run(["status"]) == 0
    err = capsys.readouterr().err
    assert "ak-123...abcd" in err
    assert "hosted" in err
