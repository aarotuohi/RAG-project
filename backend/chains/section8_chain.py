"""
Section 8 chain — Project team.
Queries the CV database to find the best-fit experts for the project,
then generates a summary for each selected expert.
"""
from __future__ import annotations
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

from backend.ollama_client import get_llm
from backend.vectorstore.chroma_client import get_collection
from backend.config import CHROMA_COLLECTION_CV
from backend.chains.extraction_chain import ProjectData


_RANKING_PROMPT = PromptTemplate.from_template(
    """You are a project staffing expert. Based on the project requirements below,
evaluate the following experts and select the most suitable ones.

PROJECT REQUIREMENTS:
Name: {project_name}
Goals: {goals}
Required expertise: {required_expertise}
Work categories: {categories_needed}
Constraints: {constraints}

AVAILABLE EXPERTS (CV summaries):
{expert_summaries}

Select the 2-4 most suitable experts. For each selected expert return:
- Their name exactly as shown
- Why they are a good fit (1-2 sentences)

Format your response as:
SELECTED EXPERTS:
1. [Expert Name] — [reason]
2. [Expert Name] — [reason]
...

List only experts from the provided summaries. Do not invent people."""
)

_CV_SUMMARY_PROMPT = PromptTemplate.from_template(
    """Write a concise professional CV summary (3-5 sentences) for inclusion in a project offer document.
Focus on the expert's most relevant skills, experience, and qualifications for the described project.

PROJECT: {project_name}
EXPERT CV TEXT:
{cv_text}

Professional CV summary:"""
)


def _retrieve_candidate_cvs(query: str, k: int = 8) -> list[Document]:
    try:
        collection = get_collection(CHROMA_COLLECTION_CV)
        docs = collection.similarity_search(query, k=k)
        return docs
    except Exception:
        return []


def _extract_selected_names(ranking_text: str, candidate_docs: list[Document]) -> list[str]:
    """Parse the LLM ranking response to get selected expert names."""
    selected = []
    for line in ranking_text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Match "1. Name — reason" or "- Name — reason"
        m = None
        import re
        m = re.match(r"^[\d\-\*\.]+\s+(.+?)\s*[—\-\–]", line)
        if m:
            name = m.group(1).strip()
            if name:
                selected.append(name)
    return selected


def generate_section8(project: ProjectData) -> dict:
    """
    Returns:
      {
        'intro_text': str,
        'experts': [{'name': str, 'reason': str, 'cv_summary': str, 'full_cv': str}]
      }
    """
    llm = get_llm()

    query = f"{project.project_name} {project.goals} {project.required_expertise} {project.constraints}"
    candidate_docs = _retrieve_candidate_cvs(query)

    if not candidate_docs:
        return {
            "intro_text": "Project team will be confirmed upon contract signing.",
            "experts": [],
        }

    # Build a numbered list of candidate summaries for the ranking prompt
    expert_summaries = ""
    for i, doc in enumerate(candidate_docs):
        name = doc.metadata.get("person_name", f"Expert {i+1}")
        excerpt = doc.page_content[:600]
        expert_summaries += f"\n--- Expert {i+1}: {name} ---\n{excerpt}\n"

    ranking_prompt = _RANKING_PROMPT.format(
        project_name=project.project_name or "New Project",
        goals=project.goals or "Not specified",
        required_expertise=project.required_expertise or "Not specified",
        categories_needed=project.required_expertise or "General",
        constraints=project.constraints or "None",
        expert_summaries=expert_summaries[:5000],
    )
    ranking_response = llm.invoke(ranking_prompt)
    selected_names = _extract_selected_names(ranking_response, candidate_docs)

    # Match selected names to candidate docs
    experts = []
    for name in selected_names:
        matched_doc = next(
            (d for d in candidate_docs if name.lower() in d.metadata.get("person_name", "").lower()),
            None,
        )
        if not matched_doc:
            continue

        # Generate a polished CV summary for the offer document
        cv_prompt = _CV_SUMMARY_PROMPT.format(
            project_name=project.project_name or "Project",
            cv_text=matched_doc.page_content[:2000],
        )
        cv_summary = llm.invoke(cv_prompt).strip()

        # Extract reason from the ranking response
        import re
        reason_match = re.search(
            rf"{re.escape(name)}\s*[—\-\–]\s*(.+)", ranking_response
        )
        reason = reason_match.group(1).strip() if reason_match else ""

        experts.append({
            "name": matched_doc.metadata.get("person_name", name),
            "reason": reason,
            "cv_summary": cv_summary,
            "full_cv": matched_doc.page_content,
        })

    intro_text = (
        f"The following experts have been selected for the {project.project_name or 'project'} "
        f"based on their skills and experience relevant to the project requirements."
    )

    return {
        "intro_text": intro_text,
        "experts": experts,
    }
