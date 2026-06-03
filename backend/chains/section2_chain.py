"""
Section 2 chain — Project implementation and cost estimation.
Retrieves similar historical projects from ChromaDB,
asks the LLM to produce a structured step list (JSON),
then computes the grand total programmatically.
"""
from __future__ import annotations
import json
import logging
import re

from langchain_core.prompts import PromptTemplate

from backend.ollama_client import get_llm
from backend.vectorstore.chroma_client import get_collection
from backend.config import CHROMA_COLLECTION_COST, WORK_CATEGORIES, CATEGORY_RATES
from backend.chains.extraction_chain import ProjectData
from backend.ingestion.excel_parser import CostSubStep, CostStepGroup

logger = logging.getLogger(__name__)


_ESTIMATION_PROMPT = PromptTemplate.from_template(
    """You are a project cost estimation expert. Your job is to produce an accurate \
step-by-step cost estimate for a new project by learning from real historical project data.

════════════════════════════════════════
NEW PROJECT
════════════════════════════════════════
Name: {project_name}
Goals: {goals}
Constraints: {description}
Required expertise: {required_expertise}
Payment type: {payment_type}

════════════════════════════════════════
HISTORICAL PROJECTS — REAL DATA FROM PREVIOUS CALCULATIONS
════════════════════════════════════════
{historical_data}

════════════════════════════════════════
HOW TO READ THE HISTORICAL DATA ABOVE
════════════════════════════════════════
Each historical block is structured as one work phase (= one STEP in your output):
  "Phase: <phase name>"        → map this to one step object  (step_id: "STEP N", name: "...")
  "Sub-step N.M: <task name>"  → map each of these to one entry inside that step's "sub_steps" array

Every indented line under a Phase header is a separate sub-step with its own Rate, Hours and Total.
Do NOT flatten all sub-steps into a single step — preserve the phase → sub-step hierarchy.

════════════════════════════════════════
INSTRUCTIONS
════════════════════════════════════════
1. Study the historical projects above carefully.
2. Identify which historical steps and sub-steps are most similar to what the new project needs.
3. Re-use the structure (phases and sub-steps) from the most relevant historical project as your
   starting template — do not invent a completely new structure when a good historical match exists.
4. For hourly rates: use the rate shown in the matching historical sub-step (Rate: X€/h).
   Only fall back to the standard rates below when a sub-step has NO historical equivalent.
5. Scale hours up or down based on project size and complexity compared to the historical example.
6. Add any sub-steps the new project needs that don't appear in history, using the standard rates.

Standard hourly rates (€/h) — use ONLY when no historical rate is available for a sub-step:
{categories}

CRITICAL: You MUST use the nested "sub_steps" array. Do NOT place hourly_rate/hours/persons \
directly on the step object — only inside sub_steps items.

Return ONLY a JSON array — no explanation, no markdown, no totals row:
[
  {{
    "step_id": "STEP 1",
    "name": "main step name in {output_language}",
    "output": "short description of what this step delivers",
    "sub_steps": [
      {{
        "name": "sub-step description",
        "category": "one of the work categories above",
        "hourly_rate": <rate from historical data, or standard rate if no match>,
        "hours": <estimated hours per person for this sub-step>,
        "persons": <number of people needed for this sub-step>
      }}
    ]
  }},
  ...
]"""
)

_DESCRIPTION_PROMPT = PromptTemplate.from_template(
    """Write a professional 2-3 sentence paragraph for a sales offer document describing 
the project implementation approach. Mention whether it is hour-based or fixed-price.

Project name: {project_name}
Goals: {goals}
Payment type: {payment_type}
Material deliverables: {material_deliverables}

Implementation paragraph:"""
)

