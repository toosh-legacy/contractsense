from openai import OpenAI
from app.core.config import settings

# Initialise the client once at module level
# same pattern as the embedding model — load once, reuse everywhere
client = OpenAI(api_key=settings.openai_api_key)


def analyze_clause(clause_text: str) -> dict:
    """
    Send a single chunk of contract text to the LLM and get back
    a structured risk analysis.

    Args:
        clause_text: A chunk of contract text

    Returns:
        A dict with risk_level, clause_type, reason, and recommendation
    """
    prompt = f"""You are a contract analysis assistant. Analyze the following contract clause and return a JSON object with exactly these fields:

- "clause_type": the type of clause (e.g. "confidentiality", "termination", "liability", "payment", "intellectual_property", "dispute_resolution", "auto_renewal", "governing_law", "other")
- "risk_level": one of "LOW", "MEDIUM", or "HIGH"
- "reason": a plain English explanation of why this clause has this risk level (1-2 sentences, written for a non-lawyer)
- "recommendation": what the reader should do or watch out for (1 sentence)

Only return the JSON object. No markdown, no backticks, no explanation outside the JSON.

Contract clause:
{clause_text}"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # cheap and fast, perfect for this task
        messages=[
            {
                "role": "system",
                "content": "You are a contract analysis assistant. You always respond with valid JSON only."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0,        # 0 = deterministic, we want consistent analysis
        max_tokens=300,
    )

    raw = response.choices[0].message.content.strip()

    # Parse the JSON response
    import json
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # If the LLM returns something unexpected, return a safe default
        result = {
            "clause_type": "other",
            "risk_level": "MEDIUM",
            "reason": "Could not analyze this clause automatically.",
            "recommendation": "Review this clause manually.",
        }

    return result


def extract_key_terms(full_text: str) -> dict:
    """
    Extract the key structured information from a full contract.

    This is different from clause analysis — instead of analyzing
    individual chunks, we ask the LLM to find specific named fields
    from the whole document.

    Args:
        full_text: The complete contract text (truncated if too long)

    Returns:
        A dict with parties, dates, and key terms
    """
    # Truncate to ~3000 words to stay within token limits
    # gpt-4o-mini has a 128k context window but we keep it cheap
    words = full_text.split()
    truncated = " ".join(words[:3000])

    prompt = f"""Extract the following information from this contract and return a JSON object with exactly these fields:

- "parties": list of party names mentioned (e.g. ["Acme Corp", "John Smith"])
- "effective_date": the date the agreement starts (string, or null if not found)
- "expiry_date": when the agreement ends (string, or null if not found)
- "governing_law": which jurisdiction's law governs (string, or null if not found)
- "contract_type": what kind of contract this is (e.g. "NDA", "Employment Agreement", "SaaS Agreement", "Lease")
- "key_obligations": list of the 3 most important obligations (plain English, max 15 words each)

Only return the JSON object. No markdown, no backticks, no extra text.

Contract:
{truncated}"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a contract analysis assistant. You always respond with valid JSON only."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0,
        max_tokens=500,
    )

    raw = response.choices[0].message.content.strip()

    import json
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "parties": [],
            "effective_date": None,
            "expiry_date": None,
            "governing_law": None,
            "contract_type": "Unknown",
            "key_obligations": [],
        }

    return result


def answer_question(question: str, context_chunks: list[str]) -> dict:
    """
    Answer a user's question about a contract using retrieved chunks.

    This is the RAG generation step — we already retrieved the relevant
    chunks via ChromaDB, now we pass them to the LLM as context.

    Args:
        question: The user's natural language question
        context_chunks: List of relevant text chunks from vector search

    Returns:
        A dict with the answer and the source text it came from
    """
    # Join the chunks into a single context block
    context = "\n\n---\n\n".join(context_chunks)

    prompt = f"""You are a contract analysis assistant. Answer the user's question based ONLY on the contract text provided below. 

If the answer is not in the provided text, say "I could not find information about this in the contract."

Be concise and specific. Quote the relevant part of the contract when helpful.

Contract excerpts:
{context}

Question: {question}"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a contract analysis assistant. Answer questions based only on the provided contract text."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0,
        max_tokens=500,
    )

    answer = response.choices[0].message.content.strip()

    return {
        "answer": answer,
        "sources": context_chunks,
    }