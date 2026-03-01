"""
API routes — /api/status, /api/open-file-dialog, /api/upload-transcript,
              /api/extract-path, /api/generate, /api/download, /api/outputs
"""
from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File as FastAPIFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import json

from backend.chains.extraction_chain import extract_from_file, ProjectData, project_data_to_dict
from backend.generator.offer_generator import generate_offer
from backend.vectorstore.chroma_client import collection_count
from backend.ollama_client import recommend_model, list_local_models, is_ollama_running
from backend.config import (
    TRANSCRIPTS_DIR,
    CHROMA_COLLECTION_COST, CHROMA_COLLECTION_CV, CHROMA_COLLECTION_BOILER, CHROMA_COLLECTION_CONTACTS,
    OUTPUTS_DIR, SETTINGS_FILE,
)


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_transcript_dir() -> Path:
    """Return the active transcript folder (custom or default)."""
    custom = _load_settings().get("transcript_folder", "")
    if custom:
        p = Path(custom)
        if p.is_dir():
            return p
    return TRANSCRIPTS_DIR

router = APIRouter(prefix="/api")



# ── Native file dialog ───────────────────────────────────────────────────────

@router.get("/open-file-dialog")
def open_file_dialog():
    """Open a native OS file picker and return the chosen path."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Select meeting transcript",
            filetypes=[
                ("Transcript files", "*.txt *.docx *.pdf *.md"),
                ("All files", "*.*"),
            ],
        )
        root.destroy()
        if path:
            return {"path": path}
        return {"path": ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


# ── Transcript Extraction ─────────────────────────────────────────────────────
@router.post("/upload-transcript")
async def upload_transcript(file: UploadFile = FastAPIFile(...)):
    """Save an uploaded transcript file to TRANSCRIPTS_DIR and return its path."""
    dest = _get_transcript_dir() / (file.filename or "transcript.txt")
    # If a file with the same name already exists, don't overwrite
    stem = dest.stem
    suffix = dest.suffix
    counter = 1
    while dest.exists():
        dest = dest.parent / f"{stem}_{counter}{suffix}"
        counter += 1
    content = await file.read()
    dest.write_bytes(content)
    return {"path": str(dest), "name": dest.name}

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
    document_language: str = "en"  # "en" | "fi"


@router.post("/generate")
def generate(req: GenerateRequest):
    """Generate the full offer document. Returns a streaming NDJSON response with progress events."""
    project = ProjectData(**{k: v for k, v in req.project.items() if k in ProjectData.__dataclass_fields__})

    def event_stream():
        for event in generate_offer(project, req.enable_web_search, req.export_pdf, req.document_language):
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
