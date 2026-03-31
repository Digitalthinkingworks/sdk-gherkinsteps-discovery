# embedding_service/tests/test_embedding.py

import math
import pytest
from fastapi.testclient import TestClient
from embedding_service.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── Health ────────────────────────────────────────────────────────────────────
def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["dimension"] == 384


# ── Basic embedding ───────────────────────────────────────────────────────────
def test_embed_returns_correct_shape(client):
    r = client.post("/embed", json={"texts": ["cancel order feature"]})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["dimension"] == 384
    assert len(body["embeddings"]) == 1
    assert len(body["embeddings"][0]) == 384


def test_embed_batch_returns_one_vector_per_text(client):
    texts = [
        "cancel order feature",
        "update stock levels in warehouse",
        "process return request",
    ]
    r = client.post("/embed", json={"texts": texts})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert len(body["embeddings"]) == 3


# ── Normalisation + cosine similarity ────────────────────────────────────────
def cosine(a: list[float], b: list[float]) -> float:
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a))
    mag_b = math.sqrt(sum(x ** 2 for x in b))
    return dot / (mag_a * mag_b)


def test_identical_texts_have_cosine_similarity_one(client):
    r = client.post("/embed", json={"texts": ["cancel order", "cancel order"]})
    vecs = r.json()["embeddings"]
    assert cosine(vecs[0], vecs[1]) > 0.9999


def test_semantically_similar_texts_score_higher_than_unrelated(client):
    r = client.post("/embed", json={
        "texts": [
            "cancel order processing",
            "processing orders cancelling",
            "update warehouse stock levels",
        ]
    })
    vecs = r.json()["embeddings"]
    sim_correct   = cosine(vecs[0], vecs[1])
    sim_unrelated = cosine(vecs[0], vecs[2])
    assert sim_correct > sim_unrelated, (
        f"Expected cancel≈cancel ({sim_correct:.3f}) > cancel≈inventory ({sim_unrelated:.3f})"
    )


# ── Validation ────────────────────────────────────────────────────────────────
def test_empty_texts_list_returns_422(client):
    r = client.post("/embed", json={"texts": []})
    assert r.status_code == 422


def test_whitespace_only_text_returns_422(client):
    r = client.post("/embed", json={"texts": ["   "]})
    assert r.status_code == 422


def test_oversized_batch_returns_422(client):
    r = client.post("/embed", json={"texts": ["x"] * 65})
    assert r.status_code == 422