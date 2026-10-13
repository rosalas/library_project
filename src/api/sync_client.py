import time
from typing import Any, ClassVar

import httpx

from config import settings
from exceptions import APIError
from logger import logger


class SyncLibraryAPIClient:
    RETRYABLE_STATUS_CODES: ClassVar[set] = {429, 500, 502, 503, 504}

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ) -> SyncLibraryAPIClient:
        self.base_url = (base_url or settings.open_library_base_url).rstrip("/")
        self.timeout = timeout or settings.api_timeout_seconds
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def _request(
        self, method: str, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.request(method, url, params=params)

                    if (
                        response.status_code in self.RETRYABLE_STATUS_CODES
                        and attempt < self.max_retries - 1
                    ):
                        sleep_time = self.backoff_factor * (2**attempt)
                        logger.warning(
                            "API request to %s returned HTTP %d. Retrying in %.1f s (attempt %d/%d)...",
                            url,
                            sleep_time,
                            attempt + 1,
                            self.max_retries,
                        )
                        time.sleep(sleep_time)
                        continue

                    if response.status_code == 404:
                        logger.warning("Resource not found at %s (HTTP 404).", url)
                        return {}

                    response.raise_for_status()
                    return response.json()

            except httpx.TimeoutException as error:
                if attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2**attempt)
                    logger.warning(
                        "Timeout connecting to %s. Retrying in %.1f s (attempt %d/%d)...",
                        url,
                        sleep_time,
                        attempt,
                        self.maxr_retries,
                    )
                    time.sleep(sleep_time)
                    continue

                logger.error(
                    "Request timed out for %s after %d retries.", url, self.max_retries
                )

                raise APIError(
                    f"Request timed out for endpoint '{endpoint}'"
                ) from error

            except httpx.HTTPStatusError as error:
                logger.error(
                    "HTTP error %d for %s: %s", error.response.status_code, url, error
                )

                raise APIError(
                    f"HTTP error {error.response.status_code} requesting '{endpoint}'.",
                    status_code=error.response.status_code,
                ) from error

            except httpx.RequestError as error:
                logger.error("Network error connecting to endpoint %s: %s", url, error)

                raise APIError(
                    f"Failed connection to endpoint '{endpoint}': {error}"
                ) from error

        raise APIError(
            f"Exhausted all {self.max_retries} retries for endpoint '{endpoint}'."
        )

    def get_work(self, work_id: str) -> dict[str, Any]:
        # Fetch a single work payload by work ID (e.g., 'OL45804W')
        clean_id = work_id.replace("/works/", "").strip()
        return self._request("GET", f"works/{clean_id}.json")

    def search_books(
        self, query: str, page: int = 1, limit: int = 10
    ) -> dict[str, Any]:
        # Search books by query string across title, author, and description
        params = {"q": query, "page": page, "limit": limit}
        return self._request("GET", "search.json", params=params)

    def get_subject_works(
        self, subject: str, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        # Fetch works under a specific subject category (e.g., 'python').
        params = {"limit": limit, "offset": offset}
        return self._request(
            "GET", f"subjects/{subject.lower().strip()}.json", params=params
        )

    def get_author_works(self, author_id: str, limit: int = 20) -> dict[str, Any]:
        # Fetch list of works produced by a given author ID (e.g., 'OL26320A')
        clean_id = author_id.replace("/authors/", "").strip()
        params = {"limit": limit}
        return self._request("GET", f"authors/{clean_id}/works.json", params=params)
