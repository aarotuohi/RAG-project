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
2. Identify which historical steps are most similar to what the new project needs.
3. Use the EXACT hourly rates (Rate: X€/h) from the historical data for matching work types — do NOT invent rates.
4. Scale hours up or down based on project complexity compared to historical examples.
5. Add any steps the new project needs that don't appear in history, using the standard rates below.
6. For EVERY sub-step, use EXACTLY the standard hourly rate listed below — do NOT use any other rate.

Work categories and STANDARD hourly rates (€/h):
{categories}

CRITICAL: You MUST use the nested "sub_steps" array. Do NOT place hourly_rate/hours/persons \
directly on the step object — only inside sub_steps items.

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
        "hourly_rate": <exact number from historical data>,
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


def _retrieve_similar_projects(description: str, k: int = 20) -> str:
    """
    Retrieve the most relevant historical cost chunks from ChromaDB.

    Fetches k chunks, then groups every chunk that came from the same source
    file so the LLM sees each historical project as a coherent whole
    (all relevant phases together) rather than isolated rows.
    Returns at most 4 distinct projects to stay within the prompt context budget.
    """
    try:
        collection = get_collection(CHROMA_COLLECTION_COST)
        docs = collection.similarity_search(description, k=k)

        if not docs:
            return "No historical data available."

        # Group chunks by source file, preserving retrieval-score order
        # (similarity_search returns best matches first).
        from collections import OrderedDict
        project_chunks: OrderedDict[str, list[str]] = OrderedDict()
        for d in docs:
            src = d.metadata.get("source", "unknown")
            project_chunks.setdefault(src, [])
            # Avoid duplicate content (same chunk retrieved twice)
            if d.page_content not in project_chunks[src]:
                project_chunks[src].append(d.page_content)

        sections = []
        for i, (src, chunks) in enumerate(project_chunks.items(), 1):
            if i > 4:          # cap at 4 projects to keep prompt size manageable
                break
            src_name = src.replace("\\", "/").split("/")[-1]
            combined = "\n\n".join(chunks)
            sections.append(f"--- Historical project {i}: {src_name} ---\n{combined}")

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
