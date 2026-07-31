import json

from openai import OpenAI
from app.core.config import settings

# Initialise the client once at module level
# same pattern as the embedding model — load once, reuse everywhere
client = OpenAI(api_key=settings.openai_api_key)

# The hidden clauses we hunt for. Giving the model a fixed list works
# far better than asking it to "find anything sneaky" — an open-ended
# question gets you a different answer every run, which is useless when
# the output feeds a score.
HIDDEN_CLAUSE_WATCHLIST = """- auto_renewal: the contract renews itself unless cancelled in a specific window
- unilateral_price_increase: one side can raise prices at its own discretion
- evergreen_term: the term extends indefinitely with no natural end
- indemnity_carve_out: an indemnity that sits outside the liability cap
- exclusivity: the customer is barred from using other suppliers
- change_of_control: rights that trigger, or are lost, if a party is acquired
- most_favoured_nation: an obligation to match terms given to other customers
- audit_rights: one side may inspect the other's records, often at their cost
- unilateral_amendment: one side can change the terms without agreement
- liquidated_damages: a fixed penalty payable on breach
- minimum_commitment: a volume or spend floor you pay for whether you use it or not
- automatic_escalation: fees, volumes or scope that ratchet up over time"""


# ── Shared plumbing ──────────────────────────────────────────

def chat_json(prompt: str, system: str, max_tokens: int, fallback: dict) -> dict:
    """
    Send a prompt and get a JSON object back.

    Every JSON-returning call in this file used to repeat the same
    create → strip → json.loads → fall back dance, so it lives here now.
    We ask the API for JSON mode explicitly rather than only begging
    for it in the prompt, which is much harder for the model to ignore.

    Args:
        prompt: The user message
        system: The system message
        max_tokens: Response length limit
        fallback: What to return if the model returns unusable JSON

    Returns:
        The parsed JSON object, or the fallback
    """
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0,        # 0 = deterministic, we want consistent analysis
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )

    choice = response.choices[0]
    raw = choice.message.content.strip()

    # A truncated response is still "valid" as far as the API is concerned,
    # but the JSON will be cut off mid-object and we will silently fall back
    # to "nothing found". On a risk report that reads as a clean bill of
    # health, so it needs to be loud rather than quiet.
    if choice.finish_reason == "length":
        print(
            f"LLM response hit the {max_tokens} token limit and was truncated. "
            "Raise max_tokens or shrink the batch."
        )

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print("LLM returned invalid JSON — using fallback.")
        return fallback


def chat_with_web_search(prompt: str, system: str) -> dict:
    """
    Ask the model a question and let it search the web if it wants to.

    This uses the Responses API rather than chat completions, because
    that is where OpenAI's hosted web_search tool lives. The model
    decides whether a search is actually needed — we are not forcing
    one on every call.

    Args:
        prompt: The question
        system: Instructions for how to answer

    Returns:
        {"text": str, "sources": [{"title", "url"}]}
    """
    if not settings.enable_web_search:
        # Turned off — answer from the model's own knowledge instead
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=700,
        )
        return {
            "text": response.choices[0].message.content.strip(),
            "sources": [],
        }

    response = _responses_create_with_search(prompt, system)

    return {
        "text": response.output_text.strip(),
        "sources": _extract_sources(response),
    }


def _responses_create_with_search(prompt: str, system: str):
    """
    Call the Responses API with the web search tool attached.

    Newer models take the tool as "web_search"; older ones, including
    some gpt-4o variants, only accept "web_search_preview". We try the
    current name first and fall back rather than pinning the project
    to one model family.
    """
    last_error = None

    for tool_type in ("web_search", "web_search_preview"):
        try:
            return client.responses.create(
                model=settings.openai_model,
                instructions=system,
                input=prompt,
                tools=[{"type": tool_type}],
            )
        except Exception as e:
            print(f"Web search tool '{tool_type}' rejected: {e}")
            last_error = e

    raise last_error


def _extract_sources(response) -> list[dict]:
    """
    Pull the cited URLs out of a Responses API result.

    Citations arrive as annotations hanging off the output text, so we
    walk the output items looking for url_citation entries. Duplicates
    are dropped — the model often cites the same page several times.
    """
    sources = []
    seen = set()

    for item in response.output:
        for content in getattr(item, "content", None) or []:
            for annotation in getattr(content, "annotations", None) or []:
                if getattr(annotation, "type", "") != "url_citation":
                    continue

                url = getattr(annotation, "url", "")
                if not url or url in seen:
                    continue

                seen.add(url)
                sources.append({
                    "title": getattr(annotation, "title", "") or url,
                    "url": url,
                })

    return sources


