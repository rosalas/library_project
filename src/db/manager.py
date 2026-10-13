import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import settings
from exceptions import CacheError
from logger import logger


class DatabaseManager:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.database_path
        self._initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _initialize_schema(self) -> None:
        schema_sql = """
        CREATE TABLE IF NOT EXISTS t_works (
            work_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            first_publish_year INTEGER,
            author_key TEXT,
            subject_tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS t_authors (
            author_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            birth_date TEXT,
            top_work TEXT
        );

        CREATE TABLE IF NOT EXISTS t_api_cache (
            cache_key TEXT PRIMARY KEY,
            response_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ttl_seconds INTEGER DEFAULT 86400
        );

        CREATE INDEX IF NOT EXISTS idx_works_year ON t_works(first_publish_year);
        CREATE INDEX IF NOT EXISTS idx_cache_created ON t_api_cache(created_at);
        """

        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()

    def get_cached_response(self, cache_key: str) -> dict[str, Any] | None:
        query = """
            SELECT response_json, created_at, ttl_seconds
            FROM t_api_cache
            WHERE cache_key = ?
        """

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (cache_key,))
                row = cursor.fetchone()

                if not row:
                    return None

                response_json, created_at_str, ttl_seconds = (
                    row["response_json"],
                    row["created_at"],
                    row["ttl_seconds"],
                )

                # Python 3.11+ soporta ISO strings con espacio o 'T' de forma nativa
                created_at = datetime.fromisoformat(created_at_str)

                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)

                now = datetime.now(UTC)
                elapsed = (now - created_at).total_seconds()

                if elapsed < ttl_seconds:
                    logger.debug("Cache HIT for key: '%s'", cache_key)
                    return json.loads(response_json)

                logger.debug("Cache EXPIRED for key: '%s'", cache_key)
                return None

        except (sqlite3.Error, json.JSONDecodeError, ValueError) as err:
            logger.warning("Cache retrieval failed for key '%s': %s", cache_key, err)
            return None

    def set_cached_response(
        self, cache_key: str, payload: dict[str, Any], ttl_seconds: int = 86400
    ) -> None:
        query = """
            INSERT INTO t_api_cache (cache_key, response_json, created_at, ttl_seconds)
            VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                response_json = excluded.response_json,
                created_at = CURRENT_TIMESTAMP,
                ttl_seconds = excluded.ttl_seconds
        """

        try:
            serialized_json = json.dumps(payload)
            with self.get_connection() as conn:
                conn.execute(query, (cache_key, serialized_json, ttl_seconds))
                conn.commit()
            logger.debug(
                "Cache STORED for key: '%s' (TTL: %ds)", cache_key, ttl_seconds
            )
        except (sqlite3.Error, TypeError) as err:
            logger.error("Failed to store cache for key '%s': %s", cache_key, err)
            raise CacheError(
                f"Cache write failed for key '{cache_key}': {err}"
            ) from err

    def upsert_work(self, work_data: dict[str, Any]) -> None:
        query = """
            INSERT INTO t_works (work_id, title, first_publish_year, author_key, subject_tags)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(work_id) DO UPDATE SET
                title = excluded.title,
                first_publish_year = excluded.first_publish_year,
                author_key = excluded.author_key,
                subject_tags = excluded.subject_tags
        """

        params = (
            work_data.get("work_id"),
            work_data.get("title", "Unknown Title"),
            work_data.get("first_publish_year"),
            work_data.get("author_key"),
            work_data.get("subject_tags"),
        )

        try:
            with self.get_connection() as conn:
                conn.execute(query, params)
                conn.commit()
        except sqlite3.Error as err:
            logger.error(
                "Failed to upsert work '%s': %s", work_data.get("work_id"), err
            )
            raise CacheError(f"Work upsert failed: {err}") from err

    def upsert_author(self, author_data: dict[str, Any]) -> None:
        query = """
            INSERT INTO t_authors (author_key, name, birth_date, top_work)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(author_key) DO UPDATE SET
                name = excluded.name,
                birth_date = excluded.birth_date,
                top_work = excluded.top_work
        """

        params = (
            author_data.get("author_key"),
            author_data.get("name", "Unknown Author"),
            author_data.get("birth_date"),
            author_data.get("top_work"),
        )

        try:
            with self.get_connection() as conn:
                conn.execute(query, params)
                conn.commit()
        except sqlite3.Error as err:
            logger.error(
                "Failed to upsert author '%s': %s", author_data.get("author_key"), err
            )
            raise CacheError(f"Author upsert failed: {err}") from err

    def bulk_upsert_works(self, works_list: list[dict[str, Any]]) -> int:
        if not works_list:
            return 0

        query = """
            INSERT INTO t_works (work_id, title, first_publish_year, author_key, subject_tags)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(work_id) DO UPDATE SET
                title = excluded.title,
                first_publish_year = excluded.first_publish_year,
                author_key = excluded.author_key,
                subject_tags = excluded.subject_tags
        """

        records = [
            (
                w.get("work_id"),
                w.get("title", "Unknown Title"),
                w.get("first_publish_year"),
                w.get("author_key"),
                w.get("subject_tags"),
            )
            for w in works_list
        ]

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(query, records)
                conn.commit()
                processed_count = cursor.rowcount
            logger.info("Successfully bulk upserted %d works.", processed_count)
            return processed_count
        except sqlite3.Error as err:
            logger.error(
                "Failed to execute bulk upsert for %d works: %s", len(works_list), err
            )
            raise CacheError(f"Bulk work upsert failed: {err}") from err

    def purge_expired_cache(self) -> int:
        query = """
            DELETE FROM t_api_cache
            WHERE (strftime('%s', 'now') - strftime('%s', created_at)) >= ttl_seconds
        """

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                conn.commit()
                deleted_rows = cursor.rowcount
            logger.info("Purged %d expired entries from API cache.", deleted_rows)
            return deleted_rows
        except sqlite3.Error as err:
            logger.error("Failed to purge expired cache entries: %s", err)
            raise CacheError(f"Cache purge operation failed: {err}") from err

    def get_database_stats(self) -> dict[str, Any]:
        valid_cache_query = """
            SELECT COUNT(*) FROM t_api_cache
            WHERE (strftime('%s', 'now') - strftime('%s', created_at)) < ttl_seconds
        """

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM t_works;")
                works_count = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM t_authors;")
                authors_count = cursor.fetchone()[0]

                cursor.execute(valid_cache_query)
                valid_cache_count = cursor.fetchone()[0]

            db_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
            db_size_mb = round(db_size_bytes / (1024**2), 2)

            return {
                "works_count": works_count,
                "authors_count": authors_count,
                "valid_cache_entries": valid_cache_count,
                "database_size_mb": db_size_mb,
            }
        except (sqlite3.Error, OSError) as err:
            logger.error("Failed to retrieve database statistics: %s", err)
            raise CacheError(f"Database diagnostics failed: {err}") from err
