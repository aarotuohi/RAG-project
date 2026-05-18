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

    # Start Ollama if it is not already running
    try:
        ensure_ollama_running()
    except RuntimeError as e:
        logger.warning("%s", e)

    # Use the standard model from config unless explicitly overridden via env var
    if os.environ.get("OLLAMA_LLM_MODEL"):
        cfg.OLLAMA_LLM_MODEL = os.environ["OLLAMA_LLM_MODEL"]
    else:
        os.environ["OLLAMA_LLM_MODEL"] = cfg.OLLAMA_LLM_MODEL
    logger.info("Using model: %s", cfg.OLLAMA_LLM_MODEL)
    # -- Claude alternative: replace the four lines above with:
    # print(f"[AISALES] LLM: Anthropic {cfg.ANTHROPIC_MODEL}")
    # print(f"[AISALES] Embeddings: Ollama {cfg.OLLAMA_EMBED_MODEL}")

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
