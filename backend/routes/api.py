"""
API routes — /api/status, /api/open-file-dialog, /api/upload-transcript,
              /api/extract-path, /api/generate, /api/download, /api/outputs
"""
from __future__ import annotations
import asyncio
import datetime
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import json

from backend.auth import require_auth
from backend.chains.extraction_chain import extract_from_file, ProjectData, project_data_to_dict
from backend.generator.offer_generator import generate_offer, regenerate_section
from backend.vectorstore.chroma_client import collection_count
from backend.ollama_client import recommend_model, list_local_models, is_ollama_running, is_anthropic_reachable, set_active_model
from backend.ingestion.ingestion_queue import submit_job, get_job, list_jobs, queue_size
import backend.config as _cfg
from backend.config import (
    TRANSCRIPTS_DIR,
    CHROMA_COLLECTION_COST, CHROMA_COLLECTION_CV, CHROMA_COLLECTION_BOILER, CHROMA_COLLECTION_CONTACTS,
    OUTPUTS_DIR, SETTINGS_FILE,
    COST_HISTORY_DIR,
)

logger = logging.getLogger(__name__)

# ── Concurrency limits ────────────────────────────────────────────────────────
# At most 1 full-offer generation and 2 transcript extractions at a time.
_gen_sem     = asyncio.Semaphore(1)
_extract_sem = asyncio.Semaphore(2)


def _safe_user_id(user_id: str) -> str:
    """Return a filesystem-safe, non-traversable string from a user_id (UUID)."""
    import re
    # Allow only alphanumeric chars and hyphens (UUID format); fall back to 'unknown'
    clean = re.sub(r'[^a-zA-Z0-9\-]', '', user_id)[:64]
    return clean or "unknown"


def _user_output_dir(claims: dict) -> Path:
    """Return (and create) OUTPUTS_DIR/{user_id} for the authenticated user."""
    uid = _safe_user_id(claims.get("sub", "anonymous"))
    d = OUTPUTS_DIR / uid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _user_transcript_dir(claims: dict) -> Path:
    """Return (and create) TRANSCRIPTS_DIR/{user_id} for the authenticated user."""
    settings_custom = _load_settings().get("transcript_folder", "")
    if settings_custom:
        p = Path(settings_custom)
        if p.is_dir():
            return p
    uid = _safe_user_id(claims.get("sub", "anonymous"))
    d = TRANSCRIPTS_DIR / uid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_offer_meta(
    project: ProjectData,
    done_event: dict,
    stats_log: dict[str, dict],
    language: str,
) -> None:
    """Write a sidecar .meta.json file alongside the generated DOCX."""
    try:
        docx_path = Path(done_event["docx"])
        meta = {
            "customer_name":    project.customer_name or "",
            "company_name":     project.company_name or "",
            "project_name":     project.project_name or "",
            "project_number":   project.project_number or "",
            "document_language": language,
            "generated_at":     datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "elapsed_total_s":  done_event.get("elapsed_total_s"),
            "section_stats":    stats_log,
            "files": {
                "docx":  done_event.get("docx"),
                "pdf":   done_event.get("pdf"),
                "xlsx":  done_event.get("xlsx"),
            },
        }
        docx_path.with_suffix(".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as _e:
        logger.warning("Failed to write offer meta: %s", _e)


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_transcript_dir() -> Path:
    """Return the active transcript folder (custom or default). Used as a fallback."""
    custom = _load_settings().get("transcript_folder", "")
    if custom:
        p = Path(custom)
        if p.is_dir():
            return p
    return TRANSCRIPTS_DIR

# require_auth runs on every route; raises HTTP 401 when token is invalid.
# When AUTH_ENABLED is False (Azure AD not configured) it is a no-op.
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])



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
        "active_model": _cfg._active_anthropic_model,
        "available_models": _cfg.AVAILABLE_ANTHROPIC_MODELS,
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


class SetModelRequest(BaseModel):
    model_id: str


@router.post("/set-model")
def set_model(req: SetModelRequest):
    """Switch the active Anthropic LLM model at runtime."""
    valid_ids = {m["id"] for m in _cfg.AVAILABLE_ANTHROPIC_MODELS}
    if req.model_id not in valid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{req.model_id}'. Valid: {sorted(valid_ids)}",
        )
    set_active_model(req.model_id)
    return {"active_model": req.model_id}


