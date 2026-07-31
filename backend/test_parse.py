from app.services.pdf_parser import parse_pdf, get_document_stats
from app.services.chunker import chunk_document, get_chunk_stats
from app.services.embedder import embed_chunks, embed_query
from app.services.vector_store import store_embeddings, search

# ── Phase 1: Parse ───────────────────────────────────────────
print("=== PHASE 1: PARSING ===")
doc = parse_pdf("tests/fixtures/sample.pdf")
stats = get_document_stats(doc)
for key, value in stats.items():
    print(f"  {key}: {value}")

# ── Phase 2a: Chunk ──────────────────────────────────────────
print("\n=== PHASE 2A: CHUNKING ===")
chunks = chunk_document(doc, chunk_size=150, chunk_overlap=20)
chunk_stats = get_chunk_stats(chunks)
for key, value in chunk_stats.items():
    print(f"  {key}: {value}")

# Improvement 2 — print chunk boundaries
from app.services.chunker import print_chunk_boundaries
print_chunk_boundaries(chunks)

# ── Phase 2b: Embed ──────────────────────────────────────────
print("\n=== PHASE 2B: EMBEDDING ===")
embedded = embed_chunks(chunks)
print(f"  Embedded {len(embedded)} chunks")
print(f"  Embedding dimensions: {len(embedded[0]['embedding'])}")

# ── Phase 2c: Store ──────────────────────────────────────────
print("\n=== PHASE 2C: STORING IN CHROMADB ===")
stored = store_embeddings("sample_contract", embedded)
print(f"  Stored {stored} chunks in ChromaDB")

# ── Phase 2d: Search ─────────────────────────────────────────
print("\n=== PHASE 2D: SEMANTIC SEARCH ===")
query = "What are the confidentiality obligations?"
print(f"  Query: '{query}'")

query_vector = embed_query(query)
results = search("sample_contract", query_vector, n_results=3)

for i, result in enumerate(results, 1):
    print(f"\n  Result {i} (similarity: {result['similarity_score']}, page {result['page_num']}):")
    print(f"  {result['text'][:200]}")