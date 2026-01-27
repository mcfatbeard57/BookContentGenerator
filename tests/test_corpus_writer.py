"""Tests for corpus writer module"""
from datetime import date
from pathlib import Path
import tempfile

import pytest

from src.models.entities import Character, Location, Faction, SourceReference
from src.corpus.writer import (
    entity_to_frontmatter,
    entity_to_markdown_body,
    entity_to_file_content,
    entity_to_filename,
)


@pytest.fixture
def sample_character():
    """Create a sample character for testing"""
    return Character(
        entity_id="char_harry",
        name="Harry Dresden",
        aliases=["Dresden", "Wizard Dresden"],
        sources=[SourceReference(source_type="book", source_id="storm_front")],
        first_appearance="Chapter 1",
        occurrence_count=50,
        last_updated=date(2026, 1, 27),
        canonical_description="Harry Dresden is a wizard and private investigator in Chicago.",
        physical_traits=["Tall", "Lean", "Wears leather duster"],
        personality_traits=["Sarcastic", "Principled"],
        abilities=["Evocation", "Thaumaturgy"],
        role="protagonist",
        species="human",
    )


@pytest.fixture
def sample_location():
    """Create a sample location for testing"""
    return Location(
        entity_id="loc_chicago",
        name="Chicago",
        aliases=["The Windy City"],
        sources=[SourceReference(source_type="book", source_id="storm_front")],
        last_updated=date(2026, 1, 27),
        canonical_description="A major city in Illinois, known for its supernatural underworld.",
        location_type="city",
        environment=["Urban", "Lake Michigan"],
        architecture=["Skyscrapers", "Historic buildings"],
        atmosphere=["Gritty", "Noir"],
    )


class TestEntityToFrontmatter:
    """Tests for YAML front-matter generation"""
    
    def test_includes_required_fields(self, sample_character):
        fm = entity_to_frontmatter(sample_character)
        
        assert fm["entity_type"] == "character"
        assert fm["entity_id"] == "char_harry"
        assert fm["name"] == "Harry Dresden"
        assert "Dresden" in fm["aliases"]
    
    def test_includes_sources(self, sample_character):
        fm = entity_to_frontmatter(sample_character)
        
        assert len(fm["sources"]) == 1
        assert fm["sources"][0]["source_id"] == "storm_front"


class TestEntityToMarkdownBody:
    """Tests for Markdown body generation"""
    
    def test_includes_canonical_description(self, sample_character):
        body = entity_to_markdown_body(sample_character)
        
        assert "## Canonical Description" in body
        assert "Harry Dresden is a wizard" in body
    
    def test_includes_physical_traits(self, sample_character):
        body = entity_to_markdown_body(sample_character)
        
        assert "## Physical Traits" in body
        assert "- Tall" in body
    
    def test_includes_location_specific_sections(self, sample_location):
        body = entity_to_markdown_body(sample_location)
        
        assert "## Location Type" in body
        assert "city" in body
        assert "## Environment" in body


class TestEntityToFileContent:
    """Tests for complete file content generation"""
    
    def test_has_yaml_delimiters(self, sample_character):
        content = entity_to_file_content(sample_character)
        
        assert content.startswith("---\n")
        assert "\n---\n" in content
    
    def test_has_markdown_after_frontmatter(self, sample_character):
        content = entity_to_file_content(sample_character)
        
        # Split at second delimiter
        parts = content.split("---\n", 2)
        assert len(parts) == 3
        markdown_part = parts[2]
        assert "## Canonical Description" in markdown_part


class TestEntityToFilename:
    """Tests for filename generation"""
    
    def test_uses_entity_id(self, sample_character):
        filename = entity_to_filename(sample_character)
        assert filename == "harry.md"
    
    def test_location_filename(self, sample_location):
        filename = entity_to_filename(sample_location)
        assert filename == "chicago.md"
