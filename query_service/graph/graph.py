# query_service/graph/graph.py

from langgraph.graph import StateGraph, END

from query_service.graph.state import QueryState
from query_service.graph.nodes import (
    embed_query_node,
    retrieve_node,
    score_confidence_node,
    synthesise_node,
    clarify_node,
    route_after_confidence,
)


def build_graph():
    """
    Compile and return the LangGraph StateGraph.
    Call once at application startup and reuse the compiled graph.

    Graph topology:
        embed_query → retrieve → score_confidence
                                       ├─(high confidence)→ synthesise → END
                                       └─(low confidence) → clarify    → END
    """
    g = StateGraph(QueryState)

    # ── Register nodes ────────────────────────────────────────────────
    g.add_node("embed_query",       embed_query_node)
    g.add_node("retrieve",          retrieve_node)
    g.add_node("score_confidence",  score_confidence_node)
    g.add_node("synthesise",        synthesise_node)
    g.add_node("clarify",           clarify_node)

    # ── Edges ─────────────────────────────────────────────────────────
    g.set_entry_point("embed_query")
    g.add_edge("embed_query",      "retrieve")
    g.add_edge("retrieve",         "score_confidence")

    # Conditional branch after confidence scoring
    g.add_conditional_edges(
        "score_confidence",
        route_after_confidence,
        {
            "synthesise": "synthesise",
            "clarify":    "clarify",
        },
    )

    g.add_edge("synthesise", END)
    g.add_edge("clarify",    END)

    return g.compile()


# Module-level compiled graph — import and call directly
sdk_discovery_graph = build_graph()


def run_query(query: str, sdk_filter: str | None = None) -> dict:
    """
    Main entry point for the query service.
    Returns either a result card (high confidence) or
    clarification options (low confidence).
    """
    initial_state: QueryState = {
        "query":                query,
        "sdk_filter":           sdk_filter,
        "query_vector":         None,
        "candidates":           None,
        "confidence":           None,
        "clarification_needed": None,
        "result":               None,
        "clarification_options": None,
    }

    final_state = sdk_discovery_graph.invoke(initial_state)

    # Return whichever branch produced output
    if final_state.get("result"):
        return {
            "type":   "result",
            "data":   final_state["result"],
        }
    return {
        "type":    "clarification",
        "data":    final_state.get("clarification_options", []),
        "message": "Query matched multiple scenarios with low confidence. "
                   "Please pick the closest match.",
    }