# query_service/tests/test_graph.py

from query_service.graph.graph import run_query


def test_add_item_step_found():
    r = run_query("add a new item to inventory")
    assert r["type"] == "result"
    assert "add" in r["data"]["step_text"].lower()
    assert r["data"]["class_name"] == "InventorySteps"

def test_remove_item_step_found():
    r = run_query("remove an item from inventory")
    assert r["type"] == "result"
    assert "remove" in r["data"]["step_text"].lower()

def test_update_quantity_step_found():
    r = run_query("update quantity of an item")
    assert r["type"] == "result"
    assert "update" in r["data"]["step_text"].lower()

def test_ship_order_step_found():
    r = run_query("process shipment at warehouse")
    assert r["type"] == "result"
    assert r["data"]["class_name"] == "OrderFulfilmentSteps"

def test_hold_order_step_found():
    r = run_query("place a hold on an order")
    assert r["type"] == "result"
    assert "hold" in r["data"]["step_text"].lower()

def test_low_stock_step_found():
    r = run_query("view items with low stock")
    assert r["type"] == "result"
    assert "low stock" in r["data"]["step_text"].lower()

def test_export_report_step_found():
    r = run_query("export inventory report")
    assert r["type"] == "result"
    assert "export" in r["data"]["step_text"].lower()

def test_import_data_step_found():
    r = run_query("import inventory file")
    assert r["type"] == "result"
    assert "import" in r["data"]["step_text"].lower()

def test_result_card_has_step_fields():
    r = run_query("add item to inventory")
    assert r["type"] == "result"
    card = r["data"]
    for f in ("sdk_name", "class_name", "step_definition_file", "method_name",
              "keyword", "step_text", "usage_hint", "maven_coords", "confidence"):
        assert f in card, f"Missing field: {f}"

def test_usage_hint_contains_step_text():
    r = run_query("remove item from inventory")
    card = r["data"]
    # Hint should reference the keyword and method
    assert card["keyword"] in card["usage_hint"]

def test_keyword_is_valid_cucumber_keyword():
    r = run_query("verify item quantity after update")
    card = r["data"]
    assert card["keyword"] in ("Given", "When", "Then", "And")

def test_maven_coords_contains_sdk_name():
    r = run_query("search for an item")
    assert r["data"]["sdk_name"] in r["data"]["maven_coords"]

def test_different_queries_return_different_steps():
    add  = run_query("add item",    )["data"]["step_text"]
    ship = run_query("ship order")["data"]["step_text"]
    assert add != ship

def test_vague_query_does_not_crash():
    r = run_query("do something")
    assert r["type"] in ("result", "clarification")

def test_clarification_has_step_fields():
    r = run_query("process something in the system")
    if r["type"] == "clarification":
        for opt in r["data"]:
            for f in ("rank", "sdk_name", "class_name", "step_text", "confidence"):
                assert f in opt