# query_service/tests/test_api.py

import pytest
from fastapi.testclient import TestClient
from query_service.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

def test_query_add_item_returns_result(client):
    r = client.post("/query", json={"query": "add a new item to inventory"})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "result"
    # New schema: check step_text contains "add", not tags
    assert "add" in body["data"]["step_text"].lower(), (
        f"Expected 'add' in step_text. Got: {body['data']['step_text']}"
    )

# REPLACE this test:
def test_query_ship_order_returns_result(client):
    r = client.post("/query", json={"query": "ship a customer order"})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "result"
    # New schema: check class_name or step_text, not tags
    assert (
        "OrderFulfilment" in body["data"]["class_name"] or
        "ship" in body["data"]["step_text"].lower() or
        "shipment" in body["data"]["step_text"].lower()
    ), f"Unexpected result: {body['data']}"

# REPLACE this test:
def test_clarification_response_has_ranked_options(client):
    r = client.post("/query", json={"query": "process something"})
    assert r.status_code == 200
    body = r.json()
    if body["type"] == "clarification":
        assert len(body["data"]) >= 1
        assert body["data"][0]["rank"] == 1
        # New schema: step_text instead of scenario_name
        assert "step_text" in body["data"][0], (
            f"Expected 'step_text' in clarification option. "
            f"Got keys: {list(body['data'][0].keys())}"
        )