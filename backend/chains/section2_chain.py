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
from backend.config import CHROMA_COLLECTION_COST, WORK_CATEGORIES
from backend.chains.extraction_chain import ProjectData
from backend.ingestion.excel_parser import CostStep


_ESTIMATION_PROMPT = PromptTemplate.from_template(
    """You are a project estimation expert. Based on the new project description and 
historical project data below, create a detailed cost estimate.

NEW PROJECT:
Name: {project_name}
Description: {description}
Goals: {goals}
Required expertise: {required_expertise}
Payment type: {payment_type}

SIMILAR HISTORICAL PROJECTS (for reference — use these to calibrate hours):
{historical_data}

Work categories available: {categories}

Create a step-by-step cost estimate. Return ONLY a JSON array of objects with this structure:
[
  {{
    "step_id": "STEP 1",
    "name": "step description",
    "category": "one of the work categories",
    "hourly_rate": <number>,
    "hours": <number>,
    "persons": <integer>
  }},
  ...
]

Rules:
- hourly_rate should be realistic (typically 85-150 €/h based on category)
- hours and persons must be positive numbers
- Include at least one step per relevant work category
- Do NOT include a totals row — only individual steps
- Return ONLY the JSON array, no explanation."""
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


def _retrieve_similar_projects(description: str, k: int = 5) -> str:
    try:
        collection = get_collection(CHROMA_COLLECTION_COST)
        docs = collection.similarity_search(description, k=k)
        return "\n\n".join(d.page_content for d in docs)
    except Exception:
        return "No historical data available."


def generate_section2(project: ProjectData, language: str = "en") -> dict:
    """
    Returns:
      {
        'description_text': str,
        'steps': [CostStep, ...],
        'grand_total': float,
        'payment_type': str,
      }
    """
    lang_note = "Write the entire response in Finnish." if language == "fi" else "Write the entire response in English."
    llm = get_llm()

    description_query = f"{project.project_name} {project.goals} {project.required_expertise}"
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
        historical_data=historical_data[:4000],
        categories=", ".join(WORK_CATEGORIES),
    )
    raw = llm.invoke(est_prompt)
    cleaned = _clean_json(raw)

    steps: list[CostStep] = []
    try:
        step_list = json.loads(cleaned)
        for s in step_list:
            try:
                cs = CostStep(
                    step_id=str(s.get("step_id", f"STEP {len(steps)+1}")),
                    name=str(s.get("name", "")),
                    category=str(s.get("category", "Services")),
                    hourly_rate=float(s.get("hourly_rate", 0)),
                    hours=float(s.get("hours", 0)),
                    persons=int(s.get("persons", 1)),
                )
                steps.append(cs)
            except Exception:
                continue
    except json.JSONDecodeError:
        pass

    # Grand total computed purely in Python — LLM never touches the math
    grand_total = round(sum(s.total for s in steps), 2)

    return {
        "description_text": description_text,
        "steps": steps,
        "grand_total": grand_total,
        "payment_type": project.payment_type or "hourly",
    }
