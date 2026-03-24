"""
Section 8 chain — Project team.
Queries the CV database to find the best-fit experts for the project.
No LLM summaries — only name, title, and role description from CV files.
"""
from __future__ import annotations
import re
from langchain_core.documents import Document

from backend.ollama_client import get_llm
from backend.vectorstore.chroma_client import get_collection
from backend.config import CHROMA_COLLECTION_CV
from backend.chains.extraction_chain import ProjectData
from langchain_core.prompts import PromptTemplate


_RANKING_PROMPT = PromptTemplate.from_template(
    """You are a project staffing expert. Based on the project requirements below,
evaluate the following experts and select the most suitable ones.

PROJECT REQUIREMENTS:
Name: {project_name}
Goals: {goals}
Required expertise: {required_expertise}
Work categories: {categories_needed}
Constraints: {constraints}

AVAILABLE EXPERTS:
{expert_summaries}

Select the 2-4 most suitable experts. For each selected expert return ONLY:
- Their name exactly as shown
- What they will do on this specific project (1 sentence, based on their title/skills)

Format your response as:
SELECTED EXPERTS:
1. [Expert Name] — [what they will do on the project]
2. [Expert Name] — [what they will do on the project]
...

List only experts from the provided summaries. Do not invent people."""
)


def _retrieve_candidate_cvs(query: str, k: int = 8) -> list[Document]:
    try:
        collection = get_collection(CHROMA_COLLECTION_CV)
        docs = collection.similarity_search(query, k=k)
        return docs
    except Exception:
        return []


def _parse_field(text: str, *labels: str) -> str:
    """Extract a field value from CV text by looking for label: value lines."""
    for label in labels:
        m = re.search(rf"(?:{label})\s*[:\-]\s*(.+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _extract_selected(ranking_text: str) -> list[tuple[str, str]]:
    """
    Parse ranking response into list of (name, role_description) tuples.
    """
    results = []
    for line in ranking_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^[\d\-\*\.]+\s+(.+?)\s*[—\-\–]\s*(.+)", line)
        if m:
            name = m.group(1).strip()
            role = m.group(2).strip()
            if name:
                results.append((name, role))
    return results


def generate_section8(project: ProjectData, language: str = "en") -> dict:
    """
    Returns:
      {
        'intro_text': str,
        'experts': [{'name': str, 'title': str, 'role': str}]
      }
    No LLM summaries. Name and title come directly from CV files.
    Role description is determined by the ranking LLM (one sentence).
    """
    llm = get_llm()

    query = (
        f"{project.project_name} {project.goals} {project.required_expertise} "
        f"{project.constraints} {project.material_deliverables}"
    )
    candidate_docs = _retrieve_candidate_cvs(query)

    if not candidate_docs:
        return {
            "intro_text": (
                "Projektitiimi vahvistetaan sopimuksen allekirjoittamisen jälkeen."
                if language == "fi"
                else "Project team will be confirmed upon contract signing."
            ),
            "experts": [],
        }

    # Build candidate list for ranking prompt — name + title + skills only
    expert_summaries = ""
    for i, doc in enumerate(candidate_docs):
        name  = doc.metadata.get("person_name", f"Expert {i+1}")
        title = (
            doc.metadata.get("title")
            or _parse_field(doc.page_content, "Title", "Titteli", "Nimike", "Position", "Role")
            or "—"
        )
        skills = (
            doc.metadata.get("skills")
            or _parse_field(doc.page_content, "Skills", "Taidot", "Expertise", "Technologies")
            or doc.page_content[:200]
        )
        expert_summaries += f"\n{i+1}. {name} | Title: {title} | Skills: {skills}\n"

    lang_note = "Write the entire response in Finnish." if language == "fi" else "Write the entire response in English."
    ranking_prompt = _RANKING_PROMPT.format(
        project_name=project.project_name or "New Project",
        goals=project.goals or "Not specified",
        required_expertise=project.required_expertise or "Not specified",
        categories_needed=project.required_expertise or "General",
        constraints=project.constraints or "None",
        expert_summaries=expert_summaries[:5000],
    ) + f"\n\n{lang_note}"
    ranking_response = llm.invoke(ranking_prompt)
    selected = _extract_selected(ranking_response)

    experts = []
    for name, role in selected:
        matched_doc = next(
            (d for d in candidate_docs
             if name.lower() in d.metadata.get("person_name", "").lower()),
            None,
        )
        if not matched_doc:
            continue

        # Pull title from metadata first, then parse from CV text
        title = (
            matched_doc.metadata.get("title")
            or _parse_field(matched_doc.page_content, "Title", "Titteli", "Nimike", "Position", "Role")
            or "—"
        )
        full_name = matched_doc.metadata.get("person_name", name)

        experts.append({
            "name":  full_name,
            "title": title,
            "role":  role,   # one sentence: what they will do on THIS project
        })

    if language == "fi":
        intro_text = "Ehdotamme seuraavia asiantuntijoita projektille:"
    else:
        intro_text = "We suggest the following experts for the project:"

    return {
        "intro_text": intro_text,
        "experts": experts,
}