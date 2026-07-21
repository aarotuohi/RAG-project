"""
Offer generator — orchestrates all section chains to produce the complete offer.
Runs sections sequentially and yields progress events.
"""
from __future__ import annotations
import asyncio
import dataclasses
import json
import logging
import time
from pathlib import Path
from typing import AsyncIterator

from backend.chains.extraction_chain import ProjectData
from backend.chains.section1_chain import generate_section1
from backend.chains.section2_chain import generate_section2
from backend.chains.section8_chain import generate_section8
from backend.chains.boilerplate import (
    generate_thankyou, generate_timetable, generate_restrictions,
    generate_material, generate_contact_text, read_boilerplate, read_boilerplate_dated,
)
from backend.generator.docx_builder import build_offer_document
from backend.generator.pdf_converter import convert_to_pdf
from backend.generator.excel_builder import build_cost_excel
from backend.ingestion.contact_parser import parse_contact_file
from backend.ingestion.excel_parser import CostStepGroup, CostSubStep
from backend.config import CONTACTS_DIR

logger = logging.getLogger(__name__)

# Maps the section_key used in the regen request to the key used inside the sections dict
_REGEN_KEY_TO_SECTIONS_KEY: dict[str, str] = {
    "thank_you": "thankyou",
    "section1":  "section1",
    "section2":  "section2",
    "section3":  "section3",
    "section4":  "section4",
    "section5":  "section5",
    "section6":  "section6",
    "section7":  "section7",
    "section8":  "section8",
    "section9":  "section9",
    "section10": "section10_text",
}


def _sections_to_json(sections: dict) -> dict:
    """Convert sections dict to a JSON-serialisable form (handles CostStepGroup dataclasses)."""
    out: dict = {}
    for k, v in sections.items():
        if k == "section2" and isinstance(v, dict) and "steps" in v:
            steps_data = [
                dataclasses.asdict(s) if hasattr(s, "__dataclass_fields__") else s
                for s in v.get("steps", [])
            ]
            out[k] = {**v, "steps": steps_data}
        else:
            out[k] = v
    return out


def _reconstruct_step_group(d: dict) -> CostStepGroup:
    sub_steps = [
        CostSubStep(
            name=str(ss.get("name", "")),
            category=str(ss.get("category", "Service development")),
            hourly_rate=float(ss.get("hourly_rate", 0)),
            hours=float(ss.get("hours", 0)),
            persons=int(ss.get("persons", 1)),
        )
        for ss in d.get("sub_steps", [])
        if isinstance(ss, dict)
    ]
    return CostStepGroup(
        step_id=str(d.get("step_id", "")),
        name=str(d.get("name", "")),
        output=str(d.get("output", "")),
        sub_steps=sub_steps,
    )


def _sections_from_json(data: dict) -> dict:
    """Reconstruct sections dict from JSON (restores CostStepGroup objects for section2)."""
    sections: dict = {}
    for k, v in data.items():
        if k == "section2" and isinstance(v, dict) and "steps" in v:
            steps = [
                _reconstruct_step_group(sg) if isinstance(sg, dict) else sg
                for sg in v.get("steps", [])
            ]
            sections[k] = {**v, "steps": steps}
        else:
            sections[k] = v
    return sections


def _load_all_contacts() -> list[dict]:
    """Return every contact record found across all files in CONTACTS_DIR."""
    all_records: list[dict] = []
    for f in CONTACTS_DIR.iterdir():
        if f.suffix.lower() in (".xlsx", ".xls", ".docx", ".pdf"):
            try:
                records = parse_contact_file(f)
                all_records.extend(records.values())
            except Exception:
                continue
    return all_records


