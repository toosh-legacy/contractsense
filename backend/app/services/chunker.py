import re
from dataclasses import dataclass
from app.services.pdf_parser import ParsedDocument


@dataclass
class TextChunk:
    """A single chunk of text ready for embedding."""
    chunk_id: str        # unique ID e.g. "sample_pdf_chunk_003"
    text: str            # the actual text content
    page_num: int        # which page this came from
    chunk_index: int     # position in the document (0, 1, 2...)
    char_count: int      # character length
    word_count: int      # word count


def chunk_document(
    doc: ParsedDocument,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[TextChunk]:
    """
    Split a ParsedDocument into overlapping chunks for embedding.

    We chunk by words rather than characters because word boundaries
    are more natural and LLMs think in tokens (close to words).

    Args:
        doc: A ParsedDocument from the PDF parser
        chunk_size: Target number of words per chunk
        chunk_overlap: Number of words to repeat between chunks
                      so context isn't lost at boundaries

    Returns:
        List of TextChunk objects ready for embedding,
        with low-quality chunks (under 30 words) filtered out.
    """
    words = doc.raw_text.split()

    if not words:
        return []

    chunks = []
    chunk_index = 0
    position = 0

    while position < len(words):
        end = min(position + chunk_size, len(words))
        chunk_words = words[position:end]
        chunk_text = " ".join(chunk_words)

        page_num = _estimate_page(doc, position, len(words))

        base_name = doc.filename.replace(".pdf", "").replace(" ", "_").lower()
        chunk_id = f"{base_name}_chunk_{chunk_index:03d}"

        chunks.append(TextChunk(
            chunk_id=chunk_id,
            text=chunk_text,
            page_num=page_num,
            chunk_index=chunk_index,
            char_count=len(chunk_text),
            word_count=len(chunk_words),
        ))

        chunk_index += 1
        position += chunk_size - chunk_overlap

    # Improvement 1 — filter out low-quality chunks
    # Chunks under 30 words are usually headers, footers, or
    # stray section titles. They add noise to search results
    # without containing enough context to be useful.
    chunks = [chunk for chunk in chunks if chunk.word_count >= 30]

    return chunks


def get_chunk_stats(chunks: list[TextChunk]) -> dict:
    """Return stats about a set of chunks."""
    if not chunks:
        return {"total_chunks": 0}

    word_counts = [c.word_count for c in chunks]
    return {
        "total_chunks": len(chunks),
        "avg_words_per_chunk": round(sum(word_counts) / len(word_counts)),
        "min_words": min(word_counts),
        "max_words": max(word_counts),
        "pages_covered": list(set(c.page_num for c in chunks)),
    }


def print_chunk_boundaries(chunks: list[TextChunk]) -> None:
    """
    Improvement 2 — print the start of every chunk so you can
    visually inspect whether your chunk size is right.

    If chunks start mid-sentence constantly, your size is too small.
    If every chunk looks like a completely different topic, it's too big.
    """
    print(f"\n=== CHUNK BOUNDARIES ({len(chunks)} chunks) ===")
    for chunk in chunks:
        preview = chunk.text[:80].replace("\n", " ")
        print(
            f"  [{chunk.chunk_id}] "
            f"page {chunk.page_num} | "
            f"{chunk.word_count} words | "
            f"{preview}..."
        )


def _estimate_page(doc: ParsedDocument, word_position: int, total_words: int) -> int:
    """
    Estimate which page a word at `word_position` comes from.

    We do this proportionally — if you're 50% through the document
    and the document has 4 pages, you're probably on page 2.
    """
    if total_words == 0 or doc.total_pages == 0:
        return 1

    progress = word_position / total_words
    estimated_page = int(progress * doc.total_pages) + 1
    return min(estimated_page, doc.total_pages)