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


app = FastAPI(title="AISALES", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Serve the compiled React frontend — run `npm run build` in /frontend first
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
