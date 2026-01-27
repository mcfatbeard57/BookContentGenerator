"""Ingestion Registry - Track processed books to enable incremental ingestion"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import orjson

from src.config import INGESTION_LOG_PATH


@dataclass
class BookRecord:
    """Record of a processed book"""
    
    book_id: str
    file_path: str
    content_hash: str
    title: str
    author: str
    chapter_count: int
    word_count: int
    processed_at: str  # ISO format timestamp
    entities_extracted: int = 0


@dataclass
class IngestionRegistry:
    """Registry tracking all processed books"""
    
    processed_books: dict[str, BookRecord] = field(default_factory=dict)
    
    def is_processed(self, content_hash: str) -> bool:
        """Check if a book with this content hash has already been processed"""
        for record in self.processed_books.values():
            if record.content_hash == content_hash:
                return True
        return False
    
    def get_record_by_hash(self, content_hash: str) -> BookRecord | None:
        """Get book record by content hash"""
        for record in self.processed_books.values():
            if record.content_hash == content_hash:
                return record
        return None
    
    def get_record_by_id(self, book_id: str) -> BookRecord | None:
        """Get book record by book ID"""
        return self.processed_books.get(book_id)
    
    def add_record(self, record: BookRecord) -> None:
        """Add or update a book record"""
        self.processed_books[record.book_id] = record
    
    def update_entity_count(self, book_id: str, count: int) -> None:
        """Update the entity count for a processed book"""
        if book_id in self.processed_books:
            self.processed_books[book_id].entities_extracted = count
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "processed_books": {
                book_id: {
                    "book_id": record.book_id,
                    "file_path": record.file_path,
                    "content_hash": record.content_hash,
                    "title": record.title,
                    "author": record.author,
                    "chapter_count": record.chapter_count,
                    "word_count": record.word_count,
                    "processed_at": record.processed_at,
                    "entities_extracted": record.entities_extracted,
                }
                for book_id, record in self.processed_books.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "IngestionRegistry":
        """Create registry from dictionary"""
        registry = cls()
        
        for book_id, record_data in data.get("processed_books", {}).items():
            registry.processed_books[book_id] = BookRecord(
                book_id=record_data["book_id"],
                file_path=record_data["file_path"],
                content_hash=record_data["content_hash"],
                title=record_data["title"],
                author=record_data["author"],
                chapter_count=record_data["chapter_count"],
                word_count=record_data["word_count"],
                processed_at=record_data["processed_at"],
                entities_extracted=record_data.get("entities_extracted", 0),
            )
        
        return registry


def load_registry(path: Path | None = None) -> IngestionRegistry:
    """
    Load the ingestion registry from disk.
    
    Returns empty registry if file doesn't exist.
    """
    path = path or INGESTION_LOG_PATH
    
    if not path.exists():
        return IngestionRegistry()
    
    try:
        with open(path, "rb") as f:
            data = orjson.loads(f.read())
        return IngestionRegistry.from_dict(data)
    except (json.JSONDecodeError, orjson.JSONDecodeError) as e:
        print(f"Warning: Could not parse registry file, starting fresh: {e}")
        return IngestionRegistry()


def save_registry(registry: IngestionRegistry, path: Path | None = None) -> None:
    """Save the ingestion registry to disk."""
    path = path or INGESTION_LOG_PATH
    
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write with orjson for performance
    with open(path, "wb") as f:
        f.write(orjson.dumps(
            registry.to_dict(),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        ))


def create_book_record(
    book_id: str,
    file_path: Path,
    content_hash: str,
    title: str,
    author: str,
    chapter_count: int,
    word_count: int,
) -> BookRecord:
    """Create a new book record with current timestamp"""
    return BookRecord(
        book_id=book_id,
        file_path=str(file_path),
        content_hash=content_hash,
        title=title,
        author=author,
        chapter_count=chapter_count,
        word_count=word_count,
        processed_at=datetime.now().isoformat(),
    )
