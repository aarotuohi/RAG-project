"""
API routes — /api/status, /api/open-file-dialog, /api/upload-transcript,
              /api/extract-path, /api/generate, /api/download, /api/outputs
"""
from __future__ import annotations
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File as FastAPIFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import json

from backend.chains.extraction_chain import extract_from_file, ProjectData, project_data_to_dict
from backend.generator.offer_generator import generate_offer, regenerate_section
from backend.vectorstore.chroma_client import collection_count
from backend.ollama_client import recommend_model, list_local_models, is_ollama_running, is_anthropic_reachable
from backend.ingestion.ingestion_queue import submit_job, get_job, list_jobs, queue_size
import backend.config as _cfg
from backend.config import (
    TRANSCRIPTS_DIR,
    CHROMA_COLLECTION_COST, CHROMA_COLLECTION_CV, CHROMA_COLLECTION_BOILER, CHROMA_COLLECTION_CONTACTS,
    OUTPUTS_DIR, SETTINGS_FILE,
    COST_HISTORY_DIR,
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
    _anthropic_ok, _anthropic_detail = is_anthropic_reachable()
    return {
        "llm_provider": "anthropic",
        "active_model": _cfg.ANTHROPIC_MODEL,
        "anthropic_reachable": _anthropic_ok,
        "anthropic_detail": _anthropic_detail,
        "embed_model": _cfg.OLLAMA_EMBED_MODEL,
        "ollama_running": is_ollama_running(),
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
async def extract_transcript(req: ExtractPathRequest):
    """Extract structured project data from a local transcript file."""
    src = Path(req.file_path)
    if not src.exists() or not src.is_file():
        raise HTTPException(status_code=400, detail=f"File not found: {req.file_path}")
    try:
        return project_data_to_dict(await asyncio.to_thread(extract_from_file, src))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Offer Generation ──────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    project: dict
    enable_web_search: bool = True
    export_pdf: bool = True
    generate_cost_table: bool = True
    document_language: str = "en"  # "en" | "fi"


@router.post("/generate")
async def generate(req: GenerateRequest):
    """Generate the full offer document. Returns a streaming NDJSON response with progress events."""
    project = ProjectData(**{k: v for k, v in req.project.items() if k in ProjectData.__dataclass_fields__})

    async def event_stream():
        async for event in generate_offer(project, req.enable_web_search, req.export_pdf, req.generate_cost_table, req.document_language):
            # Pad to >1KB so TCP/proxy buffers flush immediately on every event
            line = json.dumps(event) + "\n"
            yield line + (" " * max(0, 1024 - len(line))) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# ── Section Regeneration ─────────────────────────────────────────────────────

_REGENERATABLE_SECTIONS = {
    "thank_you", "section1", "section2", "section3",
    "section4", "section5", "section8",
}


class RegenerateSectionRequest(BaseModel):
    section_key: str
    project: dict
    enable_web_search: bool = True
    document_language: str = "en"
    docx_path: str | None = None   # current offer DOCX path; if set, DOCX is rebuilt
    export_pdf: bool = True        # rebuild PDF when docx_path is provided


@router.post("/regenerate-section")
async def regenerate_section_endpoint(req: RegenerateSectionRequest):
    """Re-run a single section and stream the result as NDJSON."""
    if req.section_key not in _REGENERATABLE_SECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Section '{req.section_key}' cannot be regenerated. Valid: {sorted(_REGENERATABLE_SECTIONS)}",
        )

    project = ProjectData(**{k: v for k, v in req.project.items() if k in ProjectData.__dataclass_fields__})

    async def event_stream():
        import time
        import dataclasses as _dc
        from backend.generator.excel_builder import build_cost_excel
        from backend.generator.offer_generator import rebuild_offer_from_section

        progress_line = json.dumps({"status": "progress", "section": req.section_key, "message": f"Regenerating {req.section_key}\u2026"}) + "\n"
        yield progress_line + (" " * max(0, 1024 - len(progress_line))) + "\n"
        t0 = time.time()
        try:
            raw_result = await asyncio.to_thread(
                regenerate_section, project, req.section_key,
                req.enable_web_search, req.document_language,
            )
            elapsed = round(time.time() - t0, 1)

            # ── Serialise section2 steps for JSON transport ──────────────────
            transport_result = raw_result
            xlsx_path: str | None = None
            if req.section_key == "section2":
                sec2 = raw_result.get("section2", {})
                steps = sec2.get("steps", [])
                # Build standalone Excel even when not rebuilding full DOCX
                if not req.docx_path:
                    try:
                        xlsx_file = await asyncio.to_thread(
                            build_cost_excel, project, sec2, req.document_language
                        )
                        xlsx_path = str(xlsx_file)
                    except Exception as _xe:
                        pass
                transport_result = {
                    "section2": {
                        "description_text": sec2.get("description_text", ""),
                        "grand_total": sec2.get("grand_total", 0),
                        "payment_type": sec2.get("payment_type", ""),
                        "steps": [
                            _dc.asdict(s) if hasattr(s, "__dataclass_fields__") else s
                            for s in steps
                        ],
                        "xlsx": xlsx_path,
                    }
                }

            # ── Rebuild full DOCX (and optionally PDF/Excel) ─────────────────
            rebuilt: dict = {}
            if req.docx_path:
                try:
                    rebuilt = await asyncio.to_thread(
                        rebuild_offer_from_section,
                        Path(req.docx_path), project, req.section_key,
                        raw_result, req.document_language, req.export_pdf,
                    )
                except Exception as _re:
                    pass  # non-fatal; frontend still shows regenerated content

            done_payload: dict = {
                "status": "done",
                "section": req.section_key,
                "result": transport_result,
                "elapsed_s": elapsed,
                **rebuilt,  # docx, pdf, xlsx if rebuild succeeded
            }
            done_line = json.dumps(done_payload) + "\n"
            yield done_line + (" " * max(0, 1024 - len(done_line))) + "\n"
        except Exception as e:
            error_line = json.dumps({"status": "error", "section": req.section_key, "message": str(e)}) + "\n"
            yield error_line + (" " * max(0, 1024 - len(error_line))) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


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


class DeleteRequest(BaseModel):
    path: str


@router.post("/delete-output")
def delete_output(req: DeleteRequest):
    """Delete a generated offer file. Only files inside OUTPUTS_DIR are allowed."""
    file_path = Path(req.path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        file_path.resolve().relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    file_path.unlink()
    return {"deleted": True, "name": file_path.name}


# ── Section Test Endpoints ───────────────────────────────────────────────────

class TestGenerateRequest(BaseModel):
    section: str   # "section1" | "section2"
    project: dict
    enable_web_search: bool = True
    document_language: str = "en"


@router.post("/test-generate")
def test_generate(req: TestGenerateRequest):
    """Run only section1 or section2 and return raw result for testing."""
    from backend.chains.section1_chain import generate_section1
    from backend.chains.section2_chain import generate_section2
    from backend.chains.extraction_chain import ProjectData

    project = ProjectData(**{k: v for k, v in req.project.items() if k in ProjectData.__dataclass_fields__})

    if req.section == "section1":
        try:
            result = generate_section1(project, enable_web_search=req.enable_web_search, language=req.document_language)
            return {"section": "section1", "result": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    elif req.section == "section2":
        try:
            from dataclasses import asdict
            from backend.generator.excel_builder import build_cost_excel
            raw = generate_section2(project, language=req.document_language)
            steps = raw.get("steps", [])
            xlsx_path: str | None = None
            try:
                xlsx_file = build_cost_excel(project, raw, language=req.document_language)
                xlsx_path = str(xlsx_file)
            except Exception:
                pass  
            return {
                "section": "section2",
                "result": {
                    "description_text": raw.get("description_text", ""),
                    "grand_total": raw.get("grand_total", 0),
                    "payment_type": raw.get("payment_type", ""),
                    "steps": [asdict(s) if hasattr(s, "__dataclass_fields__") else s for s in steps],
                    "xlsx": xlsx_path,
                },
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=400, detail="section must be 'section1' or 'section2'")


# From her on it is the bottleneck solution


# ── Background Ingestion ──────────────────────────────────────────────────────

_INGEST_COLLECTION_MAP = {
    "cost_history": CHROMA_COLLECTION_COST,
    "cv":           CHROMA_COLLECTION_CV,
    "boilerplate":  CHROMA_COLLECTION_BOILER,
    "contacts":     CHROMA_COLLECTION_CONTACTS,
}

_INGEST_DIR_MAP = {
    "cost_history": None,   # resolved dynamically from config
    "cv":           None,
    "boilerplate":  None,
    "contacts":     None,
}


@router.post("/ingest")
async def ingest_file(
    collection: str,
    file: UploadFile = FastAPIFile(...),
    folder: str = "",
):
    """
    Accept a file upload, save it to disk, and queue it for background ingestion.
    Returns a job_id immediately — the actual indexing happens in the background.

    collection must be one of: cost_history | cv | boilerplate | contacts
    folder (optional): for cost_history only — the sub-folder (category) to save the file into.
    """
    if collection not in _INGEST_COLLECTION_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collection '{collection}'. Valid values: {list(_INGEST_COLLECTION_MAP)}",
        )

    from backend.config import COST_HISTORY_DIR, CV_DIR, BOILERPLATE_DIR, CONTACTS_DIR
    dest_dir = {
        "cost_history": COST_HISTORY_DIR,
        "cv":           CV_DIR,
        "boilerplate":  BOILERPLATE_DIR,
        "contacts":     CONTACTS_DIR,
    }[collection]

    # For cost_history, optionally place the file inside a category sub-folder
    if collection == "cost_history" and folder:
        safe_folder = folder.strip().replace(" ", "_").lower()
        if safe_folder and "/" not in safe_folder and "\\" not in safe_folder and not safe_folder.startswith("."):
            sub = dest_dir / safe_folder
            sub.mkdir(parents=True, exist_ok=True)
            dest_dir = sub

    dest = dest_dir / (file.filename or "upload")
    stem, suffix, counter = dest.stem, dest.suffix, 1
    while dest.exists():
        dest = dest.parent / f"{stem}_{counter}{suffix}"
        counter += 1

    content = await file.read()
    dest.write_bytes(content)

    job_id = submit_job(file_path=dest, collection_name=_INGEST_COLLECTION_MAP[collection])
    return {"job_id": job_id, "file": dest.name, "collection": collection, "status": "pending"}


@router.get("/ingest/status/{job_id}")
def ingest_status(job_id: str):
    """Return the status of a single ingestion job."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id":       job.job_id,
        "file":         job.file_path.name,
        "collection":   job.collection_name,
        "status":       job.status,
        "chunks_added": job.chunks_added,
        "error":        job.error,
        "queued_at":    job.queued_at,
        "finished_at":  job.finished_at,
    }


@router.get("/ingest/queue")
def ingest_queue():
    """Return all ingestion jobs and the current queue depth."""
    jobs = list_jobs()
    return {
        "queue_depth": queue_size(),
        "jobs": [
            {
                "job_id":       j.job_id,
                "file":         j.file_path.name,
                "collection":   j.collection_name,
                "status":       j.status,
                "chunks_added": j.chunks_added,
                "error":        j.error,
                "queued_at":    j.queued_at,
                "finished_at":  j.finished_at,
            }
            for j in jobs
        ],
    }
