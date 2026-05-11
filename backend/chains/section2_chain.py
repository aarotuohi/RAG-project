"""
Section 2 chain — Project implementation and cost estimation.
Retrieves similar historical projects from ChromaDB,
asks the LLM to produce a structured step list (JSON),
then computes the grand total programmatically.
"""
from __future__ import annotations
import json
import re

from langchain_core.prompts import PromptTemplate

from backend.ollama_client import get_llm
from backend.vectorstore.chroma_client import get_collection
from backend.config import CHROMA_COLLECTION_COST, WORK_CATEGORIES, CATEGORY_RATES
from backend.chains.extraction_chain import ProjectData
from backend.ingestion.excel_parser import CostSubStep, CostStepGroup


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


def _clean_json(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    return text.strip()


def _detect_project_category(description: str, k: int = 20) -> list[str]:
    """
    Query ChromaDB without any filter and vote on 'project_category' metadata
    among the top-k most similar chunks.

    The query prioritises expertise and deliverable signals (strongest type
    indicators) over project name.

    Returns:
      - [best_category]          — one clear winner (strictly more votes than second)
      - [first, second]          — tie at the top; use both as fallback
      - []                       — no categories in collection (flat layout)
    """
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
    """
    Retrieve the most relevant historical cost phases from ChromaDB.

    *categories* controls which sub-folders are searched:
      - 1 category  → exact metadata filter on 'project_category'
      - 2 categories → '$in' filter covering both sub-folders (fallback)
      - None / []   → no filter; searches the entire collection
    """
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

        # Sort by score ascending (smaller cosine distance = more relevant).
        # Drop phases whose similarity score is too poor (> threshold) so that
        # unrelated historical data doesn't pollute the estimate.
        _SCORE_THRESHOLD = 1.2  # cosine distance; tune if needed
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

    # --- Step 1: Generate description paragraph ---
    desc_prompt = _DESCRIPTION_PROMPT.format(
        project_name=project.project_name or "New Project",
        goals=project.goals or "Not specified",
        payment_type=project.payment_type or "hourly",
        material_deliverables=project.material_deliverables or "Not specified",
    ) + f"\n\n{lang_note}"
    description_text = llm.invoke(desc_prompt).strip()

    # --- Step 2: Generate structured cost estimate ---
    est_prompt = _ESTIMATION_PROMPT.format(
        project_name=project.project_name or "New Project",
        description=f"{project.goals} {project.constraints}",
        goals=project.goals or "Not specified",
        required_expertise=project.required_expertise or "Not specified",
        payment_type=project.payment_type or "hourly",
        historical_data=historical_data[:8000],
        categories="\n".join(
            f"  - {cat}: {CATEGORY_RATES[cat]}\u20ac/h"
            for cat in WORK_CATEGORIES
        ),
        output_language="Finnish" if language == "fi" else "English",
    ) + f"\n\nIMPORTANT: All text fields in the JSON (name, output, sub-step name) MUST be written in {'Finnish' if language == 'fi' else 'English'}, regardless of the language of the historical data."
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
    except json.JSONDecodeError:
        pass

    grand_total = round(sum(sg.total_cost for sg in step_groups), 2)

    return {
        "description_text": description_text,
        "steps": step_groups,
        "grand_total": grand_total,
        "payment_type": project.payment_type or "hourly",
        "project_output": project.goals or "",
    }
