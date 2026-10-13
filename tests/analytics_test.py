import pandas as pd
import pytest

from db.manager import DatabaseManager
from processing.analytics import CatalogAnalytics


@pytest.fixture
def sample_db(tmp_path):
    """Fixture que inicializa una base de datos SQLite temporal para las pruebas de analítica."""
    db_file = tmp_path / "test_analytics.db"
    db_mgr = DatabaseManager(db_path=db_file)
    conn = db_mgr.get_connection()

    works_data = [
        ("OL1W", "  pYthOn automation ", 2021, "OL1A", "Programming, Python"),
        ("OL2W", "advanced python", "2018", "OL1A", None),
        ("OL3W", "legacy book", None, "OL2A", "History"),
        ("OL4W", "future robotics", 2025, "OL3A", "AI"),
    ]

    conn.executemany(
        """
        INSERT OR REPLACE INTO t_works (work_id, title, first_publish_year, author_key, subject_tags)
        VALUES (?, ?, ?, ?, ?)
        """,
        works_data,
    )

    authors_data = [
        ("OL1A", "Guido van Rossum", "1956-01-31", "Python Design"),
        ("OL2A", "Ada Lovelace", "1815-12-10", "Analytical Engine"),
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO t_authors (author_key, name, birth_date, top_work)
        VALUES (?, ?, ?, ?)
        """,
        authors_data,
    )

    conn.commit()
    yield conn
    conn.close()


def test_deduplicate_catalog():
    """Verifica que deduplicate_catalog elimine filas duplicadas basadas en work_id."""
    df_raw = pd.DataFrame(
        [
            {"work_id": "OL1W", "title": "Book A"},
            {"work_id": "OL1W", "title": "Book A Duplicate"},
            {"work_id": "OL2W", "title": "Book B"},
        ]
    )
    analytics = CatalogAnalytics(db_conn=None)
    df_dedup = analytics.deduplicate_catalog(df_raw)

    assert len(df_dedup) == 2
    assert list(df_dedup["work_id"]) == ["OL1W", "OL2W"]


def test_get_cleaned_catalog_df(sample_db):
    """Verifica el casteo de tipos, normalización de títulos, reemplazo de nulos y cálculo de décadas."""
    analytics = CatalogAnalytics(db_conn=sample_db)
    df = analytics.get_cleaned_catalog_df()

    assert len(df) == 4
    assert df["first_publish_year"].dtype == "int64"
    assert df.loc[df["work_id"] == "OL3W", "first_publish_year"].values[0] == 0
    assert df.loc[df["work_id"] == "OL1W", "title"].values[0] == "Python Automation"
    assert df.loc[df["work_id"] == "OL2W", "subject_tags"].values[0] == "Uncategorized"
    assert df.loc[df["work_id"] == "OL1W", "publication_decade"].values[0] == "2020s"
    assert df.loc[df["work_id"] == "OL3W", "publication_decade"].values[0] == "Unknown"


def test_summarize_by_author(sample_db):
    """Verifica el agrupamiento por autor y el cálculo de métricas."""
    analytics = CatalogAnalytics(db_conn=sample_db)
    summary_df = analytics.summarize_by_author()

    assert not summary_df.empty
    top_author_row = summary_df.iloc[0]

    assert top_author_row["author_key"] == "OL1A"
    assert top_author_row["total_works"] == 2
    assert top_author_row["earliest_year"] == 2018
    assert top_author_row["latest_year"] == 2021


def test_summarize_by_decade(sample_db):
    """Verifica el agrupamiento y conteo de obras por década."""
    analytics = CatalogAnalytics(db_conn=sample_db)
    decade_df = analytics.summarize_by_decade()

    assert not decade_df.empty
    assert "publication_decade" in decade_df.columns
    assert "total_works" in decade_df.columns

    row_2020s = decade_df[decade_df["publication_decade"] == "2020s"]
    assert row_2020s["total_works"].values[0] == 2


def test_join_works_with_authors(sample_db):
    """Verifica el LEFT JOIN entre t_works y t_authors."""
    analytics = CatalogAnalytics(db_conn=sample_db)
    joined_df = analytics.join_works_with_authors()

    assert "author_name" in joined_df.columns
    assert "author_birth_date" in joined_df.columns

    ol1a_row = joined_df[joined_df["author_key"] == "OL1A"].iloc[0]
    assert ol1a_row["author_name"] == "Guido van Rossum"

    ol3a_row = joined_df[joined_df["author_key"] == "OL3A"].iloc[0]
    assert ol3a_row["author_name"] == "Unknown Author"


def test_empty_database_handling(tmp_path):
    """Verifica que las funciones de analítica retornen DataFrames vacíos cuando la DB está vacía."""
    db_file = tmp_path / "empty_analytics.db"
    db_mgr = DatabaseManager(db_path=db_file)
    conn = db_mgr.get_connection()

    analytics = CatalogAnalytics(db_conn=conn)

    assert analytics.get_cleaned_catalog_df().empty
    assert analytics.summarize_by_author().empty
    assert analytics.summarize_by_decade().empty
    assert analytics.join_works_with_authors().empty

    conn.close()
