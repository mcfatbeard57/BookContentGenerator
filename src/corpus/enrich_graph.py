"""Enrich Graph - Add priority data from corpus files to graph nodes"""
import json
from pathlib import Path

from src.config import (
    CORPUS_CHARACTERS_DIR,
    CORPUS_FACTIONS_DIR,
    CORPUS_LOCATIONS_DIR,
    CORPUS_TIMELINE_DIR,
    WORLD_GRAPH_PATH,
)
from src.enrichment.wiki_linker import parse_entity_frontmatter


def get_priority_map() -> dict[str, str]:
    """
    Build a mapping from entity_id to priority by scanning corpus files.
    
    Returns:
        Dict mapping entity_id -> priority ("canonical", "major", "minor")
    """
    priority_map: dict[str, str] = {}
    
    corpus_dirs = [
        CORPUS_CHARACTERS_DIR,
        CORPUS_LOCATIONS_DIR,
        CORPUS_FACTIONS_DIR,
        CORPUS_TIMELINE_DIR,
    ]
    
    for corpus_dir in corpus_dirs:
        if not corpus_dir.exists():
            continue
        
        for entity_file in corpus_dir.glob("*.md"):
            if entity_file.name.startswith("_"):
                continue
            
            frontmatter = parse_entity_frontmatter(entity_file)
            if frontmatter and "entity_id" in frontmatter:
                entity_id = frontmatter["entity_id"]
                priority = frontmatter.get("priority", "minor")
                priority_map[entity_id] = priority
    
    return priority_map


def enrich_graph_with_priority(graph_path: Path | None = None) -> None:
    """
    Add priority field to all nodes in the graph.
    """
    graph_path = graph_path or WORLD_GRAPH_PATH
    
    if not graph_path.exists():
        print(f"Error: Graph not found at {graph_path}")
        return
    
    # Load graph
    with open(graph_path, "r") as f:
        graph_data = json.load(f)
    
    # Get priority map from corpus files
    priority_map = get_priority_map()
    
    # Enrich nodes
    enriched_count = 0
    for entity_id, node in graph_data.get("nodes", {}).items():
        if entity_id in priority_map:
            node["priority"] = priority_map[entity_id]
            enriched_count += 1
        else:
            node["priority"] = "minor"  # Default
    
    # Save enriched graph
    with open(graph_path, "w") as f:
        json.dump(graph_data, f, indent=2, sort_keys=True)
    
    print(f"✓ Enriched {enriched_count} nodes with priority data")
    print(f"  Saved to: {graph_path}")


if __name__ == "__main__":
    enrich_graph_with_priority()
