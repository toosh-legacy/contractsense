import chromadb
from chromadb.config import Settings as ChromaSettings
from app.core.config import settings


def get_chroma_client() -> chromadb.Client:
    """
    Create a persistent ChromaDB client.
    'Persistent' means it saves to disk so your vectors
    survive between restarts — not just in memory.
    """
    client = chromadb.PersistentClient(
        path=settings.chroma_dir,
    )
    return client


def get_or_create_collection(client: chromadb.Client, collection_name: str):
    """
    Get an existing collection or create it if it doesn't exist.
    A collection is like a table in a database — it holds
    all the vectors for one document or group of documents.
    """
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
        # cosine similarity: measures the angle between vectors
        # better than euclidean distance for text embeddings
    )
    return collection


def store_embeddings(collection_name: str, embedded_chunks: list[dict]) -> int:
    """
    Store embedded chunks in ChromaDB.

    Args:
        collection_name: Name for this document's collection
        embedded_chunks: Output from embedder.embed_chunks()

    Returns:
        Number of chunks stored
    """
    client = get_chroma_client()
    collection = get_or_create_collection(client, collection_name)

    # ChromaDB expects four parallel lists:
    # ids, embeddings, documents (the text), and metadatas
    ids = [chunk["chunk_id"] for chunk in embedded_chunks]
    embeddings = [chunk["embedding"] for chunk in embedded_chunks]
    documents = [chunk["text"] for chunk in embedded_chunks]
    metadatas = [
        {
            "page_num": chunk["page_num"],
            "chunk_index": chunk["chunk_index"],
            "word_count": chunk["word_count"],
        }
        for chunk in embedded_chunks
    ]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    return len(ids)


def get_all_chunks(collection_name: str) -> list[dict]:
    """
    Read every chunk of a document back out of ChromaDB, in order.

    Upload already parsed, chunked and stored this document. Anything
    that needs the whole contract afterwards can read it back from here
    instead of asking the user to upload the same PDF a second time.

    Args:
        collection_name: Which document collection to read

    Returns:
        List of chunks sorted by chunk_index, each with
        chunk_id, text, page_num and chunk_index
    """
    client = get_chroma_client()
    collection = get_or_create_collection(client, collection_name)

    # No query here — collection.get() with no filter returns everything
    results = collection.get(include=["documents", "metadatas"])

    chunks = []
    for chunk_id, doc, meta in zip(
        results["ids"],
        results["documents"],
        results["metadatas"],
    ):
        chunks.append({
            "chunk_id": chunk_id,
            "text": doc,
            "page_num": meta.get("page_num", 1),
            "chunk_index": meta.get("chunk_index", 0),
        })

    # Chroma makes no promise about ordering, and reading a contract
    # out of order would scramble the analysis
    chunks.sort(key=lambda c: c["chunk_index"])

    return chunks


def collection_exists(collection_name: str) -> bool:
    """
    Check whether a document has been uploaded and indexed.

    Note we deliberately do not use get_or_create_collection here —
    that would create an empty collection as a side effect.
    """
    client = get_chroma_client()
    existing = [c.name for c in client.list_collections()]
    return collection_name in existing


def search(
    collection_name: str,
    query_embedding: list[float],
    n_results: int = 5,
) -> list[dict]:
    """
    Search for the most relevant chunks for a given query embedding.

    Args:
        collection_name: Which document collection to search
        query_embedding: The embedded query from embedder.embed_query()
        n_results: How many chunks to return

    Returns:
        List of matching chunks with their text, metadata, and similarity score
    """
    client = get_chroma_client()
    collection = get_or_create_collection(client, collection_name)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    # ChromaDB returns parallel lists — zip them into readable dicts
    matches = []
    for doc, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        matches.append({
            "text": doc,
            "page_num": meta["page_num"],
            "chunk_index": meta["chunk_index"],
            "similarity_score": round(1 - distance, 4),
            # distance is how far apart — we invert it to get similarity
            # 1.0 = identical, 0.0 = completely unrelated
        })

    return matches