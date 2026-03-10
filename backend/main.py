"""
FastAPI application entry point.
"""
from contextlib import asynccontextmanager
from pathlib import Path
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routes.api import router
from backend.ollama_client import ensure_ollama_running, recommend_model
from backend.ingestion.ingestion_queue import start_worker
import backend.config as cfg


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background ingestion worker
    start_worker()

    # Start Ollama if it is not already running
    try:
        ensure_ollama_running()
    except RuntimeError as e:
        print(f"[AISALES] WARNING: {e}")

    # Pick the best model for the available hardware
    if not os.environ.get("OLLAMA_LLM_MODEL"):
        model = recommend_model()
        os.environ["OLLAMA_LLM_MODEL"] = model
        cfg.OLLAMA_LLM_MODEL = model
        print(f"[AISALES] Using model: {model}")

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
