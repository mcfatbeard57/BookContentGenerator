"""Pydantic models for the knowledge graph"""
from typing import Literal

from pydantic import BaseModel, Field

from src.config import RELATIONSHIP_TYPES


RelationType = Literal[
    "APPEARS_IN",
    "MEMBER_OF", 
    "KNOWS",
    "LOCATED_IN",
    "PARTICIPATES_IN",
]


class Node(BaseModel):
    """A node in the knowledge graph representing an entity"""
    
    entity_id: str
    entity_type: str
    name: str


class Edge(BaseModel):
    """An edge in the knowledge graph representing a relationship"""
    
    from_id: str
    to_id: str
    relation: RelationType
    source: str | None = None  # book_id or chapter that established this
    weight: float = 1.0  # relationship strength (frequency-based)


class WorldGraph(BaseModel):
    """The complete knowledge graph for a corpus"""
    
    nodes: dict[str, Node] = Field(default_factory=dict)  # entity_id -> Node
    edges: list[Edge] = Field(default_factory=list)
    
    def add_node(self, entity_id: str, entity_type: str, name: str) -> None:
        """Add or update a node in the graph"""
        self.nodes[entity_id] = Node(
            entity_id=entity_id,
            entity_type=entity_type,
            name=name,
        )
    
    def add_edge(
        self,
        from_id: str,
        to_id: str,
        relation: RelationType,
        source: str | None = None,
    ) -> None:
        """Add an edge if it doesn't already exist"""
        # Check for existing edge
        for edge in self.edges:
            if (
                edge.from_id == from_id
                and edge.to_id == to_id
                and edge.relation == relation
            ):
                # Edge exists, increment weight
                edge.weight += 1.0
                return
        
        # Add new edge
        self.edges.append(Edge(
            from_id=from_id,
            to_id=to_id,
            relation=relation,
            source=source,
        ))
    
    def get_node(self, entity_id: str) -> Node | None:
        """Get a node by ID"""
        return self.nodes.get(entity_id)
    
    def get_edges_from(self, entity_id: str) -> list[Edge]:
        """Get all edges originating from an entity"""
        return [e for e in self.edges if e.from_id == entity_id]
    
    def get_edges_to(self, entity_id: str) -> list[Edge]:
        """Get all edges pointing to an entity"""
        return [e for e in self.edges if e.to_id == entity_id]
    
    def get_related_entities(
        self,
        entity_id: str,
        relation: RelationType | None = None,
    ) -> list[str]:
        """Get all entities related to the given entity"""
        related = set()
        
        for edge in self.edges:
            if relation and edge.relation != relation:
                continue
            
            if edge.from_id == entity_id:
                related.add(edge.to_id)
            elif edge.to_id == entity_id:
                related.add(edge.from_id)
        
        return list(related)
