"""Tests for graph builder module"""
import pytest

from src.models.graph import WorldGraph, Node, Edge


class TestWorldGraph:
    """Tests for WorldGraph operations"""
    
    def test_add_node(self):
        graph = WorldGraph()
        graph.add_node("char_harry", "character", "Harry Dresden")
        
        assert "char_harry" in graph.nodes
        assert graph.nodes["char_harry"].name == "Harry Dresden"
    
    def test_add_edge(self):
        graph = WorldGraph()
        graph.add_node("char_harry", "character", "Harry Dresden")
        graph.add_node("loc_chicago", "location", "Chicago")
        graph.add_edge("char_harry", "loc_chicago", "APPEARS_IN", "book1")
        
        assert len(graph.edges) == 1
        assert graph.edges[0].from_id == "char_harry"
        assert graph.edges[0].to_id == "loc_chicago"
    
    def test_add_duplicate_edge_increments_weight(self):
        graph = WorldGraph()
        graph.add_node("char_harry", "character", "Harry Dresden")
        graph.add_node("loc_chicago", "location", "Chicago")
        
        graph.add_edge("char_harry", "loc_chicago", "APPEARS_IN", "book1")
        graph.add_edge("char_harry", "loc_chicago", "APPEARS_IN", "book1")
        
        assert len(graph.edges) == 1
        assert graph.edges[0].weight == 2.0
    
    def test_get_edges_from(self):
        graph = WorldGraph()
        graph.add_node("char_harry", "character", "Harry Dresden")
        graph.add_node("loc_chicago", "location", "Chicago")
        graph.add_node("loc_edinburgh", "location", "Edinburgh")
        
        graph.add_edge("char_harry", "loc_chicago", "APPEARS_IN")
        graph.add_edge("char_harry", "loc_edinburgh", "APPEARS_IN")
        
        edges = graph.get_edges_from("char_harry")
        assert len(edges) == 2
    
    def test_get_edges_to(self):
        graph = WorldGraph()
        graph.add_node("char_harry", "character", "Harry")
        graph.add_node("char_murphy", "character", "Murphy")
        graph.add_node("loc_chicago", "location", "Chicago")
        
        graph.add_edge("char_harry", "loc_chicago", "APPEARS_IN")
        graph.add_edge("char_murphy", "loc_chicago", "APPEARS_IN")
        
        edges = graph.get_edges_to("loc_chicago")
        assert len(edges) == 2
    
    def test_get_related_entities(self):
        graph = WorldGraph()
        graph.add_node("char_harry", "character", "Harry")
        graph.add_node("char_murphy", "character", "Murphy")
        graph.add_node("loc_chicago", "location", "Chicago")
        
        graph.add_edge("char_harry", "char_murphy", "KNOWS")
        graph.add_edge("char_harry", "loc_chicago", "APPEARS_IN")
        
        related = graph.get_related_entities("char_harry")
        assert len(related) == 2
        assert "char_murphy" in related
        assert "loc_chicago" in related
    
    def test_get_related_entities_filtered(self):
        graph = WorldGraph()
        graph.add_node("char_harry", "character", "Harry")
        graph.add_node("char_murphy", "character", "Murphy")
        graph.add_node("loc_chicago", "location", "Chicago")
        
        graph.add_edge("char_harry", "char_murphy", "KNOWS")
        graph.add_edge("char_harry", "loc_chicago", "APPEARS_IN")
        
        related = graph.get_related_entities("char_harry", relation="KNOWS")
        assert len(related) == 1
        assert "char_murphy" in related