# ── Transcript Extraction ─────────────────────────────────────────────────────
@router.post("/upload-transcript")
async def upload_transcript(
    file: UploadFile = FastAPIFile(...),
    claims: dict = Depends(require_auth),
):
    """Save an uploaded transcript file to the user's TRANSCRIPTS_DIR and return its path."""
    dest = _user_transcript_dir(claims) / (file.filename or "transcript.txt")
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
    if _extract_sem.locked():
        raise HTTPException(status_code=429, detail="Too many extraction requests are running. Please wait a moment.")
    await _extract_sem.acquire()
    try:
        return project_data_to_dict(await asyncio.to_thread(extract_from_file, src))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _extract_sem.release()


# ── Offer Generation ──────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    project: dict
    enable_web_search: bool = True
    export_pdf: bool = True
    generate_cost_table: bool = True
    document_language: str = "en"  # "en" | "fi"


@router.post("/generate")
async def generate(req: GenerateRequest, claims: dict = Depends(require_auth)):
    """Generate the full offer document. Returns a streaming NDJSON response with progress events."""
    if _gen_sem.locked():
        raise HTTPException(
            status_code=429,
            detail="A generation is already in progress. Please wait for it to finish.",
        )
    # Acquire before returning the StreamingResponse so the slot is held from this point.
    # acquire() returns immediately (no suspension) because we just confirmed the semaphore is free.
    await _gen_sem.acquire()

    project = ProjectData(**{k: v for k, v in req.project.items() if k in ProjectData.__dataclass_fields__})
    user_out_dir = _user_output_dir(claims)

    async def event_stream():
        _stats_log: dict[str, dict] = {}
        try:
            async for event in generate_offer(project, req.enable_web_search, req.export_pdf, req.generate_cost_table, req.document_language, output_dir=user_out_dir):
                if event.get("status") == "stats":
                    _stats_log[event["section"]] = {
                        "elapsed_s": event.get("elapsed_s", 0),
                        "tokens":    event.get("tokens", 0),
                    }
                elif event.get("status") == "done" and event.get("docx"):
                    _write_offer_meta(project, event, _stats_log, req.document_language)
                # Pad to >1KB so TCP/proxy buffers flush immediately on every event
                line = json.dumps(event) + "\n"
                yield line + (" " * max(0, 1024 - len(line))) + "\n"
        finally:
            _gen_sem.release()

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
    user_prompt: str | None = None  # optional improvement/fix instructions from the user


@router.post("/regenerate-section")
async def regenerate_section_endpoint(req: RegenerateSectionRequest, claims: dict = Depends(require_auth)):
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
                req.enable_web_search, req.document_language, req.user_prompt,
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
def download_file(path: str, claims: dict = Depends(require_auth)):
    """Download a generated offer file. Only files inside the user's output directory are allowed."""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    user_out_dir = _user_output_dir(claims)
    try:
        file_path.resolve().relative_to(user_out_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    return FileResponse(str(file_path), filename=file_path.name)


@router.get("/outputs")
def list_outputs(claims: dict = Depends(require_auth)):
    """List generated offer files belonging to the authenticated user."""
    _VISIBLE = {'.docx', '.pdf', '.xlsx'}
    files = []
    user_out_dir = _user_output_dir(claims)
    for f in user_out_dir.iterdir():
        if not f.is_file() or f.suffix not in _VISIBLE:
            continue
        entry: dict = {"name": f.name, "path": str(f), "size": f.stat().st_size}
        if f.suffix == '.docx':
            meta_path = f.with_suffix(".meta.json")
            if meta_path.exists():
                try:
                    entry["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
        files.append(entry)
    return sorted(files, key=lambda x: x["name"], reverse=True)


class DeleteRequest(BaseModel):
    path: str


@router.post("/delete-output")
def delete_output(req: DeleteRequest, claims: dict = Depends(require_auth)):
    """Delete a generated offer file. Only files inside the user's output directory are allowed."""
    file_path = Path(req.path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    user_out_dir = _user_output_dir(claims)
    try:
        file_path.resolve().relative_to(user_out_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    file_path.unlink()
    # Remove sidecar files that are only meaningful alongside the DOCX
    if file_path.suffix == '.docx':
        for _sidecar in ('.meta.json', '.sections.json'):
            _sc = file_path.with_suffix(_sidecar)
            if _sc.exists():
                try:
                    _sc.unlink()
                except Exception:
                    pass
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
