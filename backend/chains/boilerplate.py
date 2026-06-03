"""
Boilerplate injector — reads static text files and returns their content verbatim.
Sections 4, 6, 7, 9 use this to ensure legal/compliance text is never hallucinated.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
from langchain_core.prompts import PromptTemplate
from backend.config import BOILERPLATE_DIR, BOILERPLATE_FILES
from backend.ollama_client import get_llm
from backend.chains.extraction_chain import ProjectData


def _fmt_date(value: str) -> str:
    """Convert an ISO date string (YYYY-MM-DD) to Finnish d.M.YYYY format.
    Returns the original value unchanged if it is not a parseable ISO date."""
    if not value:
        return value
    try:
        d = date.fromisoformat(value)
        return f"{d.day}.{d.month}.{d.year}"
    except ValueError:
        return value


def read_boilerplate(key: str, language: str = "en") -> str:
    """
    Read a boilerplate file by key (e.g. 'quality', 'delivery', 'documentation').
    Picks the language-specific file first (e.g. quality_assurance_fi.txt),
    then falls back to the English version, then returns a placeholder.
    """
    lang_map = BOILERPLATE_FILES.get(key)
    if not lang_map:
        return f"[Boilerplate '{key}' not configured.]"

    # Try requested language, then 'en', then any available file in the map
    candidates = list(dict.fromkeys([language, "en"] + list(lang_map.keys())))
    for lang in candidates:
        filename = lang_map.get(lang)
        if not filename:
            continue
        path = BOILERPLATE_DIR / filename
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore").strip()

    # Legacy fallback: support old single-language filenames (e.g. delivery_terms.txt)
    # so existing installations keep working without re-running setup_first_run.py.
    legacy_names = [
        f"{key}.txt",
        f"{key.replace('_', '')}.txt",
    ] + [fn.rsplit("_", 1)[0] + ".txt" for fn in lang_map.values()]
    for name in dict.fromkeys(legacy_names):
        path = BOILERPLATE_DIR / name
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore").strip()

    # Tell the user which files are expected
    expected = ", ".join(lang_map.values())
    return (
        f"[Boilerplate file for '{key}' not found. "
        f"Expected one of: {expected} in {BOILERPLATE_DIR}]"
    )


def read_boilerplate_dated(key: str, doc_date: str = "", language: str = "en") -> str:
    """
    Like read_boilerplate() but replaces {payment_due_date} with the last
    calendar day of the month in which the document is dated.
    Falls back to today if doc_date is empty or unparseable.
    """
    import calendar
    from datetime import date

    text = read_boilerplate(key, language=language)

    try:
        parsed = date.fromisoformat(doc_date) if doc_date else date.today()
    except ValueError:
        parsed = date.today()

    last_day = calendar.monthrange(parsed.year, parsed.month)[1]
    d = date(parsed.year, parsed.month, last_day)
    due_date = f"{d.day}.{d.month}.{d.year}"
    return text.replace("{payment_due_date}", due_date)


def read_custom_boilerplate(filepath: Path) -> str:
    """Read any arbitrary boilerplate file."""
    if not filepath.exists():
        return f"[File not found: {filepath}]"
    return filepath.read_text(encoding="utf-8", errors="ignore").strip()


# ── LLM-assisted sections (light parameterization, not legal text) ────────────

_THANKYOU_PROMPT = PromptTemplate.from_template(
    """Write a short, warm, professional thank-you paragraph (2-3 sentences) for a sales offer document.
Thank the company for the meeting and express enthusiasm about the potential collaboration.

Customer company: {company_name}
Customer name: {customer_name}
Project: {project_name}

Thank-you paragraph:"""
)

_THANKYOU_PROMPT_FI = PromptTemplate.from_template(
    """Kirjoita lyhyt, lämmin ja ammattimainen kiitoskappale (2-3 lausetta) myyntitarjousdokumenttiin.
Kiitä yritystä tapaamisesta ja ilmaise innostusta mahdollisesta yhteistyöstä.
Kirjoita koko vastaus suomeksi.

Asiakasyritys: {company_name}
Asiakkaan nimi: {customer_name}
Projekti: {project_name}

Kiitoskappale:"""
)

_TIMETABLE_PROMPT = PromptTemplate.from_template(
    """Write a concise timetable section (2-4 sentences) for a sales offer document.
State when the project starts and ends, and mention any key milestones if known.

Project start: {project_start}
Project end: {project_end}
Other notes: {other_notes}

Timetable text:"""
)

_TIMETABLE_PROMPT_FI = PromptTemplate.from_template(
    """Kirjoita tiivis aikataulu-osio (2-4 lausetta) myyntitarjousdokumenttiin.
Kerro milloin projekti alkaa ja päättyy, ja mainitse mahdolliset välitavoitteet.
Kirjoita koko vastaus suomeksi.

Projektin aloitus: {project_start}
Projektin lopetus: {project_end}
Muut huomiot: {other_notes}

Aikatauluteksti:"""
)

_RESTRICTIONS_PROMPT = PromptTemplate.from_template(
    """Write a professional project restrictions and responsibilities section (3-5 sentences) 
for a sales offer document. Describe what work the project requires, 
state the payment model, and any customer responsibilities.

Payment type: {payment_type}
Constraints: {constraints}
Required work: {required_expertise}

Rules:
- Write each sentence on its own line.
- Start every line with a tab character (\\t).

