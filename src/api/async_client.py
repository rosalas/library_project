import asyncio
from typing import Any, ClassVar

import httpx

from config import settings
from exceptions import APIError
from logger import logger


class AsyncLibraryAPIClient:
    RETRYABLE_STATUS_CODES: ClassVar[set] = {429, 500, 502, 503, 504}

    def __init__(
        self,
        base_url: str | None = None,
        max_connections: int = 5,
        timeout: float | None = None,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ) -> AsyncLibraryAPIClient:
        self.base_url = (base_url or settings.open_library_base_url).rstrip("/")
        self.timeout = timeout or settings.api_timeout_seconds
        self.max_connections = max_connections
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.semaphore = asyncio.Semaphore(max_connections)

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        async with self.semaphore:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await client.request(method, url, params=params)

                    if (
                        response.status_code in self.RETRYABLE_STATUS_CODES
                        and attempt < self.max_retries
                    ):
                        sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                        logger.warning(
                            "Async API request to %s returned HTTP %d. Retrying in %.1fs (Attempt %d/%d)...",
                            url,
                            response.status_code,
                            sleep_time,
                            attempt,
                            self.max_retries,
                        )
                        await asyncio.sleep(sleep_time)
                        continue

                    if response.status_code == 404:
                        logger.warning("Resource not found at %s (404).", url)
                        return {}

                    response.raise_for_status()
                    return response.json()

                except httpx.TimeoutException as err:
                    if attempt < self.max_retries:
                        sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                        logger.warning(
                            "Async timeout for %s. Retrying in %.1fs (Attempt %d/%d)...",
                            url,
                            sleep_time,
                            attempt,
                            self.max_retries,
                        )
                        await asyncio.sleep(sleep_time)
                        continue
                    logger.error(
                        "Async request timed out for %s after %d retries.",
                        url,
                        self.max_retries,
                    )
                    raise APIError(
                        f"Async request timed out for endpoint '{endpoint}'"
                    ) from err

                except httpx.HTTPStatusError as err:
                    logger.error(
                        "HTTP Error %d for %s: %s",
                        err.response.status_code,
                        url,
                        err,
                    )
                    raise APIError(
                        f"HTTP Error {err.response.status_code} requesting '{endpoint}'",
                        status_code=err.response.status_code,
                    ) from err

                except httpx.RequestError as err:
                    logger.error("Async network error connecting to %s: %s", url, err)
                    raise APIError(
                        f"Failed connection to endpoint '{endpoint}': {err}"
                    ) from err

            raise APIError(
                f"Exhausted all {self.max_retries} retries for endpoint '{endpoint}'"
            )

    async def fetch_work(
        self, client: httpx.AsyncClient, work_id: str
    ) -> dict[str, Any]:
        # Fetch a single work payload by work ID asynchronously
        clean_id = work_id.replace("/works/", "").strip()
        return await self._request(client, "GET", f"works/{clean_id}.json")

    async def fetch_works_batch(self, work_ids: list[str]) -> list[dict[str, Any]]:
        # Fetch multiple work items concurrently using asyncio.gather and connection pooling
        limits = httpx.Limits(max_connections=self.max_connections)
        timeout_config = httpx.Timeout(self.timeout)

        async with httpx.AsyncClient(limits=limits, timeout=timeout_config) as client:
            tasks = [self.fetch_work(client, wid) for wid in work_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            valid_results = []
            for work_id, result in zip(work_ids, results, strict=False):
                if isinstance(result, Exception):
                    logger.error(
                        "Failed batch task for work_id '%s': %s",
                        work_id,
                        result,
                    )
                elif result:
                    valid_results.append(result)

            return valid_results

    async def search_books_async(
        self, query: str, page: int = 1, limit: int = 10
    ) -> dict[str, Any]:
        # Asynchronously search books by query string
        timeout_config = httpx.Timeout(self.timeout)
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            return await self._request(
                client,
                "GET",
                "search.json",
                params={"q": query, "page": page, "limit": limit},
            )

    async def fetch_subject_works_async(
        self, subject: str, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        # Asynchronously fetch works for a specific subject category
        timeout_config = httpx.Timeout(self.timeout)
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            return await self._request(
                client,
                "GET",
                f"subjects/{subject.lower().strip()}.json",
                params={"limit": limit, "offset": offset},
            )
