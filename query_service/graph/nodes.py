# query_service/graph/nodes.py

import os
import logging

from query_service.graph.state import QueryState
from query_service.retriever import hybrid_search, _embed_query

from config.model_factory import generate_usage_hint as factory_hint
from config.settings import (
    confidence_threshold as config_threshold,
    get as cfg_get,
    top_k_retrieval,
    maven_group_id,
)


logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = config_threshold()   # loaded from YAML


def embed_query_node(state: QueryState) -> QueryState:
    """
    Embed the user's natural language query into a vector.
    Calls the embedding microservice on port 8001.
    """
    logger.info(f"[embed_query] query='{state['query']}'")
    vector = _embed_query(state["query"])
    return {**state, "query_vector": vector}


# ── Node 2: retrieve ──────────────────────────────────────────────────────────

def retrieve_node(state: QueryState) -> QueryState:
    """
    Run hybrid search (vector + BM25 + RRF) against the Chroma index.
    Applies sdk_filter if provided.
    """
    known_sdks = list(cfg_get("ingestion").get("sdks", {}).keys())

    # Auto-detect SDK name mention in query
    filters = None
    if state.get("sdk_filter"):
        filters = {"sdk_name": state["sdk_filter"]}
    else:
        query_lower = state["query"].lower()
        for sdk in known_sdks:
            if sdk.lower() in query_lower:
                filters = {"sdk_name": sdk}
                break

    candidates = hybrid_search(
        query   = state["query"],
        top_k   = top_k_retrieval(),
        filters = filters,
    )
    return {**state, "candidates": candidates}


# ── Node 3: score_confidence ──────────────────────────────────────────────────

def score_confidence_node(state: QueryState) -> QueryState:
    """
    Inspect the top candidate's vector similarity score.
    Sets clarification_needed=True if below threshold,
    which routes the graph to the clarify node instead of synthesise.
    """
    candidates = state.get("candidates") or []

    if not candidates:
        logger.warning("[score_confidence] no candidates — routing to clarify")
        return {**state, "confidence": 0.0, "clarification_needed": True}

    top_score = candidates[0]["score"]
    needs_clarification = top_score < CONFIDENCE_THRESHOLD

    logger.info(
        f"[score_confidence] top_score={top_score:.3f}  "
        f"threshold={CONFIDENCE_THRESHOLD}  "
        f"clarification_needed={needs_clarification}"
    )
    return {
        **state,
        "confidence":           top_score,
        "clarification_needed": needs_clarification,
    }


# ── Node 4: synthesise ────────────────────────────────────────────────────────
def synthesise_node(state: QueryState) -> QueryState:
    """
    Format the top candidate into a structured result card.
    Phase 1 strategy:
      - If USE_LLM=true and Ollama is running: use LLM to write a 
        natural language usage hint.
      - Otherwise: build the card directly from metadata fields.
        This makes the system fully functional without any LLM dependency.
    """
    top  = state["candidates"][0]
    meta = top["metadata"]

    result = {
        "sdk_name":                 meta.get("sdk_name", ""),
        "sdk_version":              meta.get("sdk_version", ""),
        "class_name":               meta.get("class_name", ""),
        "step_definition_file":     meta.get("step_definition_file", ""),
        "method_name":              meta.get("method_name", ""),
        "keyword":                  meta.get("keyword", ""),
        "step_text":                meta.get("step_text", ""),
        "section":                  meta.get("section", ""),
        "github_url":               meta.get("github_url", ""),
        "confidence":               round(state["confidence"], 3),
        "usage_hint":               _generate_usage_hint(meta, state["query"]),
        "maven_coords":             _maven_coords(meta),
    }

    logger.info(f"[synthesise] result for step document '{meta.get('step_text')}'")
    return {**state, "result": result}


def _generate_usage_hint(meta: dict, query: str) -> str:
    """
    Generate a usage hint. Uses LLM if configured, otherwise
    builds a deterministic hint from metadata fields.
    """
    return factory_hint(meta, query)


def _maven_coords(meta: dict) -> str:
    sdk   = meta.get("sdk_name", "unknown-sdk")
    ver   = meta.get("sdk_version", "latest")
    group = maven_group_id(sdk)   # reads from YAML sdks section
    return (
        f"<dependency>\n"
        f"  <groupId>{group}</groupId>\n"
        f"  <artifactId>{sdk}</artifactId>\n"
        f"  <version>{ver}</version>\n"
        f"  <scope>test</scope>\n"
        f"</dependency>"
    )

# ── Node 5: clarify ───────────────────────────────────────────────────────────

def clarify_node(state: QueryState) -> QueryState:
    """
    Low-confidence path.
    Returns top-3 candidates with scores so the tester can disambiguate.
    The response is structured identically to the result card so the
    caller can render it the same way with a 'pick one' prompt.
    """
    candidates = state.get("candidates") or []
    top3       = candidates[:3]

    options = [
        {
            "rank":                     i + 1,
            "sdk_name":                 c["metadata"].get("sdk_name", ""),
            "class_name":               c["metadata"].get("class_name", ""),
            "step_definition_file":     c["metadata"].get("step_definition_file", ""),
            "method_name":              c["metadata"].get("method_name", ""),
            "keyword":                  c["metadata"].get("keyword", ""),
            "step_text":                c["metadata"].get("step_text", ""),
            "github_url":               c["metadata"].get("github_url", ""),
            "confidence":               round(c["score"], 3),
        }
        for i, c in enumerate(top3)
    ]

    top_score = candidates[0]["score"] if candidates else 0
    logger.info(f"[clarify] returning {len(options)} options  top_score={top_score:.3f}")
    return {**state, "clarification_options": options, "result": None}


# ── Router ────────────────────────────────────────────────────────────────────

def route_after_confidence(state: QueryState) -> str:
    """
    Conditional edge function.
    LangGraph calls this after score_confidence_node to decide
    which node runs next.
    Returns the node name as a string.
    """
    if state.get("clarification_needed"):
        return "clarify"
    return "synthesise"