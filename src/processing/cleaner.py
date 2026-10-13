import csv
import re
import unicodedata
from collections.abc import Generator

from logger import logger


class DataCleaner:
    """Utility engine for cleaning text strings, normalizing Unicode, and parsing ISBNs using Regular Expressions."""

    # Regex mejorada para agrupar el prefijo 978-/979- con su delimitador opcional
    ISBN_REGEX = re.compile(
        r"\b(?:(?:978|979)[-\s]?)?[0-9]{1,5}[-\s]?[0-9]{1,7}[-\s]?[0-9]{1,7}[-\s]?[0-9X]\b",
        re.IGNORECASE,
    )

    INVALID_TITLE_CHAR_REGEX = re.compile(r"[^\w\s\-\:\.\,]")

    @classmethod
    def normalize_title(cls, raw_title: str) -> str:
        """Decompose special Unicode characters, strip invalid symbols, and normalize whitespace."""
        if not raw_title or not isinstance(raw_title, str):
            return "Unknown Title"

        normalized_unicode = unicodedata.normalize("NFKD", raw_title)
        ascii_text = "".join(
            char for char in normalized_unicode if not unicodedata.combining(char)
        )
        cleaned_chars = cls.INVALID_TITLE_CHAR_REGEX.sub("", ascii_text)
        normalized_title = " ".join(cleaned_chars.split()).strip().title()

        return normalized_title or "Unknown Title"

    @classmethod
    def validate_isbn(cls, isbn_str: str) -> bool:
        """Strip hyphens/spaces and verify cleaned character length is exactly 10 or 13 digits."""
        if not isbn_str or not isinstance(isbn_str, str):
            return False

        cleaned = re.sub(r"[^\dX]", "", isbn_str.upper())
        return len(cleaned) in (10, 13)

    @classmethod
    def extract_isbns(cls, text: str) -> list[str]:
        """Extract all valid ISBN-10 and ISBN-13 occurrences from dirty raw text strings."""
        if not text or not isinstance(text, str):
            return []

        matches = cls.ISBN_REGEX.findall(text)
        valid_isbns: list[str] = []

        for match in matches:
            cleaned_match = match.strip()
            if cls.validate_isbn(cleaned_match):
                valid_isbns.append(cleaned_match)

        logger.debug("Extracted %d valid ISBN(s) from text input.", len(valid_isbns))
        return valid_isbns


def stream_dirty_catalog(
    file_path: str, chunk_size: int = 1000
) -> Generator[list[dict[str, str]]]:
    """Yield chunks of catalog records from a large CSV file to bound memory consumption."""
    with open(file_path, mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        chunk = []
        for row in reader:
            chunk.append(row)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk
