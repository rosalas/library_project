import asyncio
import subprocess
import sys
import time
from pathlib import Path
from textwrap import dedent

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from api.async_client import AsyncLibraryAPIClient
from api.sync_client import SyncLibraryAPIClient
from db.manager import DatabaseManager
from exceptions import LibraryException
from logger import logger
from processing.analytics import CatalogAnalytics
from processing.cleaner import DataCleaner, stream_dirty_catalog
from reporting.generator import ReportGenerator

console = Console()


class CLIApp:
    def __init__(self) -> None:
        self.db = DatabaseManager()
        self.sync_api = SyncLibraryAPIClient()
        self.async_api = AsyncLibraryAPIClient()
        self.report_gen = ReportGenerator()

    def display_main_menu(self) -> None:
        # Render the main terminal menu panel
        console.clear()
        menu_text = dedent("""
            [bold cyan][1][/bold cyan] Search & ingest works by subject (sync vs async benchmark)
            [bold cyan][2][/bold cyan] Search books by author, title, or subject (regex normalization)
            [bold cyan][3][/bold cyan] Process & deduplicate local catalog file (streamed ingestion)
            [bold cyan][4][/bold cyan] Generate analytical reports (Excel dashboard, CSV, JSON)
            [bold cyan][5][/bold cyan] System health & database maintenance
            [bold cyan][6][/bold cyan] Run local code quality diagnostic checks (Ruff & Pytest)
            [bold cyan][0][/bold cyan] Exit
        """).strip()
        console.print(
            Panel(
                menu_text.strip(),
                title="[bold blue]Terminal controller v1.0[/bold blue]",
                expand=False,
            )
        )

    def run(self) -> None:
        # Start the interactive application loop
        while True:
            self.display_main_menu()
            choice = Prompt.ask(
                "\n[bold yellow]Select an option[/bold yellow]",
                choices=["0", "1", "2", "3", "4", "5", "6"],
                default="0",
            )

            try:
                if choice == "1":
                    self._handle_subject_search()
                elif choice == "2":
                    self._handle_book_lookup()
                elif choice == "3":
                    self._handle_file_processing()
                elif choice == "4":
                    self._handle_report_generation()
                elif choice == "5":
                    self._handle_system_health()
                elif choice == "6":
                    self._handle_diagnostics()
                elif choice == "0":
                    console.print(
                        "\n[bold green]Shutting down the program. Goodbye![/bold green]"
                    )
                    sys.exit(0)
            except LibraryException as err:
                logger.warning("Application warning: %s", err)
                console.print(f"\n[bold red]Operation Error:[/bold red] {err}")
                Prompt.ask("\n[dim]Press Enter to return to main menu[/dim]")
            except Exception as err:  # noqa: BLE001
                logger.exception("Unexpected CLI failure: %s", err)
                console.print(
                    f"\n[bold red]An unexpected error occurred:[/bold red] {err}"
                )
                Prompt.ask("\n[dim]Press Enter to return to the main menu[/dim]")

    def _handle_subject_search(self) -> None:
        # Option 1: Ingest works by subject and execute performance benchmark
        console.print(
            "\n[bold blue]--- Option 1: Subject Ingestion & Sync vs Async Benchmark ---[/bold blue]\n"
        )

        subject = Prompt.ask(
            "Enter subject category to search (e.g., 'python', 'science_fiction')"
        ).strip()
        while not subject:
            console.print("[red]Subject cannot be empty.[/red]")
            subject = Prompt.ask("Enter subject category").strip()

        limit_str = Prompt.ask("Enter work limit to fetch", default="20")
        limit = int(limit_str) if limit_str.isdigit() and int(limit_str) > 0 else 20

        # 1. Sync fetch benchmark
        with console.status(
            f"[bold green]Executing synchronous fetch for '{subject}'...[/bold green]"
        ):
            start_sync = time.perf_counter()
            sync_response = self.sync_api.get_subject_works(subject, limit=limit)
            sync_duration = time.perf_counter() - start_sync

        raw_works = sync_response.get("works", [])

        # 2. Async fetch benchmark
        with console.status(
            f"[bold green]Executing asynchronous fetch for '{subject}'...[/bold green]"
        ):
            start_async = time.perf_counter()
            asyncio.run(self.async_api.fetch_subject_works_async(subject, limit=limit))
            async_duration = time.perf_counter() - start_async

        # 3. Process and upsert records
        parsed_works = []
        for w in raw_works:
            work_key = w.get("key", "").replace("/works/", "").strip()
            if not work_key:
                continue

            authors = w.get("authors", [])
            author_key = (
                authors[0].get("key", "").replace("/authors/", "").strip()
                if authors
                else None
            )
            subjects = w.get("subject", [])
            subject_tags = (
                ", ".join(subjects[:5]) if isinstance(subjects, list) else None
            )

            parsed_works.append(
                {
                    "work_id": work_key,
                    "title": DataCleaner.normalize_title(w.get("title", "")),
                    "first_publish_year": w.get("first_publish_year"),
                    "author_key": author_key,
                    "subject_tags": subject_tags,
                }
            )

        ingested_count = self.db.bulk_upsert_works(parsed_works)

        # 4. Display performance benchmarks
        speedup = sync_duration / async_duration if async_duration > 0 else 1.0
        table = Table(
            title=f"Performance Benchmark Results: '{subject}' ({len(parsed_works)} items)"
        )
        table.add_column("Execution Strategy", style="cyan", no_wrap=True)
        table.add_column("Duration (seconds)", style="magenta")
        table.add_column("Works Ingested to DB", style="green")

        table.add_row(
            "Synchronous HTTP Client", f"{sync_duration:.3f}s", str(ingested_count)
        )
        table.add_row(
            "Asynchronous HTTP Client", f"{async_duration:.3f}s", str(ingested_count)
        )
        console.print(table)

        console.print(
            f"\n[bold green]Async execution speedup factor: {speedup:.2f}x faster[/bold green]"
        )
        Prompt.ask("\n[dim]Press Enter to return to the main menu[/dim]")

    def _handle_book_lookup(self) -> None:
        # Option 2: Search books by title or author with normalized regex cleaning
        console.print(
            "\n[bold blue]--- Option 2: Search Books by Title / Author ---[/bold blue]\n"
        )

        query = Prompt.ask("Enter title, author, or keyword to search").strip()
        if not query:
            console.print("[yellow]Query empty. Canceling search.[/yellow]")
            Prompt.ask("\n[dim]Press Enter to return to main menu[/dim]")
            return

        normalized_query = DataCleaner.normalize_title(query)
        console.print(f"[dim]Normalized query string: '{normalized_query}'[/dim]")

        with console.status("[bold green]Searching Open Library API...[/bold green]"):
            search_data = self.sync_api.search_books(normalized_query, limit=10)

        docs = search_data.get("docs", [])
        if not docs:
            console.print("[yellow]No books found matching your query.[/yellow]")
            Prompt.ask("\n[dim]Press Enter to return to main menu[/dim]")
            return

        table = Table(title=f"Search Results for '{normalized_query}'")
        table.add_column("Work ID", style="dim")
        table.add_column("Title", style="bold white")
        table.add_column("Author(s)", style="cyan")
        table.add_column("First Published", style="magenta")

        for doc in docs:
            work_id = doc.get("key", "").replace("/works/", "")
            title = DataCleaner.normalize_title(doc.get("title", ""))
            authors = ", ".join(doc.get("author_name", [])[:2]) or "Unknown Author"
            year = str(doc.get("first_publish_year", "N/A"))

            table.add_row(work_id, title, authors, year)

        console.print(table)
        Prompt.ask("\n[dim]Press Enter to return to the main menu[/dim]")

    def _handle_file_processing(self) -> None:
        # Option 3: Stream and deduplicate dirty local CSV catalog files
        console.print(
            "\n[bold blue]--- Option 3: Process Local CSV Catalog File ---[/bold blue]\n"
        )

        file_path_input = Prompt.ask(
            "Enter path to CSV catalog file",
            default="data/sample_catalog.csv",
        )
        csv_path = Path(file_path_input)

        if not csv_path.exists():
            console.print(f"[bold red]File not found at '{csv_path}'.[/bold red]")
            Prompt.ask("\n[dim]Press Enter to return to main menu[/dim]")
            return

        total_processed = 0
        total_ingested = 0

        with console.status(
            "[bold green]Streaming and deduplicating catalog file...[/bold green]"
        ):
            for chunk in stream_dirty_catalog(str(csv_path), chunk_size=500):
                cleaned_records = []
                for idx, row in enumerate(chunk):
                    total_processed += 1
                    raw_title = row.get("title", "")
                    normalized_title = DataCleaner.normalize_title(raw_title)

                    work_id = (
                        row.get("work_id")
                        or row.get("isbn")
                        or f"CSV_ROW_{total_processed}"
                    )

                    cleaned_records.append(
                        {
                            "work_id": work_id.strip(),
                            "title": normalized_title,
                            "first_publish_year": row.get("first_publish_year"),
                            "author_key": row.get("author_key"),
                            "subject_tags": row.get("subject_tags"),
                        }
                    )

                ingested_count = self.db.bulk_upsert_works(cleaned_records)
                total_ingested += ingested_count

        console.print(
            f"\n[bold green]Successfully processed {total_processed} rows and upserted {total_ingested} works into database![/bold green]"
        )
        Prompt.ask("\n[dim]Press Enter to return to the main menu[/dim]")

    def _handle_report_generation(self) -> None:
        # Option 4: Run analytics engine and export multi-format reports
        console.print(
            "\n[bold blue]--- Option 4: Generate Analytical Reports ---[/bold blue]\n"
        )

        with console.status(
            "[bold green]Executing analytics pipeline & building reports...[/bold green]"
        ):
            analytics = CatalogAnalytics(self.db.get_connection())
            catalog_df = analytics.get_cleaned_catalog_df()
            author_df = analytics.summarize_by_author()

            if catalog_df.empty:
                console.print(
                    "[yellow]Database is empty. Please ingest data via Options 1 or 3 first.[/yellow]"
                )
                Prompt.ask("\n[dim]Press Enter to return to main menu[/dim]")
                return

            excel_path = self.report_gen.export_excel_dashboard(catalog_df, author_df)
            csv_path = self.report_gen.export_csv(catalog_df, "catalog_export.csv")

            summary_stats = {
                "total_works": len(catalog_df),
                "total_authors": len(author_df),
                "top_author": author_df.iloc[0].to_dict()
                if not author_df.empty
                else {},
            }
            json_path = self.report_gen.export_json_summary(
                summary_stats, "analytics_summary.json"
            )

        table = Table(title="Generated Analytical Reports")
        table.add_column("Report Format", style="cyan")
        table.add_column("Output File Path", style="green")

        table.add_row("Excel Dashboard (.xlsx)", str(excel_path))
        table.add_row("CSV Catalog Summary (.csv)", str(csv_path))
        table.add_row("JSON Executive Summary (.json)", str(json_path))

        console.print(table)
        Prompt.ask("\n[dim]Press Enter to return to the main menu[/dim]")

    def _handle_system_health(self) -> None:
        # Option 5: Inspect SQLite database metrics and purge expired cache entries
        console.print(
            "\n[bold blue]--- Option 5: System Health & Cache Maintenance ---[/bold blue]\n"
        )

        stats = self.db.get_database_stats()

        table = Table(title="SQLite Database Health Metrics")
        table.add_column("Metric Description", style="cyan")
        table.add_column("Value", style="bold green")

        table.add_row("Total Works Cataloged (`t_works`)", str(stats["works_count"]))
        table.add_row(
            "Total Authors Cataloged (`t_authors`)", str(stats["authors_count"])
        )
        table.add_row(
            "Valid Unexpired API Cache Entries", str(stats["valid_cache_entries"])
        )
        table.add_row(
            "Database Storage Size on Disk", f"{stats['database_size_mb']} MB"
        )

        console.print(table)

        if Confirm.ask("\nWould you like to purge expired API cache entries now?"):
            purged_count = self.db.purge_expired_cache()
            console.print(
                f"[bold green]Successfully purged {purged_count} expired cache records.[/bold green]"
            )

        Prompt.ask("\n[dim]Press Enter to return to the main menu[/dim]")

    def _handle_diagnostics(self) -> None:
        # Option 6: Programmatically run local code quality tools (Ruff and Pytest)
        console.print(
            "\n[bold blue]--- Option 6: Code Quality Diagnostics ---[/bold blue]\n"
        )

        # 1. Run Ruff linting
        console.print(
            "[bold cyan]1. Executing Ruff Lint Check (`uv run ruff check .`)...[/bold cyan]"
        )
        ruff_check = subprocess.run(
            ["uv", "run", "ruff", "check", "."],
            capture_output=True,
            text=True,
            check=False,
        )
        if ruff_check.returncode == 0:
            console.print(
                "[bold green]Ruff Linting Passed! No issues found.[/bold green]\n"
            )
        else:
            console.print(
                f"[bold red]Ruff Linting Errors:[/bold red]\n{ruff_check.stdout}\n{ruff_check.stderr}\n"
            )

        # 2. Run Pytest suite
        console.print(
            "[bold cyan]2. Executing Automated Test Suite (`uv run pytest`)...[/bold cyan]"
        )
        pytest_res = subprocess.run(
            ["uv", "run", "pytest"], capture_output=True, text=True, check=False
        )
        console.print(pytest_res.stdout)
        if pytest_res.returncode != 0:
            console.print(
                f"[bold red]Test Failures Encountered:[/bold red]\n{pytest_res.stderr}"
            )

        Prompt.ask("\n[dim]Press Enter to return to the main menu[/dim]")