_ESTIMATION_PROMPT_FI = PromptTemplate.from_template(
    """Olet projektin kustannusarviointiasiantuntija. Tehtäväsi on tuottaa tarkka \
vaiheistettu kustannusarvio uudelle projektille oppimalla aidosta historiallisesta projektidatasta.

════════════════════════════════════════
UUSI PROJEKTI
════════════════════════════════════════
Nimi: {project_name}
Tavoitteet: {goals}
Rajoitteet: {description}
Vaadittu osaaminen: {required_expertise}
Maksutapa: {payment_type}

════════════════════════════════════════
HISTORIALLISET PROJEKTIT — AITO DATA AIEMMISTA LASKELMISTA
════════════════════════════════════════
{historical_data}

════════════════════════════════════════
KUINKA LUKEA HISTORIALLISTA DATAA
════════════════════════════════════════
Jokainen historiallinen lohko edustaa yhtä työvaihetta (= yksi VAIHE tulosteen JSON:ssa):
  "Phase: <vaiheen nimi>"          → muodosta yksi step-objekti  (step_id: "STEP N", name: "...")
  "Sub-step N.M: <tehtävän nimi>"  → muodosta yksi merkintä kyseisen vaiheen "sub_steps"-taulukkoon

Jokainen sisennetty rivi Phase-otsikon alla on erillinen alivaihe omalla Rate-, Hours- ja Total-arvollaan.
ÄLÄ litistä kaikkia alivaiheita yhdeksi vaiheeksi — säilytä vaihe → alivaihe -hierarkia.

════════════════════════════════════════
OHJEET
════════════════════════════════════════
1. Tutki historiallisia projekteja huolellisesti.
2. Tunnista, mitkä historialliset vaiheet ja alivaiheet vastaavat parhaiten uuden projektin tarpeita.
3. Käytä relevanteimman historiallisen projektin rakennetta (vaiheet ja alivaiheet) lähtökohtana —
   älä keksi täysin uutta rakennetta, jos sopiva historiallinen malli on olemassa.
4. Tuntihintoja varten: käytä vastaavan historiallisen alivaiheen hintaa (Rate: X€/h).
   Käytä alla olevia vakiohintoja vain, jos alivaiheelle ei löydy historiallista vastaavuutta.
5. Skaalaa tunteja ylös tai alas projektin koon ja monimutkaisuuden perusteella verrattuna historialliseen esimerkkiin.
6. Lisää alivaiheita, joita uusi projekti tarvitsee mutta joita ei esiinny historiassa — käytä vakiohintoja.

Vakiotuntihinnat (€/h) — käytä VAIN, jos alivaiheelle ei ole historiallista hintaa:
{categories}

KRIITTISTÄ: Sinun TÄYTYY käyttää sisäkkäistä "sub_steps"-taulukkoa. ÄLÄ aseta hourly_rate/hours/persons \
suoraan step-objektiin — ainoastaan sub_steps-kohteiden sisälle.

Palauta VAIN JSON-taulukko — ei selityksiä, ei markdownia, ei yhteensä-riviä:
[
  {{
    "step_id": "STEP 1",
    "name": "päävaiheen nimi suomeksi",
    "output": "lyhyt kuvaus vaiheen tuotoksesta",
    "sub_steps": [
      {{
        "name": "alivaiheen kuvaus",
        "category": "yksi yllä olevista työkategorioista",
        "hourly_rate": <hinta historiallisesta datasta, tai vakiohinta jos ei vastaavuutta>,
        "hours": <arvioitu tuntimäärä per henkilö tässä alivaiheessa>,
        "persons": <tarvittava henkilömäärä tässä alivaiheessa>
      }}
    ]
  }},
  ...
]"""
)

_DESCRIPTION_PROMPT_FI = PromptTemplate.from_template(
    """Kirjoita ammattimainen 2-3 lauseen kappale myyntitarjousasiakirjaan, joka kuvaa
projektin toteutustapaa. Mainitse, onko kyseessä tuntiperusteinen vai kiinteähintainen projekti.

Projektin nimi: {project_name}
Tavoitteet: {goals}
Maksutapa: {payment_type}
Materiaalitoimitukset: {material_deliverables}

Toteutuskappale:"""
)

_SHORT_DESC_PROMPT = PromptTemplate.from_template(
    """Write a single compact sentence (max 20 words) summarising what this project delivers.
No preamble, no full stop at the end.

Project name: {project_name}
Goals: {goals}
Deliverables: {material_deliverables}

Summary:"""
)

_SHORT_DESC_PROMPT_FI = PromptTemplate.from_template(
    """Kirjoita yksi tiivis lause (enintään 20 sanaa), joka kuvaa mitä tämä projekti tuottaa.
Ei johdantoa, ei pistettä lauseen lopussa.

Projektin nimi: {project_name}
Tavoitteet: {goals}
Toimitukset: {material_deliverables}

Tiivistelmä:"""
)


def _historical_rates(historical_data: str) -> dict[str, float]:
  
    totals: dict[str, list[float]] = {}
    for line in historical_data.splitlines():
        cat_m  = re.search(r"Category:\s*([^|]+)", line)
        rate_m = re.search(r"Rate:\s*([\d.,]+)\s*€/h", line)
        if not cat_m or not rate_m:
            continue
        cat  = cat_m.group(1).strip()
        try:
            rate = float(rate_m.group(1).replace(",", "."))
        except ValueError:
            continue
        if rate > 0:
            totals.setdefault(cat, []).append(rate)

    result: dict[str, float] = {}
    for cat, rates in totals.items():
        avg = round(sum(rates) / len(rates))
        # Normalise to the canonical WORK_CATEGORIES spelling (case-insensitive)
        matched = next(
            (k for k in WORK_CATEGORIES if k.lower() == cat.lower()),
            None,
        )
        if matched:
            result[matched] = avg
        else:
            result[cat] = avg
    return result


