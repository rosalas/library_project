import pytest

from db.manager import DatabaseManager


@pytest.fixture
def db_manager(tmp_path):
    db_file = tmp_path / "test_library.db"
    return DatabaseManager(db_path=db_file)


def test_initialize_schema(db_manager):
    stats = db_manager.get_database_stats()
    assert stats["works_count"] == 0
    assert stats["authors_count"] == 0


def test_cache_set_and_get(db_manager):
    payload = {"status": "ok", "items": [1, 2, 3]}
    db_manager.set_cached_response("test_key", payload, ttl_seconds=3600)

    cached = db_manager.get_cached_response("test_key")
    assert cached == payload


def test_cache_miss_expired(db_manager):
    payload = {"data": "expired"}
    db_manager.set_cached_response("expired_key", payload, ttl_seconds=-1)

    cached = db_manager.get_cached_response("expired_key")
    assert cached is None


def test_upsert_work_and_stats(db_manager):
    work = {
        "work_id": "OL100W",
        "title": "Clean Code",
        "first_publish_year": 2008,
        "author_key": "OL200A",
        "subject_tags": "Software Engineering",
    }
    db_manager.upsert_work(work)

    stats = db_manager.get_database_stats()
    assert stats["works_count"] == 1


def test_bulk_upsert_works(db_manager):
    works = [
        {"work_id": f"OL{i}W", "title": f"Book {i}", "first_publish_year": 2020}
        for i in range(10)
    ]
    inserted_count = db_manager.bulk_upsert_works(works)
    assert inserted_count == 10

    stats = db_manager.get_database_stats()
    assert stats["works_count"] == 10
