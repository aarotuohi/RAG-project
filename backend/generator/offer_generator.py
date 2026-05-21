"""
Offer generator — orchestrates all section chains to produce the complete offer.
Runs sections sequentially and yields progress events.
"""
from __future__ import annotations
import asyncio
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
from backend.ingestion.contact_parser import parse_contact_file, lookup
from backend.config import CONTACTS_DIR

logger = logging.getLogger(__name__)


def _load_salesperson(salesperson_name: str) -> dict | None:
    """Load salesperson contact details from the first file found in CONTACTS_DIR."""
    for f in CONTACTS_DIR.iterdir():
        if f.suffix.lower() in (".xlsx", ".xls", ".docx", ".pdf"):
            try:
                records = parse_contact_file(f)
                match = lookup(records, salesperson_name)
                if match:
                    return match
            except Exception:
                continue
    return None


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
        _t0 = time.time()
        sections["section3"] = await asyncio.to_thread(generate_timetable, project, language=language)
        yield {"status": "stats", "section": "section3", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["section3"])}

        _current_section = "section4"
        yield {"status": "progress", "section": "section4", "message": "Generating Section 4: Restrictions…"}
        _t0 = time.time()
        sections["section4"] = await asyncio.to_thread(generate_restrictions, project, language=language)
        yield {"status": "stats", "section": "section4", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["section4"])}

        _current_section = "section5"
        yield {"status": "progress", "section": "section5", "message": "Generating Section 5: Material Transformation…"}
        _t0 = time.time()
        sections["section5"] = await asyncio.to_thread(generate_material, project, language=language)
        yield {"status": "stats", "section": "section5", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["section5"])}

        _current_section = "section6"
        yield {"status": "progress", "section": "section6", "message": "Loading Section 6: Documentation (boilerplate)…"}
        _t0 = time.time()
        sections["section6"] = read_boilerplate("documentation", language=language)
        yield {"status": "stats", "section": "section6", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["section6"])}

        _current_section = "section7"
        yield {"status": "progress", "section": "section7", "message": "Loading Section 7: Quality Assurance (SKOL)…"}
        _t0 = time.time()
        sections["section7"] = read_boilerplate("quality", language=language)
        yield {"status": "stats", "section": "section7", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["section7"])}

        _current_section = "section8"
        yield {"status": "progress", "section": "section8", "message": "Generating Section 8: Project Team…"}
        _t0 = time.time()
        team_contacts = _load_all_contacts()
        sections["section8"] = await asyncio.to_thread(
            generate_section8, project, language=language, contacts=team_contacts or None
        )
        yield {"status": "stats", "section": "section8", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["section8"])}

        _current_section = "section9"
        yield {"status": "progress", "section": "section9", "message": "Loading Section 9: Delivery Terms (boilerplate)…"}
        _t0 = time.time()
        sections["section9"] = read_boilerplate("delivery", language=language)
        sections["section9_payment"] = read_boilerplate_dated("payment", project.document_date, language=language)
        yield {"status": "stats", "section": "section9", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["section9"])}

        _current_section = "section10"
        yield {"status": "progress", "section": "section10", "message": "Generating Section 10: Contact Information…"}
        _t0 = time.time()
        salesperson_contact = _load_salesperson(project.salesperson_name)
        # Populate salesperson fields into ProjectData so all chains can access them
        if salesperson_contact:
            project.salesperson_phone = salesperson_contact.get("phone", "")
            project.salesperson_email = salesperson_contact.get("email", "")
            project.salesperson_title = salesperson_contact.get("title", "")
        sections["section10_text"] = generate_contact_text(project, language=language, salesperson_contact=salesperson_contact)
        yield {"status": "stats", "section": "section10", "elapsed_s": round(time.time() - _t0, 1), "tokens": _estimate_tokens(sections["section10_text"])}

        _current_section = "docx"
        yield {"status": "progress", "section": "docx", "message": "Assembling DOCX document…"}
        _t0 = time.time()
        docx_path = await asyncio.to_thread(build_offer_document, project, sections, salesperson_contact, language=language)
        yield {"status": "stats", "section": "docx", "elapsed_s": round(time.time() - _t0, 1), "tokens": 0}

        xlsx_path = None
        if generate_cost_table:
            try:
                xlsx_path = build_cost_excel(project, sections["section2"], language=language)
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
) -> dict:
    """Re-run a single section chain and return the result."""
    if section_key == "thankyou":
        return {"thankyou": generate_thankyou(project)}
    elif section_key == "section1":
        return {"section1": generate_section1(project, enable_web_search)}
    elif section_key == "section2":
        return {"section2": generate_section2(project)}
    elif section_key == "section3":
        return {"section3": generate_timetable(project)}
    elif section_key == "section4":
        return {"section4": generate_restrictions(project)}
    elif section_key == "section5":
        return {"section5": generate_material(project)}
    elif section_key == "section6":
        return {"section6": read_boilerplate("documentation")}
    elif section_key == "section7":
        return {"section7": read_boilerplate("quality")}
    elif section_key == "section8":
        return {"section8": generate_section8(project)}
    elif section_key == "section9":
        return {"section9": read_boilerplate("delivery")}
    elif section_key == "section10":
        return {"section10_text": generate_contact_text(project)}
    else:
        raise ValueError(f"Unknown section key: {section_key}")
