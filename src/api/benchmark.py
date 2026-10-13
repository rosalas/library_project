import asyncio
import time

from api.async_client import AsyncLibraryApiClient
from api.sync_client import LibraryApiClient
from logger import logger


def run_performance_benchmark(work_ids: list[str]) -> dict[str, float]:
    # 1. Sequential sync execution
    sync_client = LibraryApiClient()
    start_sync = time.perf_counter()
    [sync_client.get_work(wid) for wid in work_ids]
    sync_duration = time.perf_counter() - start_sync

    # 2. Concurrent async execution
    async_client = AsyncLibraryApiClient()
    start_async = time.perf_counter()
    asyncio.run(async_client.fetch_works_batch(work_ids))
    async_duration = time.perf_counter() - start_async

    speedup = sync_duration / async_duration if async_duration > 0 else 0.0
    logger.info(
        "Benchmark Complete: Sync = %.2fs | Async = %.2fs | Speedup = %.2fx",
        sync_duration,
        async_duration,
        speedup,
    )

    return {
        "sync_duration": sync_duration,
        "async_duration": async_duration,
        "speedup": speedup,
    }
