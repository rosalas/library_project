import sqlite3

import pandas as pd

from logger import logger


class CatalogAnalytics:
    """Engine for executing pandas data cleaning, transformations, aggregations, and table joins."""

    def __init__(self, db_conn: sqlite3.Connection):
        self.conn = db_conn

    def deduplicate_catalog(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove duplicate records based on work_id while keeping the first occurrence."""
        if df.empty or "work_id" not in df.columns:
            return df
        initial_count = len(df)
        deduped_df = df.drop_duplicates(subset=["work_id"], keep="first")
        removed_count = initial_count - len(deduped_df)

        if removed_count > 0:
            logger.info(
                "Deduplicated catalog: removed %d duplicate row(s).", removed_count
            )

        return deduped_df

    def get_cleaned_catalog_df(self) -> pd.DataFrame:
        """Load raw works from SQLite, perform type casting, clean nulls, compute decades, and deduplicate."""
        try:
            df = pd.read_sql_query("SELECT * FROM t_works", self.conn)
        except pd.errors.DatabaseError as err:
            logger.error("Failed to query t_works table: %s", err)
            return pd.DataFrame()

        if df.empty:
            logger.warning("t_works table is empty.")
            return df

        # 1. Data Cleaning & Type Casting
        df["first_publish_year"] = (
            pd.to_numeric(df["first_publish_year"], errors="coerce")
            .fillna(0)
            .astype(int)
        )
        df["title"] = df["title"].astype(str).str.strip().str.title()
        df["subject_tags"] = df["subject_tags"].fillna("Uncategorized")

        # 2. Derive Publication Decade (0 for missing/invalid years)
        df["publication_decade"] = df["first_publish_year"].apply(
            lambda yr: f"{(yr // 10) * 10}s" if yr > 0 else "Unknown"
        )

        # 3. Deduplicate Catalog
        return self.deduplicate_catalog(df)

    def summarize_by_author(self) -> pd.DataFrame:
        """Compute total works, earliest publication year, and latest publication year per author."""
        df = self.get_cleaned_catalog_df()
        if df.empty:
            return pd.DataFrame()

        summary = (
            df.groupby("author_key")
            .agg(
                total_works=("work_id", "count"),
                earliest_year=(
                    "first_publish_year",
                    lambda x: int(x[x > 0].min()) if any(x > 0) else None,
                ),
                latest_year=(
                    "first_publish_year",
                    lambda x: int(x[x > 0].max()) if any(x > 0) else None,
                ),
            )
            .reset_index()
        )

        return summary.sort_values(by="total_works", ascending=False)

    def summarize_by_decade(self) -> pd.DataFrame:
        """Group works by publication decade and compute work counts."""
        df = self.get_cleaned_catalog_df()
        if df.empty:
            return pd.DataFrame()

        decade_summary = (
            df.groupby("publication_decade")
            .agg(total_works=("work_id", "count"))
            .reset_index()
        )

        return decade_summary.sort_values(by="total_works", ascending=False)

    def join_works_with_authors(self) -> pd.DataFrame:
        """Perform a LEFT JOIN between cleaned t_works DataFrame and t_authors DataFrame on author_key."""
        works_df = self.get_cleaned_catalog_df()
        if works_df.empty:
            return pd.DataFrame()

        try:
            authors_df = pd.read_sql_query("SELECT * FROM t_authors", self.conn)
        except pd.errors.DatabaseError as err:
            logger.error("Failed to query t_authors table for join: %s", err)
            authors_df = pd.DataFrame()

        if authors_df.empty:
            logger.warning(
                "t_authors is empty. Returning works DataFrame with empty author metadata."
            )
            works_df["author_name"] = "Unknown Author"
            works_df["author_birth_date"] = None
            return works_df

        authors_df = authors_df.rename(
            columns={"name": "author_name", "birth_date": "author_birth_date"}
        )

        merged_df = pd.merge(
            works_df,
            authors_df[["author_key", "author_name", "author_birth_date"]],
            on="author_key",
            how="left",
        )

        merged_df["author_name"] = merged_df["author_name"].fillna("Unknown Author")
        return merged_df
