"""Embedder - Generate embeddings via Ollama nomic-embed-text"""
import httpx

from src.config import EMBEDDING_MODEL, OLLAMA_BASE_URL


def get_embedding(text: str, model: str = EMBEDDING_MODEL) -> list[float]:
    """
    Get embedding for a single text using Ollama API.
    
    Args:
        text: Text to embed
        model: Embedding model name
    
    Returns:
        List of floats representing the embedding vector
    """
    url = f"{OLLAMA_BASE_URL}/api/embeddings"
    
    payload = {
        "model": model,
        "prompt": text,
    }
    
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        
        result = response.json()
        return result.get("embedding", [])


def get_embeddings_batch(
    texts: list[str],
    model: str = EMBEDDING_MODEL,
) -> list[list[float]]:
    """
    Get embeddings for multiple texts.
    
    Note: Ollama doesn't support true batching, so this processes sequentially.
    
    Args:
        texts: List of texts to embed
        model: Embedding model name
    
    Returns:
        List of embedding vectors
    """
    embeddings = []
    
    for text in texts:
        try:
            embedding = get_embedding(text, model)
            embeddings.append(embedding)
        except Exception as e:
            print(f"Warning: Failed to get embedding: {e}")
            # Return zero vector as fallback
            embeddings.append([0.0] * 768)  # nomic-embed-text dimension
    
    return embeddings


def entity_to_embedding_text(entity_dict: dict) -> str:
    """
    Convert entity to text suitable for embedding.
    
    Combines name, aliases, and description for semantic search.
    """
    parts = [
        f"Name: {entity_dict.get('name', '')}",
        f"Type: {entity_dict.get('entity_type', '')}",
    ]
    
    aliases = entity_dict.get("aliases", [])
    if aliases:
        parts.append(f"Also known as: {', '.join(aliases)}")
    
    description = entity_dict.get("canonical_description")
    if description:
        parts.append(f"Description: {description}")
    
    return "\n".join(parts)
