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
from backend.config import CHROMA_COLLECTION_COST, WORK_CATEGORIES, DEFAULT_HOURLY_RATES
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
DEFAULT HOURLY RATES (use these when no historical rate is available)
════════════════════════════════════════
{default_rates}

════════════════════════════════════════
INSTRUCTIONS
════════════════════════════════════════
1. Study the historical projects above carefully.
2. Identify which historical steps are most similar to what the new project needs.
3. Prefer EXACT hourly rates from the historical data for matching work types.
4. If no historical rate exists for a work type, use the default rates above — NEVER output 0.
5. Scale hours up or down based on project complexity compared to historical examples.
6. Add any steps the new project needs that don't appear in history.

Work categories available: {categories}

Return ONLY a JSON array — no explanation, no markdown, no totals row:
[
  {{
    "step_id": "STEP 1",
    "name": "main step name in the same language as the project name",
    "output": "short description of what this step delivers",
    "sub_steps": [
      {{
        "name": "sub-step description",
        "category": "one of the work categories above",
        "hourly_rate": <number from historical data or default rates — never 0>,
        "hours": <estimated hours per person for this sub-step>,
        "persons": <number of people needed for this sub-step>
      }}
    ]
  }},
  ...
]"""
)

_DESCRIPTION_PROMPT = PromptTemplate.from_template(
    """Write exactly one professional sentence for a sales offer document describing the project implementation approach. Mention whether it is hour-based or fixed-price.

Project name: {project_name}
Goals: {goals}
Payment type: {payment_type}
Material deliverables: {material_deliverables}

One sentence:"""
)


def _clean_json(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    return text.strip()


def _retrieve_similar_projects(description: str, k: int = 12) -> str:
    """
    Retrieve the most relevant historical cost chunks from ChromaDB.
    Fetches k chunks but deduplicates by source file so the LLM sees
    data from multiple different projects rather than the same file repeated.
    """
    try:
        collection = get_collection(CHROMA_COLLECTION_COST)
        docs = collection.similarity_search(description, k=k)

        # Deduplicate: keep only the best (first) chunk per source file
        seen_sources: set[str] = set()
        unique_docs = []
        for d in docs:
            src = d.metadata.get("source", "")
            if src not in seen_sources:
                seen_sources.add(src)
                unique_docs.append(d)

        if not unique_docs:
            return "No historical data available."

        sections = []
        for i, d in enumerate(unique_docs, 1):
            src_name = d.metadata.get("source", "unknown")
            # Show just the filename, not the full path
            src_name = src_name.replace("\\", "/").split("/")[-1]
            sections.append(f"--- Historical project {i}: {src_name} ---\n{d.page_content}")

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

    description_query = (
        f"{project.project_name} {project.goals} {project.required_expertise} "
        f"{project.constraints} {project.material_deliverables} {project.payment_type}"
    )
    historical_data = _retrieve_similar_projects(description_query)

    # --- Step 1: Generate description paragraph ---
    desc_prompt = _DESCRIPTION_PROMPT.format(
        project_name=project.project_name or "New Project",
        goals=project.goals or "Not specified",
        payment_type=project.payment_type or "hourly",
        material_deliverables=project.material_deliverables or "Not specified",
    ) + f"\n\n{lang_note}"
    description_text = llm.invoke(desc_prompt).strip()

    # --- Step 2: Generate structured cost estimate ---
    default_rates_text = "\n".join(
        f"  {cat}: {rate}€/h" for cat, rate in DEFAULT_HOURLY_RATES.items()
    )
    est_prompt = _ESTIMATION_PROMPT.format(
        project_name=project.project_name or "New Project",
        description=f"{project.goals} {project.constraints}",
        goals=project.goals or "Not specified",
        required_expertise=project.required_expertise or "Not specified",
        payment_type=project.payment_type or "hourly",
        historical_data=historical_data[:8000],
        default_rates=default_rates_text,
        categories=", ".join(WORK_CATEGORIES),
    )
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
                        category = str(ss.get("category", "Services"))
                        hourly_rate = float(ss.get("hourly_rate", 0))
                        # Safety net: if LLM still returned 0, apply the default for the category
                        if hourly_rate == 0:
                            hourly_rate = DEFAULT_HOURLY_RATES.get(category, DEFAULT_HOURLY_RATES["Services"])
                        sub_steps.append(CostSubStep(
                            name=str(ss.get("name", "")),
                            category=category,
                            hourly_rate=hourly_rate,
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
