"""Tests for alias resolver module"""
import pytest

from src.extraction.alias_resolver import (
    resolve_aliases_fuzzy,
    merge_entities_by_alias_groups,
    AliasGroup,
)
from src.extraction.ner_extractor import RawEntity


class TestResolveAliasesFuzzy:
    """Tests for fuzzy string matching alias resolution"""
    
    def test_groups_similar_names(self):
        names = ["Harry Dresden", "Harry", "Dresden"]
        groups = resolve_aliases_fuzzy(names, threshold=70)
        
        # Should group at least some of these
        assert len(groups) >= 1
    
    def test_keeps_dissimilar_names_separate(self):
        names = ["Harry Dresden", "Bob the Skull", "Murphy"]
        groups = resolve_aliases_fuzzy(names, threshold=85)
        
        # Should have separate groups for each
        assert len(groups) == 3
    
    def test_empty_list_returns_empty(self):
        groups = resolve_aliases_fuzzy([])
        assert groups == []
    
    def test_single_name_returns_single_group(self):
        groups = resolve_aliases_fuzzy(["Harry"])
        assert len(groups) == 1
        assert groups[0].canonical_name == "Harry"


class TestMergeEntitiesByAliasGroups:
    """Tests for entity merging based on alias groups"""
    
    def test_merges_entities_in_same_group(self):
        entities = [
            RawEntity(
                name="Harry Dresden",
                aliases=[],
                entity_type="character",
                context="Context 1",
                source_chapter="Ch1",
                source_book="Book1",
            ),
            RawEntity(
                name="Dresden",
                aliases=[],
                entity_type="character",
                context="Context 2",
                source_chapter="Ch2",
                source_book="Book1",
            ),
        ]
        
        groups = [
            AliasGroup(
                canonical_name="Harry Dresden",
                aliases=["Dresden"],
                confidence=0.9,
            )
        ]
        
        resolved = merge_entities_by_alias_groups(entities, groups)
        
        assert len(resolved) == 1
        assert resolved[0].canonical_name == "Harry Dresden"
        assert "Dresden" in resolved[0].all_names
    
    def test_preserves_unrelated_entities(self):
        entities = [
            RawEntity(
                name="Harry",
                aliases=[],
                entity_type="character",
                context="",
                source_chapter="Ch1",
                source_book="Book1",
            ),
            RawEntity(
                name="Bob",
                aliases=[],
                entity_type="character",
                context="",
                source_chapter="Ch1",
                source_book="Book1",
            ),
        ]
        
        groups = []  # No groups
        
        resolved = merge_entities_by_alias_groups(entities, groups)
        
        assert len(resolved) == 2
    
    def test_combines_contexts(self):
        entities = [
            RawEntity(
                name="Harry",
                aliases=[],
                entity_type="character",
                context="First context",
                source_chapter="Ch1",
                source_book="Book1",
            ),
            RawEntity(
                name="Harry",
                aliases=[],
                entity_type="character",
                context="Second context",
                source_chapter="Ch2",
                source_book="Book1",
            ),
        ]
        
        groups = [
            AliasGroup(canonical_name="Harry", aliases=[], confidence=1.0)
        ]
        
        resolved = merge_entities_by_alias_groups(entities, groups)
        
        assert len(resolved) == 1
        assert len(resolved[0].contexts) == 2