Restrictions and responsibilities text:"""
)

_RESTRICTIONS_PROMPT_FI = PromptTemplate.from_template(
    """Kirjoita ammattimainen projektin rajoitteet ja vastuut -osio (3-5 lausetta)
myyntitarjousdokumenttiin. Kuvaile mitä työtä projekti vaatii,
kerro maksumalli ja asiakkaan vastuut.
Kirjoita koko vastaus suomeksi.

Maksutyyppi: {payment_type}
Rajoitteet: {constraints}
Vaadittu työ: {required_expertise}

Säännöt:
- Kirjoita jokainen lause omalle rivilleen.
- Aloita jokainen rivi sarkainmerkillä (\\t).

Rajoitteet ja vastuut -teksti:"""
)

_MATERIAL_PROMPT = PromptTemplate.from_template(
    """Write a concise material transformation section (2-4 sentences) for a sales offer document.
Describe what deliverables and materials the customer will receive.

Deliverables: {material_deliverables}
Project: {project_name}

Material transformation text:"""
)

_MATERIAL_PROMPT_FI = PromptTemplate.from_template(
    """Kirjoita tiivis materiaalimuutos-osio (2-4 lausetta) myyntitarjousdokumenttiin.
Kuvaile mitä toimituksia ja materiaaleja asiakas saa.
Kirjoita koko vastaus suomeksi.

Toimitukset: {material_deliverables}
Projekti: {project_name}

Materiaalimuutosteksti:"""
)


def generate_thankyou(project: ProjectData, language: str = "en") -> str:
    llm = get_llm()
    if language == "fi":
        prompt = _THANKYOU_PROMPT_FI.format(
            company_name=project.company_name or "yrityksenne",
            customer_name=project.customer_name or "",
            project_name=project.project_name or "projekti",
        )
    else:
        prompt = _THANKYOU_PROMPT.format(
            company_name=project.company_name or "your company",
            customer_name=project.customer_name or "",
            project_name=project.project_name or "the project",
        ) + "\n\nWrite the entire response in English."
    return llm.invoke(prompt).strip()


def generate_timetable(project: ProjectData, language: str = "en") -> str:
    llm = get_llm()
    if language == "fi":
        prompt = _TIMETABLE_PROMPT_FI.format(
            project_start=_fmt_date(project.project_start) or "Vahvistetaan myöhemmin",
            project_end=_fmt_date(project.project_end) or "Vahvistetaan myöhemmin",
            other_notes=project.other_notes or "Ei muita huomioita",
        )
    else:
        prompt = _TIMETABLE_PROMPT.format(
            project_start=_fmt_date(project.project_start) or "To be confirmed",
            project_end=_fmt_date(project.project_end) or "To be confirmed",
            other_notes=project.other_notes or "None",
        ) + "\n\nWrite the entire response in English."
    return llm.invoke(prompt).strip()


def generate_restrictions(project: ProjectData, language: str = "en") -> str:
    llm = get_llm()
    if language == "fi":
        prompt = _RESTRICTIONS_PROMPT_FI.format(
            payment_type=project.payment_type or "tuntiperusteinen",
            constraints=project.constraints or "Ei rajoitteita",
            required_expertise=project.required_expertise or "Ei määritelty",
        )
    else:
        prompt = _RESTRICTIONS_PROMPT.format(
            payment_type=project.payment_type or "hourly",
            constraints=project.constraints or "None",
            required_expertise=project.required_expertise or "Not specified",
        ) + "\n\nWrite the entire response in English."
    return llm.invoke(prompt).strip()


def generate_material(project: ProjectData, language: str = "en") -> str:
    llm = get_llm()
    if language == "fi":
        prompt = _MATERIAL_PROMPT_FI.format(
            material_deliverables=project.material_deliverables or "Vahvistetaan myöhemmin",
            project_name=project.project_name or "projekti",
        )
    else:
        prompt = _MATERIAL_PROMPT.format(
            material_deliverables=project.material_deliverables or "To be confirmed",
            project_name=project.project_name or "the project",
        ) + "\n\nWrite the entire response in English."
    return llm.invoke(prompt).strip()


def generate_contact_text(project: ProjectData, language: str = "en", salesperson_contact: dict | None = None) -> str:
    """
    Returns a fully static, templated contact/closing section.
    Name, phone, email, and title come from salesperson_contact (loaded from contacts file).
    Falls back to project.salesperson_name if no contact record is found.
    """
    contact = salesperson_contact or {}
    name  = contact.get("name")  or project.salesperson_name or "Our Representative"
    phone = contact.get("phone") or "—"
    email = contact.get("email") or "—"
    title = contact.get("title") or ""

    if language == "fi":
        lines = [
            "Toivomme, että tarjouksemme sopii teille ja johtaa yhteistyöhön yritystemme välillä.\n",
            f"Tätä sopimusta koskevissa asioissa yhteyshenkilönä toimii {name}, "
            f"joka voi myös antaa lisätietoja tarjouksesta.\n",
            f"Puhelinnumero: {phone}",
            f"Sähköposti: {email}\n",
            "Kunnioittavasti\n",
            name,
        ]
    else:
        lines = [
            "We hope that our proposal will be suitable for you and lead to "
            f"cooperation between our companies.\n",
            f"The contact person for matters relating to the agreement is {name}, "
            f"who can also provide additional information about the proposal.\n",
            f"Phone number: {phone}",
            f"Email: {email}\n",
            "Respectfully\n",
            name,
        ]

    if title:
        lines.append(title)

    return "\n".join(lines).strip()