def _clean_json(text: str) -> str:
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    text = text.strip()
    # Claude sometimes adds preamble text before the JSON array/object.
    # Find the first [ or { and the matching last ] or }.
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        start = text.find(open_ch)
        end   = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]
    return text


def _detect_project_category(description: str, k: int = 20) -> list[str]:
   
    try:
        collection = get_collection(CHROMA_COLLECTION_COST)
        results = collection.similarity_search_with_score(description, k=k)
        counts: dict[str, int] = {}
        for doc, _ in results:
            cat = doc.metadata.get("project_category") or ""
            if cat:
                counts[cat] = counts.get(cat, 0) + 1
        if not counts:
            return []
        ranked = sorted(counts, key=lambda c: counts[c], reverse=True)
        # Clear winner when top has strictly more votes than second place
        if len(ranked) == 1 or counts[ranked[0]] > counts[ranked[1]]:
            return ranked[:1]
        # Tied at the top — return both as fallback
        return ranked[:2]
    except Exception:
        return []


def _retrieve_similar_projects(description: str, k: int = 8, categories: list[str] | None = None) -> str:
   
    try:
        collection = get_collection(CHROMA_COLLECTION_COST)

        # Build metadata filter from the detected categories.
        if categories and len(categories) == 1:
            cat_filter: dict | None = {"project_category": categories[0]}
        elif categories and len(categories) >= 2:
            cat_filter = {"project_category": {"$in": categories[:2]}}
        else:
            cat_filter = None

        # Build a list of targeted sub-queries: overall description + one per
        # expertise keyword (comma/semicolon separated).
        expertise_parts = [p.strip() for p in re.split(r"[,;]+", description) if p.strip()]
        queries = [description] + expertise_parts

        # Collect (score, page_content, source) tuples; lower distance = better.
        seen_content: set[str] = set()
        candidates: list[tuple[float, str, str]] = []

        for query in queries:
            results = collection.similarity_search_with_score(query, k=k, filter=cat_filter)
            for doc, score in results:
                content = doc.page_content
                if content in seen_content:
                    continue
                seen_content.add(content)
                src = doc.metadata.get("source", "unknown")
                candidates.append((score, content, src))

      
        _SCORE_THRESHOLD = 1.2  
        candidates = [(s, c, src) for s, c, src in candidates if s <= _SCORE_THRESHOLD]

        if not candidates:
            return "No sufficiently similar historical data found."

        # Keep the top 12 phases.
        candidates.sort(key=lambda x: x[0])
        top = candidates[:12]

        # Format for the LLM — each phase is a self-contained block.
        sections = []
        for i, (score, content, src) in enumerate(top, 1):
            src_name = src.replace("\\", "/").split("/")[-1]
            sections.append(f"--- Historical phase {i} (from {src_name}, score={score:.3f}) ---\n{content}")

        return "\n\n".join(sections)
    except Exception:
        return "No historical data available."



