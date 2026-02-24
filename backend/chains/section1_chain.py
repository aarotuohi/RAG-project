"""
Section 1 chain — Background and goals.
  Part A: Bing web search summary of the company (same engine as Edge, no logging).
  Part B: Goals and constraints extracted from the transcript.
"""
from __future__ import annotations
import requests
from bs4 import BeautifulSoup
from langchain_core.prompts import PromptTemplate
from backend.ollama_client import get_llm
from backend.chains.extraction_chain import ProjectData


def _bing_search(query: str, num_results: int = 5) -> str:
    """Scrape Bing search result snippets — same results Edge would show."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Language": "en-FI,fi;q=0.9"
    }
    url = f"https://www.bing.com/search?q={requests.utils.quote(query)}&count={num_results}"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    snippets = []
    for result in soup.select(".b_algo")[:num_results]:
        title_el = result.select_one("h2")
        caption_el = result.select_one(".b_caption p")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        caption = caption_el.get_text(" ", strip=True) if caption_el else ""
        if title or caption:
            snippets.append(f"{title}\n{caption}".strip())
    return "\n\n".join(snippets) if snippets else ""

_BACKGROUND_PROMPT = PromptTemplate.from_template(
    """Based on the following web search results about the company "{company_name}", 
write a concise 2-3 sentence background description of what the company does and their main business area.
Write in a professional, neutral tone suitable for a sales offer document.

Search results:
{search_results}

Background description:"""
)

_GOALS_PROMPT = PromptTemplate.from_template(
    """Based on the following project information extracted from a sales meeting, 
write a structured paragraph describing the project goals, objectives, and constraints.
Keep it professional and concise (3-5 sentences).

Goals: {goals}
Constraints: {constraints}
Other notes: {other_notes}

Project goals and constraints paragraph:"""
)


def generate_section1(project: ProjectData, enable_web_search: bool = True) -> dict[str, str]:
    """
    Returns {'company_background': str, 'goals_text': str}
    """
    llm = get_llm()

    # --- Part A: Company background from Bing (Edge engine) ---
    company_background = ""
    if enable_web_search and project.company_name:
        try:
            results = _bing_search(f"{project.company_name} company what they do business")
            if not results:
                raise ValueError("No search results returned")
            prompt = _BACKGROUND_PROMPT.format(
                company_name=project.company_name,
                search_results=results[:3000],
            )
            company_background = llm.invoke(prompt).strip()
        except Exception as e:
            company_background = (
                f"[Company background for {project.company_name} could not be retrieved: {e}. "
                "Please fill in manually.]"
            )
    elif project.company_name:
        company_background = (
            f"[Web search disabled. Please add background information for "
            f"{project.company_name} manually.]"
        )

    # --- Part B: Goals from transcript ---
    goals_text = ""
    if project.goals or project.constraints:
        prompt = _GOALS_PROMPT.format(
            goals=project.goals or "Not specified",
            constraints=project.constraints or "Not specified",
            other_notes=project.other_notes or "None",
        )
        goals_text = llm.invoke(prompt).strip()
    else:
        goals_text = "[Goals and constraints not found in transcript. Please fill in manually.]"

    return {
        "company_background": company_background,
        "goals_text": goals_text,
    }
