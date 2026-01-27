"""Graph Builder - Construct and persist the knowledge graph"""
from pathlib import Path

import orjson

from src.config import WORLD_GRAPH_PATH
from src.models.entities import Entity, Faction, Location, TimelineEvent
from src.models.graph import Edge, Node, RelationType, WorldGraph


def load_graph(path: Path | None = None) -> WorldGraph:
    """Load the world graph from disk, or create empty if not exists"""
    path = path or WORLD_GRAPH_PATH
    
    if not path.exists():
        return WorldGraph()
    
    try:
        with open(path, "rb") as f:
            data = orjson.loads(f.read())
        
        # Reconstruct from JSON
        graph = WorldGraph()
        
        for entity_id, node_data in data.get("nodes", {}).items():
            graph.nodes[entity_id] = Node(
                entity_id=node_data["entity_id"],
                entity_type=node_data["entity_type"],
                name=node_data["name"],
            )
        
        for edge_data in data.get("edges", []):
            graph.edges.append(Edge(
                from_id=edge_data["from_id"],
                to_id=edge_data["to_id"],
                relation=edge_data["relation"],
                source=edge_data.get("source"),
                weight=edge_data.get("weight", 1.0),
            ))
        
        return graph
    
    except Exception as e:
        print(f"Warning: Could not load graph, starting fresh: {e}")
        return WorldGraph()


def save_graph(graph: WorldGraph, path: Path | None = None) -> None:
    """Persist the world graph to disk"""
    path = path or WORLD_GRAPH_PATH
    
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to JSON-serializable dict
    data = {
        "nodes": {
            entity_id: {
                "entity_id": node.entity_id,
                "entity_type": node.entity_type,
                "name": node.name,
            }
            for entity_id, node in graph.nodes.items()
        },
        "edges": [
            {
                "from_id": edge.from_id,
                "to_id": edge.to_id,
                "relation": edge.relation,
                "source": edge.source,
                "weight": edge.weight,
            }
            for edge in graph.edges
        ],
    }
    
    with open(path, "wb") as f:
        f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))


def add_entity_to_graph(graph: WorldGraph, entity: Entity) -> None:
    """Add an entity as a node to the graph"""
    graph.add_node(
        entity_id=entity.entity_id,
        entity_type=entity.entity_type,
        name=entity.name,
    )


def infer_relationships(
    graph: WorldGraph,
    entities: list[Entity],
    book_id: str,
) -> None:
    """
    Infer and add relationships between entities.
    
    Current relationship types:
    - APPEARS_IN: character/faction → location
    - MEMBER_OF: character → faction  
    - LOCATED_IN: location → parent location
    - PARTICIPATES_IN: character → timeline_event
    """
    # Build entity lookups by name for fuzzy matching
    entity_by_name: dict[str, Entity] = {}
    for entity in entities:
        entity_by_name[entity.name.lower()] = entity
        for alias in entity.aliases:
            entity_by_name[alias.lower()] = entity
    
    # Find locations for APPEARS_IN relationships
    locations = [e for e in entities if e.entity_type == "location"]
    location_names = {e.name.lower() for e in locations}
    for alias in [a for e in locations for a in e.aliases]:
        location_names.add(alias.lower())
    
    # Find factions for MEMBER_OF relationships
    factions = [e for e in entities if e.entity_type == "faction"]
    
    # Process each entity for relationships
    for entity in entities:
        # Location hierarchy (LOCATED_IN)
        if isinstance(entity, Location) and entity.parent_location_id:
            if entity.parent_location_id in graph.nodes:
                graph.add_edge(
                    from_id=entity.entity_id,
                    to_id=entity.parent_location_id,
                    relation="LOCATED_IN",
                    source=book_id,
                )
        
        # Faction base location
        if isinstance(entity, Faction) and entity.base_location_id:
            if entity.base_location_id in graph.nodes:
                graph.add_edge(
                    from_id=entity.entity_id,
                    to_id=entity.base_location_id,
                    relation="APPEARS_IN",
                    source=book_id,
                )
        
        # Timeline event participants
        if isinstance(entity, TimelineEvent):
            for participant_name in entity.participants:
                participant = entity_by_name.get(participant_name.lower())
                if participant:
                    graph.add_edge(
                        from_id=participant.entity_id,
                        to_id=entity.entity_id,
                        relation="PARTICIPATES_IN",
                        source=book_id,
                    )
            
            # Event location
            if entity.location_id and entity.location_id in graph.nodes:
                graph.add_edge(
                    from_id=entity.entity_id,
                    to_id=entity.location_id,
                    relation="APPEARS_IN",
                    source=book_id,
                )


def build_graph(
    entities: list[Entity],
    book_id: str,
    existing_graph: WorldGraph | None = None,
) -> WorldGraph:
    """
    Build or update the knowledge graph from entities.
    
    Args:
        entities: List of entities to add
        book_id: Source book identifier
        existing_graph: Optional existing graph to update
    
    Returns:
        Updated WorldGraph
    """
    graph = existing_graph or WorldGraph()
    
    print(f"Building graph with {len(entities)} entities...")
    
    # Add all entities as nodes
    for entity in entities:
        add_entity_to_graph(graph, entity)
    
    # Infer relationships
    infer_relationships(graph, entities, book_id)
    
    print(f"  → Graph has {len(graph.nodes)} nodes and {len(graph.edges)} edges")
    
    return graph
