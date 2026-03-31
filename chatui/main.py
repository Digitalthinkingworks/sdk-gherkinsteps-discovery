# query_service/main.py

import logging
from contextlib import asynccontextmanager

from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Chat UI is ready.")
    yield
    logger.info("Chat UI is shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SDK Discovery — Chat UI",
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

# Mount the view/ folder as static files so index.html can load styles.css and app.js
app.mount(
    "/view/static", 
    StaticFiles(directory=Path(__file__).parent / "view" / "static"),
    name="ui-static",
)

@app.get("/ui", response_class=HTMLResponse)
def ui():
    """Serve the App UI."""
    ui_path = Path(__file__).parent / "view" / "index.html"
    return HTMLResponse(content=ui_path.read_text(encoding="utf-8"))