def _estimate_tokens(value) -> int:
    """Rough token count from output size: ~4 chars per token."""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    return max(1, len(text) // 4)


async def generate_offer(
    project: ProjectData,
    enable_web_search: bool = True,
    export_pdf: bool = True,
    generate_cost_table: bool = True,
    language: str = "en",
    output_dir: Path | None = None,
) -> AsyncIterator[dict]:
    """
    Async generator that yields progress dicts and finally yields result paths.
    Each yield: {'status': 'progress'|'done'|'error', 'section': str, 'message': str}
    Final yield: {'status': 'done', 'docx': str, 'pdf': str | None}
    Blocking LLM calls run in a thread pool via asyncio.to_thread() so the
    event loop stays free to handle other requests during generation.
    """
    sections = {}
    _current_section = "init"

    def _step(name: str):
        yield {"status": "progress", "section": name, "message": f"Generating {name}…"}

    _total_start = time.time()

    try:
        _current_section = "thank_you"
        yield {"status": "progress", "section": "thank_you", "message": "Generating thank-you paragraph…"}
        _t0 = time.time()
        sections["thankyou"] = await asyncio.to_thread(generate_thankyou, project, language=language)
        yield {"status": "stats", "section": "thank_you", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["thankyou"])}

        _current_section = "section1"
        yield {"status": "progress", "section": "section1", "message": "Generating Section 1: Background and Goals…"}
        _t0 = time.time()
        sections["section1"] = await asyncio.to_thread(generate_section1, project, enable_web_search=enable_web_search, language=language)
        yield {"status": "stats", "section": "section1", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["section1"])}

        _current_section = "section2"
        yield {"status": "progress", "section": "section2", "message": "Generating Section 2: Cost Estimation…"}
        _t0 = time.time()
        sections["section2"] = await asyncio.to_thread(generate_section2, project, language=language)
        yield {"status": "stats", "section": "section2", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["section2"])}

        _current_section = "section3"
        yield {"status": "progress", "section": "section3", "message": "Generating Section 3: Timetable…"}
        yield {"status": "progress", "section": "section4", "message": "Generating Section 4: Restrictions…"}
        yield {"status": "progress", "section": "section5", "message": "Generating Section 5: Material Transformation…"}
        _t0 = time.time()
        _sec3, _sec4, _sec5 = await asyncio.gather(
            asyncio.to_thread(generate_timetable,   project, language=language),
            asyncio.to_thread(generate_restrictions, project, language=language),
            asyncio.to_thread(generate_material,    project, language=language),
        )
        _elapsed_345 = round(time.time() - _t0, 1)
        sections["section3"] = _sec3
        sections["section4"] = _sec4
        sections["section5"] = _sec5
        yield {"status": "stats", "section": "section3", "elapsed_s": _elapsed_345, "tokens": _estimate_tokens(_sec3)}
        yield {"status": "stats", "section": "section4", "elapsed_s": _elapsed_345, "tokens": _estimate_tokens(_sec4)}
        yield {"status": "stats", "section": "section5", "elapsed_s": _elapsed_345, "tokens": _estimate_tokens(_sec5)}

        # Sections 6, 7, 9, 10 are boilerplate reads or trivial text — run together
        _current_section = "section6"
        yield {"status": "progress", "section": "section6", "message": "Loading Section 6: Documentation (boilerplate)…"}
        yield {"status": "progress", "section": "section7", "message": "Loading Section 7: Quality Assurance (SKOL)…"}
        yield {"status": "progress", "section": "section9", "message": "Loading Section 9: Delivery Terms (boilerplate)…"}
        yield {"status": "progress", "section": "section10", "message": "Generating Section 10: Contact Information…"}
        _t0 = time.time()
        (
            _sec6, _sec7,
            (_sec9, _sec9_pay),
            _sec10,
        ) = await asyncio.gather(
            asyncio.to_thread(read_boilerplate, "documentation", language=language),
            asyncio.to_thread(read_boilerplate, "quality",       language=language),
            asyncio.to_thread(
                lambda: (
                    read_boilerplate("delivery", language=language),
                    read_boilerplate_dated("payment", project.document_date, language=language),
                )
            ),
            asyncio.to_thread(generate_contact_text, project, language=language),
        )
        _elapsed_boiler = round(time.time() - _t0, 1)
        sections["section6"]      = _sec6
        sections["section7"]      = _sec7
        sections["section9"]      = _sec9
        sections["section9_payment"] = _sec9_pay
        sections["section10_text"] = _sec10
        yield {"status": "stats", "section": "section6",  "elapsed_s": _elapsed_boiler, "tokens": _estimate_tokens(_sec6)}
        yield {"status": "stats", "section": "section7",  "elapsed_s": _elapsed_boiler, "tokens": _estimate_tokens(_sec7)}
        yield {"status": "stats", "section": "section9",  "elapsed_s": _elapsed_boiler, "tokens": _estimate_tokens(_sec9)}
        yield {"status": "stats", "section": "section10", "elapsed_s": _elapsed_boiler, "tokens": _estimate_tokens(_sec10)}

        _current_section = "section8"
        yield {"status": "progress", "section": "section8", "message": "Generating Section 8: Project Team…"}
        _t0 = time.time()
        team_contacts = _load_all_contacts()
        sections["section8"] = await asyncio.to_thread(
            generate_section8, project, language=language, contacts=team_contacts or None
        )
        yield {"status": "stats", "section": "section8", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["section8"])}

        _current_section = "docx"
        yield {"status": "progress", "section": "docx", "message": "Assembling DOCX document…"}
        _t0 = time.time()
        docx_path = await asyncio.to_thread(build_offer_document, project, sections, language=language, output_dir=output_dir)
        yield {"status": "stats", "section": "docx", "elapsed_s": round(time.time() - _t0, 1), "tokens": 0}

        # Save sections cache alongside the DOCX so individual sections can be
        # rebuilt later without regenerating the entire offer.
        try:
            sections_cache = docx_path.with_suffix(".sections.json")
            sections_cache.write_text(
                json.dumps(_sections_to_json(sections), ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception as _cache_err:
            logger.warning("Failed to save sections cache: %s", _cache_err)

        xlsx_path = None
        if generate_cost_table:
            try:
                xlsx_path = build_cost_excel(project, sections["section2"], language=language, output_dir=output_dir)
            except Exception as e:
                yield {"status": "warning", "section": "docx", "message": f"Excel export failed: {e}"}

        pdf_path = None
        if export_pdf:
            _current_section = "pdf"
            yield {"status": "progress", "section": "pdf", "message": "Converting to PDF…"}
            _t0 = time.time()
            try:
                pdf_path = convert_to_pdf(docx_path)
                yield {"status": "stats", "section": "pdf", "elapsed_s": round(time.time() - _t0, 1), "tokens": 0}
            except Exception as e:
                yield {"status": "warning", "section": "pdf", "message": f"PDF conversion failed: {e}"}

        yield {
            "status": "done",
            "section": "complete",
            "message": "Offer generated successfully.",
            "docx": str(docx_path),
            "pdf": str(pdf_path) if pdf_path else None,
            "xlsx": str(xlsx_path) if xlsx_path else None,
            "elapsed_total_s": round(time.time() - _total_start, 1),
            "sections": _sections_to_json(sections),
        }

    except Exception as e:
        logger.error(
            "Offer generation failed at section %r: %s",
            _current_section, e, exc_info=True,
        )
        yield {"status": "error", "section": _current_section, "message": str(e)}
    finally:
        logger.info(
            "generate_offer finished in %.1fs (last_section=%s)",
            time.time() - _total_start,
            _current_section,
        )


def regenerate_section(
    project: ProjectData,
    section_key: str,
    enable_web_search: bool = True,
    language: str = "en",
    user_prompt: str | None = None,
) -> dict:
    """Re-run a single section chain and return the result."""
    if section_key == "thank_you":
        return {"thank_you": generate_thankyou(project, language=language, user_prompt=user_prompt)}
    elif section_key == "section1":
        return {"section1": generate_section1(project, enable_web_search, language=language, user_prompt=user_prompt)}
    elif section_key == "section2":
        return {"section2": generate_section2(project, language=language, user_prompt=user_prompt)}
    elif section_key == "section3":
        return {"section3": generate_timetable(project, language=language, user_prompt=user_prompt)}
    elif section_key == "section4":
        return {"section4": generate_restrictions(project, language=language, user_prompt=user_prompt)}
    elif section_key == "section5":
        return {"section5": generate_material(project, language=language, user_prompt=user_prompt)}
    elif section_key == "section6":
        return {"section6": read_boilerplate("documentation", language=language)}
    elif section_key == "section7":
        return {"section7": read_boilerplate("quality", language=language)}
    elif section_key == "section8":
        team_contacts = _load_all_contacts()
        return {"section8": generate_section8(project, language=language, contacts=team_contacts or None, user_prompt=user_prompt)}
    elif section_key == "section9":
        return {"section9": read_boilerplate("delivery", language=language)}
    elif section_key == "section10":
        return {"section10_text": generate_contact_text(project, language=language)}
    else:
        raise ValueError(f"Unknown section key: {section_key}")


def rebuild_offer_from_section(
    docx_path: Path,
    project: ProjectData,
    section_key: str,
    new_section_result: dict,
    language: str = "en",
    export_pdf: bool = False,
) -> dict:
    """Load cached sections, replace one section, rebuild DOCX (and Excel/PDF).

    Args:
        docx_path: Path to the existing DOCX (used to locate the sections cache).
        project: Project data.
        section_key: The regen key (e.g. "section2", "thank_you").
        new_section_result: Return value of ``regenerate_section`` (keyed by section_key).
        language: Document language.
        export_pdf: Whether to also convert the new DOCX to PDF.

    Returns:
        Dict with at least ``docx`` (str path).  May also contain ``pdf`` and/or ``xlsx``.
    """
    sections_cache = docx_path.with_suffix(".sections.json")
    if not sections_cache.exists():
        raise FileNotFoundError(f"Sections cache not found: {sections_cache}")

    sections = _sections_from_json(json.loads(sections_cache.read_text(encoding="utf-8")))

    # Map the regen key to the sections dict key and get the new value
    sections_key = _REGEN_KEY_TO_SECTIONS_KEY.get(section_key, section_key)
    new_val = new_section_result.get(section_key)

    # For section2, the raw result may still have CostStepGroup objects in steps;
    # if it has plain dicts (already serialised), reconstruct the dataclasses.
    if section_key == "section2" and isinstance(new_val, dict) and "steps" in new_val:
        steps_raw = new_val.get("steps", [])
        steps = [
            s if hasattr(s, "__dataclass_fields__") else _reconstruct_step_group(s)
            for s in steps_raw
        ]
        new_val = {**new_val, "steps": steps}

    sections[sections_key] = new_val

    # Rebuild DOCX — save alongside the original file (stays in the user's output dir)
    new_docx_path = build_offer_document(project, sections, language=language, output_dir=docx_path.parent)

    # Persist updated cache next to the new DOCX
    try:
        new_sections_cache = new_docx_path.with_suffix(".sections.json")
        new_sections_cache.write_text(
            json.dumps(_sections_to_json(sections), ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except Exception as _cache_err:
        logger.warning("Failed to save updated sections cache: %s", _cache_err)

    result: dict = {"docx": str(new_docx_path)}

    # Rebuild Excel when section2 was updated
    if section_key == "section2":
        try:
            xlsx_path = build_cost_excel(project, sections["section2"], language=language, output_dir=docx_path.parent)
            result["xlsx"] = str(xlsx_path)
        except Exception as _e:
            logger.warning("Excel rebuild failed: %s", _e)

    # Optionally convert to PDF
    if export_pdf:
        try:
            pdf_path = convert_to_pdf(new_docx_path)
            result["pdf"] = str(pdf_path)
        except Exception as _e:
            logger.warning("PDF rebuild failed: %s", _e)

    return result

