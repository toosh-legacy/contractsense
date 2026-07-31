from sentence_transformers import SentenceTransformer
from app.services.chunker import TextChunk
from app.core.config import settings

_model = None


def get_model() -> SentenceTransformer:
    """
    Lazy-load the embedding model.
    First call loads it from disk (slow).
    Every call after returns the cached version (instant).
    """
    global _model
    if _model is None:
        print(f"Loading embedding model: {settings.embedding_model}")
        _model = SentenceTransformer(settings.embedding_model)
        print("Model loaded.")
    return _model


def embed_chunks(chunks: list[TextChunk]) -> list[dict]:
    """
    Convert a list of TextChunks into embeddings.
    """
    if not chunks:
        return []

    model = get_model()
    texts = [chunk.text for chunk in chunks]

    print(f"Embedding {len(texts)} chunks...")
    embeddings = model.encode(texts, show_progress_bar=True)
    print("Embedding complete.")

    results = []
    for chunk, embedding in zip(chunks, embeddings):
        results.append({
            "chunk_id": chunk.chunk_id,
            "text": chunk.text,
            "page_num": chunk.page_num,
            "chunk_index": chunk.chunk_index,
            "word_count": chunk.word_count,
            "embedding": embedding.tolist(),
        })

    return results


def embed_query(query: str) -> list[float]:
    """
    Embed a single search query string.
    """
    model = get_model()
    embedding = model.encode(query)
    return embedding.tolist()