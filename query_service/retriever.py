# query_service/retriever.py

import logging
from rank_bm25 import BM25Okapi

from config.vectordb_factory import get_collection
from config.model_factory import embed_texts


logger = logging.getLogger(__name__)


def _embed_query(query: str) -> list[float]:
    return embed_texts([query])[0]


def _reciprocal_rank_fusion(
    vector_ids:  list[str],
    keyword_ids: list[str],
    k: int = 60,
) -> list[str]:
    """
    Merge two ranked lists into one using Reciprocal Rank Fusion.
    RRF score = 1/(k + rank). Higher is better. k=60 is the standard default.
    Returns a list of IDs sorted best-first.
    """
    scores: dict[str, float] = {}
    for rank, doc_id in enumerate(vector_ids, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    for rank, doc_id in enumerate(keyword_ids, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda x: scores[x], reverse=True)


# ── Core retrieval functions ───────────────────────────────────────────────────

def vector_search(
    query_vector: list[float],
    top_k:        int = 10,
    filters:      dict | None = None,
) -> list[dict]:
    """
    Pure vector search against Chroma.
    filters: Chroma 'where' clause, e.g. {"sdk_name": "supply-chain-sdk"}
    Returns list of result dicts with id, document, metadata, distance.
    """
    collection = get_collection()
    kwargs = dict(
        query_embeddings = [query_vector],
        n_results        = top_k,
        include          = ["documents", "metadatas", "distances"],
    )
    if filters:
        kwargs["where"] = filters

    results = collection.query(**kwargs)

    # Chroma returns nested lists (one per query) — unwrap the first (only) query
    ids       = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    return [
        {
            "id":       ids[i],
            "document": documents[i],
            "metadata": metadatas[i],
            # Chroma cosine returns distance (0=identical, 2=opposite).
            # Convert to similarity so higher = better, consistent with BM25.
            "score":    round(1 - distances[i], 4),
        }
        for i in range(len(ids))
    ]


def keyword_search(
    query:   str,
    top_k:   int = 10,
    filters: dict | None = None,
) -> list[dict]:
    """
    BM25 keyword search over all stored document strings.
    BM25 works on exact token overlap — catches tag names and exact
    scenario keywords that semantic search sometimes misses.
    filters: optional dict to pre-filter by metadata field equality
             e.g. {"sdk_name": "supply-chain-sdk"}
    """
    collection = get_collection()

    # Fetch all documents (with optional metadata filter)
    fetch_kwargs = dict(include=["documents", "metadatas"])
    if filters:
        fetch_kwargs["where"] = filters

    all_data  = collection.get(**fetch_kwargs)
    all_ids   = all_data["ids"]
    all_docs  = all_data["documents"]
    all_metas = all_data["metadatas"]

    if not all_docs:
        return []

    # Tokenise: lowercase, split on whitespace and brackets
    # This preserves tag tokens like "CancelProcess" as single terms
    def tokenise(text: str) -> list[str]:
        import re
        return re.findall(r"[A-Za-z0-9]+", text.lower())

    tokenised_corpus = [tokenise(doc) for doc in all_docs]
    bm25             = BM25Okapi(tokenised_corpus)
    query_tokens     = tokenise(query)
    scores           = bm25.get_scores(query_tokens)

    # Pair up and sort
    ranked = sorted(
        zip(all_ids, all_docs, all_metas, scores),
        key=lambda x: x[3],
        reverse=True,
    )

    return [
        {
            "id":       row[0],
            "document": row[1],
            "metadata": row[2],
            "score":    round(float(row[3]), 4),
        }
        for row in ranked[:top_k]
    ]


def hybrid_search(
    query:   str,
    top_k:   int = 5,
    filters: dict | None = None,
) -> list[dict]:
    """
    Hybrid search: vector + BM25 fused via Reciprocal Rank Fusion.

    Why both?
    - Vector search: catches semantic matches ("cancel order" → @CancelProcess)
    - BM25: catches exact tag/token matches ("CancelProcess" literal string)
    - RRF: rewards candidates that appear highly in BOTH lists

    Returns top_k results with full metadata, sorted best-first.
    The top result's 'score' is the raw vector similarity (0–1),
    used downstream by the LangGraph confidence node.
    """
    query_vector = _embed_query(query)

    # Fetch more candidates than needed — RRF re-ranks them
    fetch_k  = min(top_k * 3, 20)
    v_results = vector_search(query_vector, top_k=fetch_k, filters=filters)
    k_results = keyword_search(query,        top_k=fetch_k, filters=filters)

    # Extract ranked ID lists for RRF
    v_ids = [r["id"] for r in v_results]
    k_ids = [r["id"] for r in k_results]

    fused_ids = _reciprocal_rank_fusion(v_ids, k_ids)[:top_k]

    # Build a lookup so we can reconstruct full result dicts from fused order
    lookup = {r["id"]: r for r in v_results}
    lookup.update({r["id"]: r for r in k_results})

    fused_results = [lookup[doc_id] for doc_id in fused_ids if doc_id in lookup]

    # Attach the vector similarity score to every result as the canonical score
    # (BM25 scores are not normalised so we don't mix them directly)
    v_score_map = {r["id"]: r["score"] for r in v_results}
    for result in fused_results:
        result["score"] = v_score_map.get(result["id"], 0.0)

    logger.info(
        f"hybrid_search('{query}') → {len(fused_results)} results  "
        f"top_score={fused_results[0]['score'] if fused_results else 'n/a'}"
    )
    return fused_results