def generate_section2(project: ProjectData, language: str = "en") -> dict:
    """
    Returns:
      {
        'description_text': str,
        'steps': [CostStepGroup, ...],
        'grand_total': float,
        'payment_type': str,
        'project_output': str,
      }
    """
    lang_note = "Write the entire response in Finnish." if language == "fi" else "Write the entire response in English."
    llm = get_llm()

    # Build the retrieval query: weight expertise and deliverables highest
    # (strongest project-type signals), then goals and name for context.
    description_query = " ".join(filter(None, [
        project.required_expertise,
        project.material_deliverables,
        project.project_name,
        project.goals,
        project.constraints,
    ]))

    # Category detection uses an even tighter signal: just expertise + deliverables
    category_query = " ".join(filter(None, [
        project.required_expertise,
        project.material_deliverables,
        project.project_name,
    ])) or description_query

    detected_category = _detect_project_category(category_query)
    historical_data = _retrieve_similar_projects(description_query, categories=detected_category or None)

    is_fi = language == "fi"
    desc_template = _DESCRIPTION_PROMPT_FI if is_fi else _DESCRIPTION_PROMPT
    est_template  = _ESTIMATION_PROMPT_FI  if is_fi else _ESTIMATION_PROMPT

    # --- Step 1: Generate description paragraph ---
    desc_kwargs = dict(
        project_name=project.project_name or ("Uusi projekti" if is_fi else "New Project"),
        goals=project.goals or ("Ei määritelty" if is_fi else "Not specified"),
        payment_type=project.payment_type or "hourly",
        material_deliverables=project.material_deliverables or ("Ei määritelty" if is_fi else "Not specified"),
    )
    desc_prompt = desc_template.format(**desc_kwargs)
    if not is_fi:
        desc_prompt += f"\n\n{lang_note}"
    description_text = llm.invoke(desc_prompt).strip()

    # --- Short description (single sentence for Excel header) ---
    short_desc_template = _SHORT_DESC_PROMPT_FI if is_fi else _SHORT_DESC_PROMPT
    short_desc_kwargs = dict(
        project_name=project.project_name or ("Uusi projekti" if is_fi else "New Project"),
        goals=project.goals or ("Ei määritelty" if is_fi else "Not specified"),
        material_deliverables=project.material_deliverables or ("Ei määritelty" if is_fi else "Not specified"),
    )
    short_description = llm.invoke(short_desc_template.format(**short_desc_kwargs)).strip()

    # Derive hourly rates exclusively from historical data.
    # CATEGORY_RATES is used only when the cost_history collection is empty.
    fallback_rates = _historical_rates(historical_data)
    if fallback_rates:
        _rate_lines = [
            f"  - {cat}: {fallback_rates[cat]}€/h"
            for cat in WORK_CATEGORIES if cat in fallback_rates
        ] + [
            f"  - {cat}: {rate}€/h"
            for cat, rate in fallback_rates.items() if cat not in WORK_CATEGORIES
        ]
        _categories_str = "\n".join(_rate_lines) or "  (Derive rates directly from the historical phases above)"
    else:
        # No historical data ingested yet — show defaults so the LLM can still produce numbers
        _categories_str = "\n".join(
            f"  - {cat}: {CATEGORY_RATES[cat]}€/h (default — add historical cost data for real rates)"
            for cat in WORK_CATEGORIES
        )

    # --- Step 2: Generate structured cost estimate ---
    est_kwargs = dict(
        project_name=project.project_name or ("Uusi projekti" if is_fi else "New Project"),
        description=f"{project.goals} {project.constraints}",
        goals=project.goals or ("Ei määritelty" if is_fi else "Not specified"),
        required_expertise=project.required_expertise or ("Ei määritelty" if is_fi else "Not specified"),
        payment_type=project.payment_type or "hourly",
        historical_data=historical_data[:8000],
        categories=_categories_str,
    )
    if not is_fi:
        est_kwargs["output_language"] = "English"
    est_prompt = est_template.format(**est_kwargs)
    if not is_fi:
        est_prompt += "\n\nIMPORTANT: All text fields in the JSON (name, output, sub-step name) MUST be written in English, regardless of the language of the historical data."
    else:
        est_prompt += "\n\nTÄRKEÄÄ: Kaikki JSON:n tekstikentät (name, output, alivaiheen name) TÄYTYY kirjoittaa suomeksi, riippumatta historiallisen datan kielestä."
    raw = llm.invoke(est_prompt)
    cleaned = _clean_json(raw)

    step_groups: list[CostStepGroup] = []
    try:
        parsed = json.loads(cleaned)
        # LLM sometimes wraps the array: {"steps": [...]} or {"cost_steps": [...]}
        if isinstance(parsed, dict):
            parsed = next(
                (v for v in parsed.values() if isinstance(v, list)),
                []
            )
        step_list = parsed if isinstance(parsed, list) else []
        for i, s in enumerate(step_list):
            if not isinstance(s, dict):
                continue
            try:
                sub_steps: list[CostSubStep] = []
                for ss in s.get("sub_steps", []):
                    if not isinstance(ss, dict):
                        continue
                    try:
                        sub_steps.append(CostSubStep(
                            name=str(ss.get("name", "")),
                            category=str(ss.get("category", "Service development")),
                            hourly_rate=float(ss.get("hourly_rate", 0)),
                            hours=float(ss.get("hours", 0)),
                            persons=int(ss.get("persons", 1)),
                        ))
                    except Exception:
                        continue
                raw_id = str(s.get("step_id", "")).strip()
                step_id = raw_id if raw_id else f"STEP {i+1}"
                step_groups.append(CostStepGroup(
                    step_id=step_id,
                    name=str(s.get("name", "")),
                    output=str(s.get("output", "")),
                    sub_steps=sub_steps,
                ))
            except Exception:
                continue
    except json.JSONDecodeError as e:
        logger.error(
            "section2 JSON parse failed: %s\nRaw response (first 500 chars): %s",
            e, cleaned[:500]
        )

    grand_total = round(sum(sg.total_cost for sg in step_groups), 2)

    return {
        "description_text": description_text,
        "short_description": short_description,
        "steps": step_groups,
        "grand_total": grand_total,
        "payment_type": project.payment_type or "hourly",
        "project_output": project.goals or "",
    }
