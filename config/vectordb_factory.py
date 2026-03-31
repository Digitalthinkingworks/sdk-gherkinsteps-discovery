# config/vectordb_factory.py

import logging
from config.settings import get as cfg_get

logger = logging.getLogger(__name__)


def get_collection():
    """
    Return a collection handle for the configured vector store provider.
    Callers treat the returned object as a duck-typed collection —
    they call .upsert(), .query(), .get() without knowing the provider.

    Supported providers (config: vector_store.provider):
      - chroma    → ChromaCollection (default, Phase 1)
      - weaviate  → WeaviateCollection wrapper (Phase 2)
      - qdrant    → QdrantCollection wrapper (Phase 2)
    """
    provider = cfg_get("vector_store").get("provider", "chroma")

    if provider == "chroma":
        return _get_chroma_collection()
    elif provider == "weaviate":
        return _get_weaviate_collection()
    elif provider == "qdrant":
        return _get_qdrant_collection()
    else:
        raise ValueError(
            f"Unknown vector store provider: '{provider}'. "
            f"Supported: chroma, weaviate, qdrant"
        )


# ── Chroma ────────────────────────────────────────────────────────────────────

def _get_chroma_collection():
    import chromadb
    from chromadb.config import Settings

    cfg = cfg_get("vector_store").get("chroma", {})
    path       = cfg.get("path", "./chroma_db")
    collection = cfg.get("collection", "sdk_scenarios")

    client = chromadb.PersistentClient(
        path     = path,
        settings = Settings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name     = collection,
        metadata = {"hnsw:space": "cosine"},
    )


# ── Weaviate (Phase 2 stub) ───────────────────────────────────────────────────

def _get_weaviate_collection():
    """
    Returns a thin wrapper around Weaviate that exposes the same
    .upsert() / .query() / .get() interface as ChromaCollection,
    so callers need zero changes when switching providers.
    """
    try:
        import weaviate
    except ImportError:
        raise ImportError(
            "weaviate-client is not installed. "
            "Run: pip install weaviate-client"
        )

    cfg      = cfg_get("vector_store").get("weaviate", {})
    url      = cfg.get("url", "http://localhost:8080")
    api_key  = cfg.get("api_key", "")
    class_nm = cfg.get("class_name", "SdkStep")

    auth = weaviate.auth.AuthApiKey(api_key) if api_key else None
    client = weaviate.connect_to_custom(
        http_host = url.replace("http://", "").replace("https://", "").split(":")[0],
        http_port = int(url.split(":")[-1]) if ":" in url else 8080,
        http_secure = url.startswith("https"),
        auth_credentials = auth,
    )

    return _WeaviateCollectionAdapter(client, class_nm)


class _WeaviateCollectionAdapter:
    """
    Adapts Weaviate's API to match the Chroma collection interface
    used throughout pipeline.py and retriever.py.
    Implement fully when migrating to Weaviate in Phase 2.
    """

    def __init__(self, client, class_name: str):
        self._client = client
        self._class  = class_name

    def upsert(self, ids, embeddings, documents, metadatas):
        raise NotImplementedError(
            "Weaviate upsert adapter not yet implemented. "
            "Complete this in Phase 2 when migrating from Chroma."
        )

    def query(self, query_embeddings, n_results, include, where=None):
        raise NotImplementedError("Weaviate query adapter not yet implemented.")

    def get(self, include, where=None):
        raise NotImplementedError("Weaviate get adapter not yet implemented.")


# ── Qdrant (Phase 2 stub) ─────────────────────────────────────────────────────

def _get_qdrant_collection():
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        raise ImportError(
            "qdrant-client is not installed. "
            "Run: pip install qdrant-client"
        )

    cfg             = cfg_get("vector_store").get("qdrant", {})
    url             = cfg.get("url", "http://localhost:6333")
    collection_name = cfg.get("collection", "sdk_scenarios")
    api_key         = cfg.get("api_key", "")

    client = QdrantClient(url=url, api_key=api_key or None)
    return _QdrantCollectionAdapter(client, collection_name)


class _QdrantCollectionAdapter:
    """
    Adapts Qdrant's API to match the Chroma collection interface.
    Implement fully when migrating to Qdrant in Phase 2.
    """

    def __init__(self, client, collection_name: str):
        self._client     = client
        self._collection = collection_name

    def upsert(self, ids, embeddings, documents, metadatas):
        raise NotImplementedError(
            "Qdrant upsert adapter not yet implemented. "
            "Complete this in Phase 2 when migrating from Chroma."
        )

    def query(self, query_embeddings, n_results, include, where=None):
        raise NotImplementedError("Qdrant query adapter not yet implemented.")

    def get(self, include, where=None):
        raise NotImplementedError("Qdrant get adapter not yet implemented.")