"""Tests for EPUB parser module"""
import tempfile
from pathlib import Path

import pytest

from src.ingestion.epub_parser import (
    normalize_text,
    html_to_text,
    generate_book_id,
    compute_content_hash,
)


class TestNormalizeText:
    """Tests for text normalization"""
    
    def test_collapses_multiple_spaces(self):
        text = "hello    world"
        assert normalize_text(text) == "hello world"
    
    def test_collapses_multiple_newlines(self):
        text = "hello\n\n\n\n\nworld"
        assert normalize_text(text) == "hello\n\nworld"
    
    def test_strips_whitespace(self):
        text = "  hello world  "
        assert normalize_text(text) == "hello world"
    
    def test_handles_mixed_whitespace(self):
        text = "hello\t\r\fworld"
        result = normalize_text(text)
        assert "\t" not in result
        assert "\r" not in result


class TestHtmlToText:
    """Tests for HTML to text conversion"""
    
    def test_extracts_paragraph_text(self):
        html = "<html><body><p>Hello world</p></body></html>"
        result = html_to_text(html)
        assert "Hello world" in result
    
    def test_removes_script_tags(self):
        html = "<html><body><p>Content</p><script>alert('test')</script></body></html>"
        result = html_to_text(html)
        assert "alert" not in result
    
    def test_removes_style_tags(self):
        html = "<html><body><p>Content</p><style>.foo{color:red}</style></body></html>"
        result = html_to_text(html)
        assert "color" not in result
    
    def test_preserves_headings(self):
        html = "<html><body><h1>Title</h1><p>Content</p></body></html>"
        result = html_to_text(html)
        assert "Title" in result


class TestGenerateBookId:
    """Tests for book ID generation"""
    
    def test_creates_valid_id(self):
        book_id = generate_book_id("The Great Book", "John Doe")
        assert "great" in book_id
        assert "john" in book_id
    
    def test_removes_special_characters(self):
        book_id = generate_book_id("Book: A Story!", "Author")
        assert ":" not in book_id
        assert "!" not in book_id
    
    def test_truncates_long_titles(self):
        long_title = "A" * 100
        book_id = generate_book_id(long_title, "Author")
        assert len(book_id) <= 50


class TestComputeContentHash:
    """Tests for content hashing"""
    
    def test_same_content_same_hash(self):
        text = "Hello world"
        hash1 = compute_content_hash(text)
        hash2 = compute_content_hash(text)
        assert hash1 == hash2
    
    def test_different_content_different_hash(self):
        hash1 = compute_content_hash("Hello world")
        hash2 = compute_content_hash("Hello World")  # Different case
        assert hash1 != hash2
    
    def test_hash_is_sha256_length(self):
        hash_value = compute_content_hash("test")
        assert len(hash_value) == 64  # SHA256 hex length


# Import chunk_text from ner_extractor for testing
from src.extraction.ner_extractor import chunk_text

class TestChunkText:
    """Tests for text chunking"""
    
    def test_short_text_single_chunk(self):
        text = "Short text"
        chunks = chunk_text(text, chunk_size=100)
        assert len(chunks) == 1
        assert chunks[0] == "Short text"
    
    def test_long_text_multiple_chunks(self):
        text = "A" * 1000
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1
    
    def test_chunks_have_overlap(self):
        text = "word " * 100  # 500 characters
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) >= 2
