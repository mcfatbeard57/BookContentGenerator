"""FAISS Index - Build and query entity embeddings index"""
import json
from pathlib import Path

import numpy as np

from src.config import FAISS_INDEX_PATH, CORPUS_GRAPH_DIR
from src.models.entities import Entity
from src.rag.embedder import entity_to_embedding_text, get_embeddings_batch

# Import faiss with error handling
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("Warning: faiss-cpu not installed. RAG features will be disabled.")


# Metadata file path (stores entity_id -> index mapping)
INDEX_METADATA_PATH = CORPUS_GRAPH_DIR / "index_metadata.json"


class EntityIndex:
    """FAISS index for entity embeddings with metadata"""
    
    def __init__(self, dimension: int = 768):
        self.dimension = dimension
        self.index = None
        self.entity_ids: list[str] = []  # Maps index position to entity_id
        
        if FAISS_AVAILABLE:
            self.index = faiss.IndexFlatL2(dimension)
    
    def add_entities(self, entities: list[Entity]) -> None:
        """Add entities to the index"""
        if not FAISS_AVAILABLE:
            print("Warning: FAISS not available, skipping index update")
            return
        
        if not entities:
            return
        
        # Convert entities to embedding text
        texts = []
        for entity in entities:
            text = entity_to_embedding_text({
                "name": entity.name,
                "entity_type": entity.entity_type,
                "aliases": entity.aliases,
                "canonical_description": entity.canonical_description,
            })
            texts.append(text)
            self.entity_ids.append(entity.entity_id)
        
        # Get embeddings
        print(f"Generating embeddings for {len(texts)} entities...")
        embeddings = get_embeddings_batch(texts)
        
        # Convert to numpy array
        embeddings_array = np.array(embeddings, dtype=np.float32)
        
        # Add to index
        self.index.add(embeddings_array)
        print(f"  → Index now contains {self.index.ntotal} vectors")
    
    def search(self, query: str, k: int = 5) -> list[tuple[str, float]]:
        """
        Search for similar entities.
        
        Returns list of (entity_id, distance) tuples.
        """
        if not FAISS_AVAILABLE or self.index is None:
            return []
        
        from src.rag.embedder import get_embedding
        
        # Get query embedding
        query_embedding = get_embedding(query)
        query_array = np.array([query_embedding], dtype=np.float32)
        
        # Search
        distances, indices = self.index.search(query_array, k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.entity_ids):
                results.append((self.entity_ids[idx], float(distances[0][i])))
        
        return results
    
    def save(self, index_path: Path | None = None, metadata_path: Path | None = None) -> None:
        """Save index and metadata to disk"""
        index_path = index_path or FAISS_INDEX_PATH
        metadata_path = metadata_path or INDEX_METADATA_PATH
        
        # Ensure directories exist
        index_path.parent.mkdir(parents=True, exist_ok=True)
        
        if FAISS_AVAILABLE and self.index is not None:
            faiss.write_index(self.index, str(index_path))
        
        # Save metadata
        with open(metadata_path, "w") as f:
            json.dump({"entity_ids": self.entity_ids}, f, indent=2)
    
    @classmethod
    def load(
        cls,
        index_path: Path | None = None,
        metadata_path: Path | None = None,
        dimension: int = 768,
    ) -> "EntityIndex":
        """Load index and metadata from disk"""
        index_path = index_path or FAISS_INDEX_PATH
        metadata_path = metadata_path or INDEX_METADATA_PATH
        
        entity_index = cls(dimension=dimension)
        
        if FAISS_AVAILABLE and index_path.exists():
            entity_index.index = faiss.read_index(str(index_path))
        
        if metadata_path.exists():
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
                entity_index.entity_ids = metadata.get("entity_ids", [])
        
        return entity_index


def build_entity_index(entities: list[Entity]) -> EntityIndex:
    """Build a new FAISS index from entities"""
    index = EntityIndex()
    index.add_entities(entities)
    return index


def load_or_create_index() -> EntityIndex:
    """Load existing index or create empty one"""
    if FAISS_INDEX_PATH.exists() and INDEX_METADATA_PATH.exists():
        return EntityIndex.load()
    return EntityIndex()
