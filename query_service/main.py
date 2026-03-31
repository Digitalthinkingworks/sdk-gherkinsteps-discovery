# query_service/main.py

import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from query_service.graph.graph import build_graph, run_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Metrics (in-memory, resets on restart — sufficient for Phase 1) ───────────
_metrics = {
    "total_queries":        0,
    "result_responses":     0,
    "clarification_responses": 0,
    "total_latency_ms":     0.0,
    "errors":               0,
}

# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Pre-compile the LangGraph at startup so the first request
    doesn't pay the compilation cost.
    """
    logger.info("Compiling LangGraph query graph...")
    app.state.graph = build_graph()
    logger.info("Query service ready.")

    # ── Warm up Ollama so first scaffold call is fast ──────────────────
    from config.settings import llm_scaffold_enabled, llm_provider, llm_config
    if llm_scaffold_enabled() and llm_provider() == "ollama":
        import requests as req
        cfg = llm_config()
        try:
            logger.info(f"Warming up Ollama model: {cfg.get('model')} ...")
            resp = req.post(
                f"{cfg.get('base_url','http://localhost:11434')}/api/generate",
                json={
                    "model":  cfg.get("model", "mistral"),
                    "prompt": "hi",
                    "stream": False,
                },
                timeout=cfg.get("timeout_seconds", 120),
            )
            if resp.ok:
                logger.info("Ollama warm-up complete — model loaded into memory.")
            else:
                logger.warning(f"Ollama warm-up returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"Ollama warm-up failed ({e}) — first scaffold call may be slow.")


    yield
    logger.info("Query service shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SDK Discovery — Query Service",
    description=(
        "Natural language search over BDD steps document file."
        "Ask in plain English, get the right SDK step document back to implement the scenario."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in Phase 2 when deploying internally
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response schemas ────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query:      str
    sdk_filter: str | None = None

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("query must not be empty")
        if len(v.strip()) < 3:
            raise ValueError("query too short — please be more specific")
        return v.strip()


class ResultCard(BaseModel):
    sdk_name:               str
    sdk_version:            str
    class_name:             str
    step_definition_file:   str
    method_name:            str
    keyword:                str
    step_text:              str
    section:                str
    github_url:             str
    confidence:             float
    usage_hint:             str
    maven_coords:           str


class ClarificationOption(BaseModel):
    rank:                   int
    sdk_name:               str
    class_name:             str
    step_definition_file:   str
    method_name:            str
    keyword:                str
    step_text:              str
    github_url:             str
    confidence:             float


class QueryResponse(BaseModel):
    type:                  str          # "result" | "clarification"
    data:                  ResultCard | list[ClarificationOption]
    message:               str | None = None
    latency_ms:            float


class HealthResponse(BaseModel):
    status:        str
    version:       str
    total_queries: int
    avg_latency_ms: float


class MetricsResponse(BaseModel):
    total_queries:              int
    result_responses:           int
    clarification_responses:    int
    avg_latency_ms:             float
    errors:                     int

# Add to query_service/main.py

class ScaffoldRequest(BaseModel):
    sdk_name:             str
    class_name:           str
    method_name:          str
    keyword:              str
    step_text:            str
    step_definition_file: str
    sdk_version:          str
    section:              str = ""
    usage_hint:           str = ""

class ScaffoldResponse(BaseModel):
    gherkin: str          # complete .feature file snippet, plain text
    latency_ms: float


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health():
    avg = (
        _metrics["total_latency_ms"] / _metrics["total_queries"]
        if _metrics["total_queries"] > 0 else 0.0
    )
    return HealthResponse(
        status         = "ok",
        version        = "1.0.0",
        total_queries  = _metrics["total_queries"],
        avg_latency_ms = round(avg, 1),
    )


@app.get("/metrics", response_model=MetricsResponse)
def metrics():
    avg = (
        _metrics["total_latency_ms"] / _metrics["total_queries"]
        if _metrics["total_queries"] > 0 else 0.0
    )
    return MetricsResponse(
        total_queries           = _metrics["total_queries"],
        result_responses        = _metrics["result_responses"],
        clarification_responses = _metrics["clarification_responses"],
        avg_latency_ms          = round(avg, 1),
        errors                  = _metrics["errors"],
    )


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    """
    Main endpoint. Accepts a natural language query, returns either:
      - type="result"        → a single best-match step document card
      - type="clarification" → top-3 options when confidence is low

    Example request:
        {"query": "add a new item to inventory"}

    Example response (result):
        {
          "type": "result",
          "data": {
            "sdk_name": "supply-chain-sdk",
            "class_name": "InventorySteps",
            "step_text": "the user adds an item...",
            "keyword": "When",
            "maven_coords": "<dependency>...",
            "usage_hint": "...",
            ...
          },
          "latency_ms": 312.4
        }
    """
    _metrics["total_queries"] += 1
    t0 = time.time()

    try:
        response = run_query(
            query      = request.query,
            sdk_filter = request.sdk_filter,
        )
    except Exception as e:
        _metrics["errors"] += 1
        logger.error(f"Graph execution error for query='{request.query}': {e}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {e}")

    latency_ms = round((time.time() - t0) * 1000, 1)
    _metrics["total_latency_ms"] += latency_ms

    if response["type"] == "result":
        _metrics["result_responses"] += 1
        return QueryResponse(
            type       = "result",
            data       = ResultCard(**response["data"]),
            latency_ms = latency_ms,
        )

    _metrics["clarification_responses"] += 1
    return QueryResponse(
        type    = "clarification",
        data    = [ClarificationOption(**opt) for opt in response["data"]],
        message = response.get("message"),
        latency_ms = latency_ms,
    )

@app.post("/scaffold", response_model=ScaffoldResponse)
def scaffold(request: ScaffoldRequest):
    """
    Generate a ready-to-use Gherkin scenario scaffold using the LLM.
    Called by the UI after a result card is shown.
    Falls back to a template if LLM is disabled or unavailable.
    """
    t0 = time.time()

    from config.model_factory import generate_gherkin_scaffold
    gherkin = generate_gherkin_scaffold(request.model_dump())

    return ScaffoldResponse(
        gherkin    = gherkin,
        latency_ms = round((time.time() - t0) * 1000, 1),
    )