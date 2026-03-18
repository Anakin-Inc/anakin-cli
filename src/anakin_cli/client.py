"""HTTP client wrapping all Anakin API endpoints.

Requires the ``requests`` library (``pip install requests``).
"""

import requests

from anakin_cli.utils import (
    AnakinAPIError,
    AnakinAuthError,
    AnakinRateLimitError,
    AnakinUpgradeError,
)

DEFAULT_BASE_URL = "https://api.anakin.io/v1"
USER_AGENT = "anakin-cli/0.2.0"


class AnakinClient:
    """Thin wrapper around the Anakin REST API."""

    def __init__(self, api_key: str | None = None, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        if api_key:
            headers["X-API-Key"] = api_key
        self.session.headers.update(headers)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_response(self, resp: requests.Response) -> dict:
        """Check for error status codes and return parsed JSON."""
        if resp.status_code == 401:
            raise AnakinAuthError(
                "Authentication failed (401). Check your API key."
            )
        if resp.status_code == 402:
            raise AnakinUpgradeError(
                "Plan upgrade required (402). Visit https://anakin.io/pricing"
            )
        if resp.status_code == 429:
            raise AnakinRateLimitError(
                "Rate limit exceeded (429). Wait a few seconds and retry."
            )
        if resp.status_code >= 500:
            raise AnakinAPIError(
                f"Server error ({resp.status_code}): {resp.text[:200]}",
                status_code=resp.status_code,
            )
        if not resp.ok:
            raise AnakinAPIError(
                f"Request failed ({resp.status_code}): {resp.text[:200]}",
                status_code=resp.status_code,
            )
        return resp.json()

    # ------------------------------------------------------------------
    # Sync endpoint
    # ------------------------------------------------------------------

    def search(self, prompt: str, limit: int = 5) -> dict:
        """POST /v1/search — synchronous AI web search."""
        resp = self.session.post(
            f"{self.base_url}/search",
            json={"prompt": prompt, "limit": limit},
        )
        return self._handle_response(resp)

    # ------------------------------------------------------------------
    # Async start endpoints (return jobId)
    # ------------------------------------------------------------------

    def start_url_scrape(
        self,
        url: str,
        *,
        country: str = "us",
        use_browser: bool = False,
        generate_json: bool = False,
        session_id: str | None = None,
    ) -> dict:
        """POST /v1/url-scraper — start a single-URL scrape job."""
        body: dict = {
            "url": url,
            "country": country,
            "useBrowser": use_browser,
            "generateJson": generate_json,
        }
        if session_id:
            body["sessionId"] = session_id
        resp = self.session.post(f"{self.base_url}/url-scraper", json=body)
        return self._handle_response(resp)

    def start_batch_scrape(
        self,
        urls: list[str],
        *,
        country: str = "us",
        use_browser: bool = False,
        generate_json: bool = False,
    ) -> dict:
        """POST /v1/url-scraper/batch — start a batch scrape (up to 10 URLs)."""
        resp = self.session.post(
            f"{self.base_url}/url-scraper/batch",
            json={
                "urls": urls,
                "country": country,
                "useBrowser": use_browser,
                "generateJson": generate_json,
            },
        )
        return self._handle_response(resp)

    def start_agentic_search(self, prompt: str) -> dict:
        """POST /v1/agentic-search — start a deep research job."""
        resp = self.session.post(
            f"{self.base_url}/agentic-search",
            json={"prompt": prompt},
        )
        return self._handle_response(resp)

    # ------------------------------------------------------------------
    # Async poll endpoints (return job status + results)
    # ------------------------------------------------------------------

    def get_url_scrape_result(self, job_id: str) -> dict:
        """GET /v1/url-scraper/{id} — poll scrape job status."""
        resp = self.session.get(f"{self.base_url}/url-scraper/{job_id}")
        return self._handle_response(resp)

    def get_agentic_search_result(self, job_id: str) -> dict:
        """GET /v1/agentic-search/{id} — poll research job status."""
        resp = self.session.get(f"{self.base_url}/agentic-search/{job_id}")
        return self._handle_response(resp)