# ── Contract analysis ────────────────────────────────────────

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

Contract clause:
{clause_text}"""

    return chat_json(
        prompt=prompt,
        system="You are a contract analysis assistant. You always respond with valid JSON only.",
        max_tokens=300,
        fallback={
            "clause_type": "other",
            "risk_level": "MEDIUM",
            "reason": "Could not analyze this clause automatically.",
            "recommendation": "Review this clause manually.",
        },
    )


def analyze_clause_batch(clause_texts: list[str]) -> list[dict]:
    """
    Analyze several chunks in one call.

    Analysing chunk by chunk means a 40-page contract costs dozens of
    round trips, one after another. Batching cuts that by roughly the
    batch size for the same quality of answer.

    On top of the normal risk fields, each clause is checked against the
    hidden clause watchlist and flagged as commercial or not, so the
    negotiation step later only has to look at the money terms.

    Args:
        clause_texts: Up to a handful of contract chunks

    Returns:
        One analysis dict per input chunk, in the same order
    """
    if not clause_texts:
        return []

    count = len(clause_texts)
    numbered = "\n\n".join(
        f"=== EXCERPT {i} ===\n{text}"
        for i, text in enumerate(clause_texts, start=1)
    )

    prompt = f"""Analyze the {count} contract excerpt(s) below.

Return a JSON object with a single key "excerpts", holding a list of EXACTLY {count} object(s) — one per excerpt, in order.

Each excerpt may itself contain several numbered contract sections. Do NOT return one object per numbered section. Return one object per EXCERPT, summarising that whole excerpt, however many sections it contains.

Each object must have:

- "excerpt": which excerpt it describes, from 1 to {count}
- "clause_type": the dominant subject of the excerpt — e.g. "confidentiality", "termination", "liability", "payment", "pricing", "intellectual_property", "dispute_resolution", "auto_renewal", "governing_law", "other"
- "risk_level": "LOW", "MEDIUM" or "HIGH" — the HIGHEST risk present anywhere in the excerpt
- "reason": plain English, 1-2 sentences, written for a non-lawyer
- "recommendation": what the reader should do about it (1 sentence)
- "is_commercial": true if anywhere in the excerpt covers price, fees, payment terms, contract length, renewal, volume commitments or discounts — false otherwise
- "hidden_clauses": every buried term found anywhere in the excerpt, from this watchlist ONLY:

{HIDDEN_CLAUSE_WATCHLIST}

Each hidden clause found must be an object with:
  - "type": the watchlist name exactly as written above
  - "severity": "LOW", "MEDIUM" or "HIGH"
  - "quote": the exact wording from the excerpt that triggered it (max 25 words)
  - "why_it_matters": the practical cost or exposure, in one sentence

List at most 6 hidden clauses per excerpt, worst first. Use an empty list when an excerpt contains none of them. Do not invent hidden clauses that are not in the text.

{numbered}"""

    result = chat_json(
        prompt=prompt,
        system="You are a contract analysis assistant. You always respond with valid JSON only.",
        # Budget generously. A clause carrying five hidden terms, each with
        # a quote and an explanation, runs past 1000 tokens on its own, and
        # under-budgeting is worse than it sounds: the reply truncates mid
        # object, the JSON fails to parse, and every clause in the batch
        # falls back to "nothing found" — a clean bill of health on a bad
        # contract. Unused budget costs nothing; we only pay for what the
        # model actually writes.
        max_tokens=min(12000, 1200 * count),
        fallback={"excerpts": []},
    )

    return _align_batch(result.get("excerpts", []), count)


def _align_batch(analyses: list, expected: int) -> list[dict]:
    """
    Force the model's batch output back into one entry per input chunk.

    The caller zips these against the original chunks, so a short or
    reordered list would attach the wrong analysis to the wrong piece of
    text. We place each entry by the excerpt number the model reported
    and pad any gaps with a safe default.

    The counting is 1-based to match the "=== EXCERPT n ===" labels the
    prompt uses, but we fall back to positional order when the model
    leaves the number out or numbers from zero.
    """
    items = [a for a in analyses if isinstance(a, dict)]

    by_position = {}
    for position, item in enumerate(items):
        number = item.get("excerpt")
        if isinstance(number, int) and 1 <= number <= expected:
            by_position[number - 1] = item
        elif position < expected:
            # No usable number — trust the order it came back in
            by_position.setdefault(position, item)

    if len(items) != expected:
        print(
            f"Batch analysis returned {len(items)} entries for {expected} "
            "excerpt(s); padding the difference."
        )

    aligned = []
    for i in range(expected):
        item = by_position.get(i, {})
        hidden = item.get("hidden_clauses") or []

        aligned.append({
            "clause_type": item.get("clause_type", "other"),
            "risk_level": item.get("risk_level", "MEDIUM"),
            "reason": item.get("reason", "Could not analyze this clause automatically."),
            "recommendation": item.get("recommendation", "Review this clause manually."),
            "is_commercial": bool(item.get("is_commercial", False)),
            "hidden_clauses": [h for h in hidden if isinstance(h, dict)],
        })

    return aligned


def detect_industry(text_sample: str, valid_keys: list[str]) -> dict:
    """
    Work out which industry's benchmarks to judge this contract against.

    The answer is constrained to keys we actually hold benchmarks for —
    a free-text industry guess would be useless to look up.

    Args:
        text_sample: The opening of the contract
        valid_keys: Industry keys from benchmarks.json

    Returns:
        {"industry": str, "contract_type": str, "confidence": str}
    """
    words = text_sample.split()
    truncated = " ".join(words[:1500])

    prompt = f"""Read the start of this contract and identify what it is.

