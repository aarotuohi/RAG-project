"""
FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routes.api import router
from backend.ollama_client import ensure_ollama_running
from backend.ingestion.ingestion_queue import start_worker
import backend.config as cfg

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background ingestion worker
    start_worker()

    # Start Ollama — still used for embeddings (nomic-embed-text)
    try:
        ensure_ollama_running()
    except RuntimeError as e:
        logger.warning("%s", e)

    logger.info("LLM: Anthropic %s", cfg.ANTHROPIC_MODEL)
    logger.info("Embeddings: Ollama %s", cfg.OLLAMA_EMBED_MODEL)

    yield  # app is running


# Allowed CORS origins.  Override via CORS_ORIGINS env var (comma-separated).
# Defaults to localhost on the ports used by Vite dev server and the FastAPI server.
_DEFAULT_ORIGINS = [
    "http://localhost:5173",   # Vite dev server (npm run dev)
    "http://localhost:8000",   # FastAPI itself (when accessed via browser)
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
]
_cors_origins_env = os.environ.get("CORS_ORIGINS", "")
ALLOWED_ORIGINS: list[str] = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else _DEFAULT_ORIGINS
)

app = FastAPI(title="AISALES", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(router)

# Serve the compiled React frontend — run `npm run build` in /frontend first
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
