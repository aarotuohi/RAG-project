"""
API routes — /api/status, /api/ingest, /api/extract-path, /api/generate, /api/download
"""
from __future__ import annotations
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import json

from backend.chains.extraction_chain import extract_from_file, ProjectData, project_data_to_dict
from backend.generator.offer_generator import generate_offer
from backend.vectorstore.chroma_client import delete_collection, collection_count, get_chroma_client
from backend.ingestion.document_loader import index_directory, index_file
from backend.ingestion.cv_parser import parse_cv_file
from backend.ingestion.excel_parser import parse_excel, steps_to_text
from backend.ollama_client import recommend_model, list_local_models, pull_model_if_missing, is_ollama_running, get_embeddings
from backend.config import (
    COST_HISTORY_DIR, CV_DIR, CONTACTS_DIR, BOILERPLATE_DIR,
    CHROMA_COLLECTION_COST, CHROMA_COLLECTION_CV, CHROMA_COLLECTION_BOILER, CHROMA_COLLECTION_CONTACTS,
    OUTPUTS_DIR,
)

router = APIRouter(prefix="/api")

# Maps category name → folder path (used in multiple endpoints)
FOLDER_MAP = {
    "cost_history": COST_HISTORY_DIR,
    "cvs":          CV_DIR,
    "contacts":     CONTACTS_DIR,
    "boilerplate":  BOILERPLATE_DIR,
}


# ── Status & Setup ────────────────────────────────────────────────────────────

@router.get("/status")
def get_status():
    return {
        "ollama_running": is_ollama_running(),
        "recommended_model": recommend_model(),
        "local_models": list_local_models(),
        "collection_counts": {
            "cost_history": collection_count(CHROMA_COLLECTION_COST),
            "cv_database":  collection_count(CHROMA_COLLECTION_CV),
            "boilerplate":  collection_count(CHROMA_COLLECTION_BOILER),
            "contacts":     collection_count(CHROMA_COLLECTION_CONTACTS),
        },
    }


class PullModelRequest(BaseModel):
    model_name: str


@router.post("/setup/pull-model")
def pull_model(req: PullModelRequest):
    try:
        pull_model_if_missing(req.model_name)
        return {"ok": True, "model": req.model_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Ingestion ─────────────────────────────────────────────────────────────────

@router.post("/ingest/cost-history")
def ingest_cost_history():
    """Index all Excel files from the cost_history folder into ChromaDB."""
    delete_collection(CHROMA_COLLECTION_COST)
    results = {}
    for f in COST_HISTORY_DIR.iterdir():
        if f.suffix.lower() in (".xlsx", ".xls"):
            try:
                col = get_chroma_client().get_or_create_collection(CHROMA_COLLECTION_COST)
                for sheet_name, steps in parse_excel(f).items():
                    text = steps_to_text(steps, project_name=f"{f.stem} / {sheet_name}")
                    col.add(
                        documents=[text],
                        embeddings=[get_embeddings().embed_query(text)],
                        metadatas=[{"source": f.name, "sheet": sheet_name}],
                        ids=[f"{f.stem}_{sheet_name}"],
                    )
                    results[f.name] = results.get(f.name, 0) + 1
            except Exception as e:
                results[f.name] = f"error: {e}"
        else:
            results[f.name] = index_file(f, CHROMA_COLLECTION_COST)
    return {"indexed": results}


@router.post("/ingest/cvs")
def ingest_cvs():
    """Index the CV file from the cvs folder into ChromaDB."""
    delete_collection(CHROMA_COLLECTION_CV)
    results = {}
    for f in CV_DIR.iterdir():
        if f.suffix.lower() in (".docx", ".pdf"):
            try:
                col = get_chroma_client().get_or_create_collection(CHROMA_COLLECTION_CV)
                emb_fn = get_embeddings()
                experts = parse_cv_file(f)
                for expert in experts:
                    col.add(
                        documents=[expert.raw_text],
                        embeddings=[emb_fn.embed_query(expert.raw_text[:1000])],
                        metadatas={"person_name": expert.person_name, "skills": ", ".join(expert.skills), "domains": ", ".join(expert.domains), "source": f.name},
                        ids=[f"{f.stem}_{expert.person_name.replace(' ', '_')}"],
                    )
                results[f.name] = len(experts)
            except Exception as e:
                results[f.name] = f"error: {e}"
    return {"indexed": results}


@router.post("/ingest/boilerplate")
def ingest_boilerplate():
    """Index all boilerplate text files into ChromaDB."""
    delete_collection(CHROMA_COLLECTION_BOILER)
    return {"indexed": index_directory(BOILERPLATE_DIR, CHROMA_COLLECTION_BOILER)}


class RegisterPathRequest(BaseModel):
    category: str
    file_path: str


@router.post("/ingest/register-path")
def register_path(req: RegisterPathRequest):
    """Copy a local file (by absolute path) into a category folder and re-index it."""
    src = Path(req.file_path)
    if not src.exists() or not src.is_file():
        raise HTTPException(status_code=400, detail=f"File not found: {req.file_path}")

    folder = FOLDER_MAP.get(req.category)
    if not folder:
        raise HTTPException(status_code=400, detail=f"Unknown category: {req.category}")

    dest = folder / src.name
    shutil.copy2(src, dest)

    if req.category == "cvs":
        return ingest_cvs()
    elif req.category == "cost_history":
        return ingest_cost_history()
    elif req.category == "boilerplate":
        return {"indexed": {src.name: index_file(dest, CHROMA_COLLECTION_BOILER)}}
    return {"saved": str(dest)}


# ── Transcript Extraction ─────────────────────────────────────────────────────

class ExtractPathRequest(BaseModel):
    file_path: str


@router.post("/extract-path")
def extract_transcript(req: ExtractPathRequest):
    """Extract structured project data from a local transcript file."""
    src = Path(req.file_path)
    if not src.exists() or not src.is_file():
        raise HTTPException(status_code=400, detail=f"File not found: {req.file_path}")
    try:
        return project_data_to_dict(extract_from_file(src))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Offer Generation ──────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    project: dict
    enable_web_search: bool = True
    export_pdf: bool = True


@router.post("/generate")
def generate(req: GenerateRequest):
    """Generate the full offer document. Returns a streaming NDJSON response with progress events."""
    project = ProjectData(**{k: v for k, v in req.project.items() if k in ProjectData.__dataclass_fields__})

    def event_stream():
        for event in generate_offer(project, req.enable_web_search, req.export_pdf):
            yield json.dumps(event) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


# ── File Download & Listing ───────────────────────────────────────────────────

@router.get("/download")
def download_file(path: str):
    """Download a generated offer file. Only files inside OUTPUTS_DIR are allowed."""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        file_path.resolve().relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    return FileResponse(str(file_path), filename=file_path.name)


@router.get("/outputs")
def list_outputs():
    """List all generated offer files."""
    files = [{"name": f.name, "path": str(f), "size": f.stat().st_size} for f in OUTPUTS_DIR.iterdir() if f.is_file()]
    return sorted(files, key=lambda x: x["name"], reverse=True)


@router.get("/documents")
def list_documents():
    """List files currently registered in each document category folder."""
    def _ls(folder: Path) -> list[str]:
        try:
            return [f.name for f in folder.iterdir() if f.is_file()]
        except Exception:
            return []
    return {
        "cost_history": _ls(COST_HISTORY_DIR),
        "cvs":          _ls(CV_DIR),
        "contacts":     _ls(CONTACTS_DIR),
        "boilerplate":  _ls(BOILERPLATE_DIR),
    }