Return a JSON object with exactly these fields:

- "industry": which of these categories best fits, chosen from this list ONLY: {", ".join(valid_keys)}. Use "default" if none clearly fits.
- "contract_type": what kind of agreement this is, e.g. "SaaS Subscription Agreement", "Master Services Agreement", "Freight Services Agreement"
- "confidence": "HIGH", "MEDIUM" or "LOW"

Contract:
{truncated}"""

    result = chat_json(
        prompt=prompt,
        system="You are a contract analysis assistant. You always respond with valid JSON only.",
        max_tokens=200,
        fallback={"industry": "default", "contract_type": "Unknown", "confidence": "LOW"},
    )

    # Never trust the model to stay inside the list
    if result.get("industry") not in valid_keys:
        result["industry"] = "default"

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

Contract:
{truncated}"""

    return chat_json(
        prompt=prompt,
        system="You are a contract analysis assistant. You always respond with valid JSON only.",
        max_tokens=500,
        fallback={
            "parties": [],
            "effective_date": None,
            "expiry_date": None,
            "governing_law": None,
            "contract_type": "Unknown",
            "key_obligations": [],
        },
    )


# ── Question answering ───────────────────────────────────────

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
        model=settings.openai_model,
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


def answer_with_advice(
    question: str,
    context_chunks: list[str],
    assessment_summary: str,
    benchmark_table: str,
) -> dict:
    """
    Answer a question with negotiation advice, not just a summary.

    Same retrieval as answer_question, but the prompt also carries what
    we already know about this contract — its scores, its hidden clauses,
    its off-market terms — plus the industry benchmarks. That is what
    turns "the contract says Net 15" into "Net 15 is below the Net 30
    market norm, ask for Net 45".

    The model may search the web when the question is about current
    market conditions rather than about the document.

    Args:
        question: The user's question
        context_chunks: Relevant chunks from vector search
        assessment_summary: Plain text summary of the cached assessment
        benchmark_table: Industry benchmarks as text

    Returns:
        {"answer": str, "sources": list[str], "web_sources": list[dict]}
    """
    context = "\n\n---\n\n".join(context_chunks)

    prompt = f"""A pricing team is reviewing the contract below and wants practical negotiation advice.

CONTRACT EXCERPTS:
{context}

WHAT WE ALREADY KNOW ABOUT THIS CONTRACT:
{assessment_summary}

INDUSTRY BENCHMARKS:
{benchmark_table}

QUESTION: {question}

Answer the question directly and concretely. Where the contract is off market, say what to ask for instead. If the question is about the contract's wording, answer from the excerpts and say so if the answer is not there. If the question is about current market conditions or typical pricing, search the web and cite what you find. Do not invent contract terms that are not in the excerpts."""

    system = (
        "You are a commercial contract negotiation advisor. Be concise and specific. "
        "Prefer concrete asks over general advice."
    )

    try:
        result = chat_with_web_search(prompt, system)
        return {
            "answer": result["text"],
            "sources": context_chunks,
            "web_sources": result["sources"],
        }
    except Exception as e:
        # Web search is a bonus, not a requirement — fall back to a
        # plain answer rather than failing the whole request
        print(f"Advice with web search failed, answering without it: {e}")

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=700,
        )

        return {
            "answer": response.choices[0].message.content.strip(),
            "sources": context_chunks,
            "web_sources": [],
        }
