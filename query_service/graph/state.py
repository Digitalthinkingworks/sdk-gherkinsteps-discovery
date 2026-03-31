# query_service/graph/state.py

from typing import TypedDict, Optional


class QueryState(TypedDict):
    """
    Shared state that flows through every LangGraph node.
    Each node reads what it needs and writes its outputs back here.
    Immutable fields (query, filters) are set at entry and never changed.
    """

    # ── Set at graph entry ────────────────────────────────────────────
    query:       str            # raw natural language query from the tester
    sdk_filter:  Optional[str]  # optional SDK name to narrow the search

    # ── Written by embed_query_node ───────────────────────────────────
    query_vector: Optional[list[float]]

    # ── Written by retrieve_node ──────────────────────────────────────
    candidates:   Optional[list[dict]]  # top-k results from hybrid_search

    # ── Written by score_confidence_node ─────────────────────────────
    confidence:            Optional[float]  # top candidate vector similarity
    clarification_needed:  Optional[bool]

    # ── Written by synthesise_node ────────────────────────────────────
    result:  Optional[dict]   # final formatted card returned to the tester

    # ── Written by clarify_node ───────────────────────────────────────
    clarification_options: Optional[list[dict]]  # top-3 for user to choose from