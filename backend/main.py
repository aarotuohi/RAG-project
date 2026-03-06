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
from backend.ingestion.ingestion_queue import start_worker
import backend.config as cfg


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background ingestion worker
    start_worker()

    # Validate that an OpenAI API key has been provided
    import os as _os
    if not _os.environ.get("OPENAI_API_KEY"):
        print(
            "[AISALES] WARNING: OPENAI_API_KEY is not set. "
            "Set it in a .env file or as an environment variable before using LLM features."
        )
    else:
        print(f"[AISALES] OpenAI model: {cfg.OPENAI_LLM_MODEL}")

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
