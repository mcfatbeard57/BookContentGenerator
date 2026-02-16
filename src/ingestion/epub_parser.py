"""EPUB Parser - Extract chapters and text from EPUB files"""
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub


@dataclass
class Chapter:
    """Represents a chapter extracted from an EPUB.

    Attributes:
        index: Zero-based position of the chapter in the book.
        title: Chapter title (extracted or auto-generated).
        content: Plain text content, whitespace-normalized.
        word_count: Number of words in ``content``.
    """

    index: int
    title: str
    content: str  # plain text, normalized
    word_count: int


@dataclass
class ParsedBook:
    """Represents a fully parsed EPUB book.

    Attributes:
        file_path: Filesystem path to the source EPUB.
        title: Book title from EPUB metadata.
        author: Author name from EPUB metadata.
        book_id: Deterministic slug derived from title + author.
        content_hash: SHA-256 digest of all chapter content.
        chapters: Ordered list of parsed chapters.
    """

    file_path: Path
    title: str
    author: str
    book_id: str  # normalized slug
    content_hash: str  # SHA256 of full text
    chapters: list[Chapter]

    @property
    def full_text(self) -> str:
        """Concatenate all chapter content into a single string."""
        return "\n\n".join(ch.content for ch in self.chapters)

    @property
    def total_words(self) -> int:
        """Total word count across all chapters."""
        return sum(ch.word_count for ch in self.chapters)


def normalize_text(text: str) -> str:
    """Normalize text by collapsing whitespace and normalizing unicode.

    Applies NFC unicode normalization, collapses runs of whitespace to
    single spaces (preserving paragraph breaks), and strips edges.

    Args:
        text: Raw text string to normalize.

    Returns:
        Cleaned text with consistent whitespace and NFC-normalized unicode.
    """
    # Unicode normalize
    text = unicodedata.normalize("NFC", text)
    
    # Replace various whitespace with single space
    text = re.sub(r"[\t\r\f\v]+", " ", text)
    
    # Collapse multiple spaces (but preserve paragraph breaks)
    text = re.sub(r" +", " ", text)
    
    # Normalize line breaks (collapse 3+ newlines to 2)
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    return text.strip()


def html_to_text(html_content: str) -> str:
    """Convert HTML content to paragraph-separated plain text.

    Strips script/style/nav elements and extracts text from block-level
    elements, preserving paragraph structure.

    Args:
        html_content: Raw HTML string from an EPUB document.

    Returns:
        Plain text with paragraphs separated by double newlines.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove script, style, nav elements
    for element in soup(["script", "style", "nav", "header", "footer"]):
        element.decompose()
    
    # Get text with paragraph separation
    text_parts = []
    for element in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "div"]):
        text = element.get_text(separator=" ", strip=True)
        if text:
            text_parts.append(text)
    
    # If no structured content found, fall back to full text
    if not text_parts:
        text_parts = [soup.get_text(separator=" ", strip=True)]
    
    return "\n\n".join(text_parts)


def extract_chapter_title(item: epub.EpubItem, index: int) -> str:
    """Extract chapter title from an EPUB item.

    Tries the item's ``title`` attribute, then heading tags (h1-h3),
    then falls back to ``Chapter {index + 1}``.

    Args:
        item: An ``EpubItem`` with HTML content.
        index: Zero-based chapter index (used for fallback title).

    Returns:
        Extracted or generated chapter title string.
    """
    # Try to get title from item
    if hasattr(item, "title") and item.title:
        return item.title
    
    # Try to extract from HTML content
    content = item.get_content().decode("utf-8", errors="ignore")
    soup = BeautifulSoup(content, "html.parser")
    
    # Look for heading elements
    for tag in ["h1", "h2", "h3", "title"]:
        heading = soup.find(tag)
        if heading:
            title = heading.get_text(strip=True)
            if title and len(title) < 100:
                return title
    
    # Fallback to generic title
    return f"Chapter {index + 1}"


def generate_book_id(title: str, author: str) -> str:
    """Generate a deterministic, URL-safe book ID from title and author.

    Args:
        title: Book title.
        author: Author name.

    Returns:
        Lowercase slug of the form ``title_author``, max 50 chars.
    """
    # Combine title and author
    combined = f"{title}_{author}".lower()
    
    # Remove special characters, keep alphanumeric and spaces
    combined = re.sub(r"[^a-z0-9\s]", "", combined)
    
    # Replace spaces with underscores
    combined = re.sub(r"\s+", "_", combined)
    
    # Truncate if too long
    return combined[:50].strip("_")


def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hex digest of text content.

    Args:
        text: The text to hash.

    Returns:
        Full-length SHA-256 hex digest string.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_epub(file_path: Path | str) -> ParsedBook:
    """Parse an EPUB file and extract structured content.

    Handles missing metadata, empty chapters, and malformed HTML.

    Args:
        file_path: Filesystem path to the ``.epub`` file.

    Returns:
        ParsedBook with extracted chapters, metadata, and content hash.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not an ``.epub``.
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"EPUB file not found: {file_path}")
    
    if not file_path.suffix.lower() == ".epub":
        raise ValueError(f"Not an EPUB file: {file_path}")
    
    # Read EPUB
    book = epub.read_epub(str(file_path), options={"ignore_ncx": True})
    
    # Extract metadata
    title = "Unknown Title"
    author = "Unknown Author"
    
    # Get title
    title_meta = book.get_metadata("DC", "title")
    if title_meta:
        title = title_meta[0][0]
    
    # Get author
    creator_meta = book.get_metadata("DC", "creator")
    if creator_meta:
        author = creator_meta[0][0]
    
    # Generate book ID
    book_id = generate_book_id(title, author)
    
    # Extract chapters
    chapters: list[Chapter] = []
    chapter_index = 0
    
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            # Get HTML content
            html_content = item.get_content().decode("utf-8", errors="ignore")
            
            # Convert to plain text
            plain_text = html_to_text(html_content)
            
            # Normalize
            normalized_text = normalize_text(plain_text)
            
            # Skip if too short (likely navigation/metadata)
            if len(normalized_text) < 100:
                continue
            
            # Extract title
            chapter_title = extract_chapter_title(item, chapter_index)
            
            # Count words
            word_count = len(normalized_text.split())
            
            chapters.append(Chapter(
                index=chapter_index,
                title=chapter_title,
                content=normalized_text,
                word_count=word_count,
            ))
            
            chapter_index += 1
    
    # Compute content hash from all chapter text
    full_text = "\n\n".join(ch.content for ch in chapters)
    content_hash = compute_content_hash(full_text)
    
    return ParsedBook(
        file_path=file_path,
        title=title,
        author=author,
        book_id=book_id,
        content_hash=content_hash,
        chapters=chapters,
    )
