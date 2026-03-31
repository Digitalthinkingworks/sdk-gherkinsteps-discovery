# query_service/tests/test_retriever.py

"""
Integration tests against the real Chroma index (step-definition based).
Index contains: InventorySteps.java, OrderFulfilmentSteps.java

Metadata fields available per document:
  sdk_name, sdk_version, class_name, step_definition_file,
  method_name, keyword, step_text, github_url, section

Pre-conditions:
  1. uvicorn embedding_service.main:app --port 8001  (must be running)
  2. chroma_db populated via run_pipeline()
"""

import pytest
from query_service.retriever import (
    vector_search, keyword_search, hybrid_search, _embed_query
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def top_step_texts(results: list[dict], n: int = 3) -> list[str]:
    return [r["metadata"].get("step_text", "") for r in results[:n]]

def top_methods(results: list[dict], n: int = 3) -> list[str]:
    return [r["metadata"].get("method_name", "") for r in results[:n]]

def top_classes(results: list[dict], n: int = 3) -> list[str]:
    return [r["metadata"].get("class_name", "") for r in results[:n]]

def top_keywords(results: list[dict], n: int = 3) -> list[str]:
    return [r["metadata"].get("keyword", "") for r in results[:n]]


# ── Connectivity ──────────────────────────────────────────────────────────────

def test_embedding_service_reachable():
    vec = _embed_query("test connectivity")
    assert len(vec) == 384


# ── Vector search ─────────────────────────────────────────────────────────────

def test_vector_search_remove_item_hits_remove_method():
    results = vector_search(_embed_query("remove item from inventory"), top_k=5)
    assert len(results) >= 1
    methods = top_methods(results)
    assert any("remove" in m.lower() for m in methods), (
        f"Expected a 'remove' method in top results. Got: {methods}"
    )

def test_vector_search_returns_score_between_0_and_1():
    results = vector_search(_embed_query("add item to inventory"), top_k=3)
    for r in results:
        assert 0.0 <= r["score"] <= 1.0

def test_vector_search_with_sdk_filter():
    results = vector_search(
        _embed_query("inventory item"),
        top_k=5,
        filters={"sdk_name": "supply-chain-sdk"},
    )
    assert all(r["metadata"]["sdk_name"] == "supply-chain-sdk" for r in results)

def test_vector_search_results_have_required_fields():
    results = vector_search(_embed_query("inventory"), top_k=3)
    for r in results:
        for field in ("id", "document", "metadata", "score"):
            assert field in r, f"Missing result field: '{field}'"
        for meta_key in ("sdk_name", "class_name", "method_name",
                         "keyword", "step_text", "github_url"):
            assert meta_key in r["metadata"], (
                f"Missing metadata key: '{meta_key}'. "
                f"Got keys: {list(r['metadata'].keys())}"
            )


# ── Keyword search ────────────────────────────────────────────────────────────

def test_keyword_search_method_name_addItem():
    """BM25 exact token match on method name."""
    results = keyword_search("addItem", top_k=5)
    methods = top_methods(results)
    assert any("addItem" in m or "add" in m.lower() for m in methods), (
        f"Expected addItem method in top results. Got: {methods}"
    )

def test_keyword_search_class_name_OrderFulfilment():
    """BM25 should surface OrderFulfilmentSteps when class name is queried."""
    results = keyword_search("OrderFulfilmentSteps", top_k=5)
    classes = top_classes(results)
    assert any("OrderFulfilment" in c for c in classes), (
        f"Expected OrderFulfilmentSteps in top results. Got: {classes}"
    )

def test_keyword_search_returns_results_for_known_term():
    results = keyword_search("inventory", top_k=5)
    assert len(results) >= 1

def test_keyword_search_scores_are_non_negative():
    results = keyword_search("update quantity", top_k=5)
    assert all(r["score"] >= 0 for r in results)


# ── Hybrid search — core quality tests ───────────────────────────────────────

def test_hybrid_add_item_hits_add_step():
    results = hybrid_search("add a new item to inventory", top_k=5)
    step_texts = top_step_texts(results, n=2)
    assert any("add" in s.lower() for s in step_texts), (
        f"Expected 'add' in top-2 step texts. Got: {step_texts}"
    )

def test_hybrid_update_quantity_hits_update_step():
    results = hybrid_search("update item quantity", top_k=5)
    step_texts = top_step_texts(results, n=2)
    assert any("update" in s.lower() or "quantity" in s.lower() for s in step_texts), (
        f"Expected 'update'/'quantity' in top-2 steps. Got: {step_texts}"
    )

def test_hybrid_remove_item_hits_remove_step():
    results = hybrid_search("remove item from inventory", top_k=5)
    step_texts = top_step_texts(results, n=2)
    assert any("remove" in s.lower() for s in step_texts), (
        f"Expected 'remove' in top-2 step texts. Got: {step_texts}"
    )

def test_hybrid_ship_order_hits_shipment_step():
    results = hybrid_search("ship a customer order", top_k=5)
    classes  = top_classes(results, n=3)
    assert any("OrderFulfilment" in c for c in classes), (
        f"Expected OrderFulfilmentSteps class in top-3. Got: {classes}"
    )

def test_hybrid_hold_order_hits_hold_step():
    results = hybrid_search("place an order on hold", top_k=5)
    step_texts = top_step_texts(results, n=3)
    assert any("hold" in s.lower() for s in step_texts), (
        f"Expected 'hold' in top-3 step texts. Got: {step_texts}"
    )

def test_hybrid_low_stock_hits_low_stock_step():
    results = hybrid_search("view items with low stock", top_k=5)
    step_texts = top_step_texts(results, n=3)
    assert any("low stock" in s.lower() or "stock" in s.lower() for s in step_texts), (
        f"Expected 'stock' in top-3 step texts. Got: {step_texts}"
    )

def test_hybrid_export_report_hits_export_step():
    results = hybrid_search("export inventory report", top_k=5)
    step_texts = top_step_texts(results, n=3)
    assert any("export" in s.lower() for s in step_texts), (
        f"Expected 'export' in top-3 step texts. Got: {step_texts}"
    )

def test_hybrid_top_score_is_plausible():
    results = hybrid_search("add item inventory", top_k=5)
    assert results[0]["score"] >= 0.35

def test_hybrid_different_queries_return_different_top_results():
    add_step  = hybrid_search("add new item",        top_k=1)[0]["metadata"]["step_text"]
    ship_step = hybrid_search("ship customer order", top_k=1)[0]["metadata"]["step_text"]
    assert add_step != ship_step, (
        f"Both queries returned the same step: '{add_step}'"
    )

def test_hybrid_sdk_filter_respected():
    results = hybrid_search(
        "item inventory",
        top_k=5,
        filters={"sdk_name": "supply-chain-sdk"},
    )
    assert all(r["metadata"]["sdk_name"] == "supply-chain-sdk" for r in results)

def test_hybrid_negative_quantity_validation_step():
    results = hybrid_search("reject negative quantity entry", top_k=5)
    step_texts = top_step_texts(results, n=3)
    assert any("quantity" in s.lower() or "reject" in s.lower()
               or "error" in s.lower() for s in step_texts), (
        f"Expected quantity/reject/error in top-3. Got: {step_texts}"
    )

def test_hybrid_import_data_hits_import_step():
    results = hybrid_search("import inventory data from file", top_k=5)
    step_texts = top_step_texts(results, n=3)
    assert any("import" in s.lower() for s in step_texts), (
        f"Expected 'import' in top-3 step texts. Got: {step_texts}"
    )

def test_hybrid_keyword_field_is_valid_cucumber_keyword():
    results = hybrid_search("verify item exists", top_k=3)
    keywords = top_keywords(results, n=3)
    valid = {"Given", "When", "Then", "And"}
    assert all(k in valid for k in keywords), (
        f"Found invalid Cucumber keyword(s): {keywords}"
    )