# embedding_service/main.py

import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, field_validator
from sentence_transformers import SentenceTransformer
from config.settings import embedding_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config — all values from sdk_discovery.yml, zero hardcoding ───────────────
_emb_cfg   = embedding_config()           # reads local: section from YAML
MODEL_NAME = _emb_cfg.get("model", "sentence-transformers/all-MiniLM-L6-v2")
MAX_BATCH  = int(_emb_cfg.get("max_batch_size", 64))

# ── Model registry ────────────────────────────────────────────────────────────
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    if _model is None:
        raise RuntimeError("Model not loaded — server is not ready yet.")
    return _model


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model
    logger.info(f"Loading embedding model: {MODEL_NAME}")
    t0     = time.time()
    _model = SentenceTransformer(MODEL_NAME)
    _model.encode(["warmup"], batch_size=1)
    actual_dim = _model.get_sentence_embedding_dimension()
    logger.info(
        f"Model ready in {time.time() - t0:.1f}s  |  "
        f"Model: {MODEL_NAME}  |  Dimension: {actual_dim}"
    )
    yield
    logger.info("Embedding service shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "SDK Discovery — Embedding Service",
    description = f"Self-hosted embedding service using {MODEL_NAME}",
    version     = "1.0.0",
    lifespan    = lifespan,
)


# ── Schemas ───────────────────────────────────────────────────────────────────
class EmbedRequest(BaseModel):
    texts: list[str]

    @field_validator("texts")
    @classmethod
    def texts_not_empty(cls, v):
        if not v:
            raise ValueError("texts list must not be empty")
        if len(v) > MAX_BATCH:
            raise ValueError(f"Batch size {len(v)} exceeds maximum of {MAX_BATCH}")
        if any(not t.strip() for t in v):
            raise ValueError("texts must not contain empty or whitespace-only strings")
        return v


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model:      str
    dimension:  int
    count:      int


class HealthResponse(BaseModel):
    status:    str
    model:     str
    dimension: int | None


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
def health():
    if _model is None:
        return HealthResponse(status="loading", model=MODEL_NAME, dimension=None)
    return HealthResponse(
        status    = "ok",
        model     = MODEL_NAME,
        dimension = _model.get_sentence_embedding_dimension(),
    )


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest):
    model = get_model()
    t0    = time.time()

    vectors = model.encode(
        request.texts,
        batch_size         = 32,
        show_progress_bar  = False,
        normalize_embeddings = True,
    )

    logger.info(f"Embedded {len(request.texts)} texts in {time.time() - t0:.3f}s")

    return EmbedResponse(
        embeddings = vectors.tolist(),
        model      = MODEL_NAME,
        dimension  = model.get_sentence_embedding_dimension(),
        count      = len(request.texts),
    )