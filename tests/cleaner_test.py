from processing.cleaner import DataCleaner, stream_dirty_catalog


def test_normalize_title():
    raw = "  pYthOn!!  aUtOmAtIoN  "
    assert DataCleaner.normalize_title(raw) == "Python Automation"


def test_normalize_title_empty_or_none():
    assert DataCleaner.normalize_title("") == "Unknown Title"
    assert DataCleaner.normalize_title(None) == "Unknown Title"


def test_validate_isbn():
    assert DataCleaner.validate_isbn("978-3-16-148410-0") is True
    assert DataCleaner.validate_isbn("0321125215") is True
    assert DataCleaner.validate_isbn("invalid_isbn_123") is False


def test_extract_isbns():
    sample = "Book ISBN is 978-3-16-148410-0 in text."
    isbns = DataCleaner.extract_isbns(sample)
    assert len(isbns) == 1
    assert "978-3-16-148410-0" in isbns[0]


def test_stream_dirty_catalog(tmp_path):
    csv_file = tmp_path / "test_catalog.csv"
    csv_file.write_text(
        "work_id,title,first_publish_year\nOL1W,Book One,2020\nOL2W,Book Two,2021\n",
        encoding="utf-8",
    )

    chunks = list(stream_dirty_catalog(str(csv_file), chunk_size=1))
    assert len(chunks) == 2
    assert chunks[0][0]["work_id"] == "OL1W"
    assert chunks[1][0]["title"] == "Book Two"
