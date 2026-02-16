"""Connection Clustering - Build entity connections from co-occurrence

Entities appearing in the same text chunk or chapter form connections
with weights proportional to co-occurrence frequency.
"""
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Connection:
    """A weighted, undirected connection between two entities.

    Attributes:
        source_id: Identifier of the first entity.
        target_id: Identifier of the second entity.
        weight: Number of co-occurrences.
        co_occurrence_chapters: Chapters where both entities appeared.
    """
    source_id: str
    target_id: str
    weight: int = 1
    co_occurrence_chapters: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize connection to a JSON-compatible dictionary.

        Returns:
            Dictionary with ``source``, ``target``, ``weight``, and
            deduplicated ``co_occurrence_chapters``.
        """
        return {
            "source": self.source_id,
            "target": self.target_id,
            "weight": self.weight,
            "co_occurrence_chapters": sorted(set(self.co_occurrence_chapters)),
        }


def build_connections(
    entity_chunk_map: dict[str, list[str]],
    min_weight: int = 1,
) -> list[Connection]:
    """
    Build entity connections based on co-occurrence in chunks.
    
    Args:
        entity_chunk_map: Dict mapping entity_id -> list of chunk_ids where
                         that entity appears. Chunk IDs encode chapter info
                         (e.g., "chapter_3:chunk_2").
        min_weight: Minimum co-occurrence count to create a connection.
    
    Returns:
        List of Connection objects, sorted by weight descending.
    """
    # Invert the map: chunk_id -> set of entity_ids
    chunk_to_entities: dict[str, set[str]] = defaultdict(set)
    for entity_id, chunk_ids in entity_chunk_map.items():
        for chunk_id in chunk_ids:
            chunk_to_entities[chunk_id].add(entity_id)

    # Count co-occurrences between entity pairs
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    pair_chapters: dict[tuple[str, str], list[str]] = defaultdict(list)

    for chunk_id, entities in chunk_to_entities.items():
        entity_list = sorted(entities)  # Deterministic order
        # Extract chapter from chunk_id (e.g., "chapter_3:chunk_2" -> "chapter_3")
        chapter = chunk_id.split(":")[0] if ":" in chunk_id else chunk_id

        for i in range(len(entity_list)):
            for j in range(i + 1, len(entity_list)):
                pair = (entity_list[i], entity_list[j])
                pair_counts[pair] += 1
                pair_chapters[pair].append(chapter)

    # Build connections with minimum weight filter
    connections = []
    for (source_id, target_id), weight in pair_counts.items():
        if weight >= min_weight:
            connections.append(Connection(
                source_id=source_id,
                target_id=target_id,
                weight=weight,
                co_occurrence_chapters=pair_chapters[(source_id, target_id)],
            ))

    # Sort by weight descending for priority
    connections.sort(key=lambda c: c.weight, reverse=True)
    return connections
