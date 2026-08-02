import logging
from typing import Any
import httpx

from app.config import settings

logger = logging.getLogger("alpha_monitor.alpha_client")


class AlphaClientError(Exception):
    """Base exception for Alpha API client errors."""

    pass


class AlphaClient:
    """HTTP client for fetching data from Alpha123 API."""

    def __init__(self, api_url: str = ""):
        self.api_url = api_url or settings.alpha_api_url
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
        }
        # Timeout: 10s connect, 20s read
        self.timeout = httpx.Timeout(20.0, connect=10.0)

    def fetch_raw_data(self) -> Any:
        """Fetch raw JSON payload from Alpha123 API.

        Raises:
            AlphaClientError: On network, status, or content-type errors.
        """
        try:
            with httpx.Client(
                headers=self.headers, timeout=self.timeout, follow_redirects=True
            ) as client:
                response = client.get(self.api_url)

                if response.status_code != 200:
                    raise AlphaClientError(
                        f"HTTP status error {response.status_code}: {response.text[:200]}"
                    )

                content_type = response.headers.get("content-type", "").lower()
                # Accept application/json or text/plain or json in content-type
                if not any(t in content_type for t in ["json", "text/plain", "text/javascript"]):
                    logger.warning(
                        f"Unexpected Content-Type header: '{content_type}'. Attempting to parse JSON."
                    )

                try:
                    return response.json()
                except Exception as json_err:
                    raise AlphaClientError(
                        f"Failed to parse response JSON: {json_err}. Raw text sample: {response.text[:200]!r}"
                    )
        except httpx.RequestError as req_err:
            raise AlphaClientError(f"HTTP request failed: {req_err}")
