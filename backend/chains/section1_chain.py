"""
Section 1 chain — Background and goals.
  Part A: Company homepage fetched with requests for background info.
  Part B: Goals and constraints extracted from the transcript.
"""
from __future__ import annotations
import re
import requests
from langchain_core.prompts import PromptTemplate
from backend.ollama_client import get_llm
from backend.chains.extraction_chain import ProjectData


def _find_homepage_url(company_name: str) -> str | None:
    """Use Bing to find the company's homepage URL."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
        ),
        "Accept-Language": "en-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    query = requests.utils.quote(f"{company_name} official website")
    resp = requests.get(
        f"https://www.bing.com/search?q={query}&count=5",
        headers=headers, timeout=10,
    )
    resp.raise_for_status()
    patterns = [
        r'<cite[^>]*>(https?://[^<\s]+)</cite>',
        r'<cite[^>]*>([^<\s]+)</cite>',
        r'"url"\s*:\s*"(https?://(?!(?:www\.)?bing\.com|(?:www\.)?microsoft\.com)[^"]+)"',
        r'href="(https?://(?!(?:www\.)?bing\.com|(?:www\.)?microsoft\.com)[^"&]+)"',
    ]
    urls = []
    for pattern in patterns:
        found = re.findall(pattern, resp.text)
        if found:
            urls = found
            break

    for url in urls:
        clean = url.rstrip("/")
        if clean.count("/") <= 3:
            return clean
    return urls[0] if urls else None


def _fetch_page_text(url: str) -> str:
    """Fetch a URL with requests and strip HTML tags to get plain text."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    html = resp.text
    # Remove scripts, styles, and tags
    html = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = re.sub(r'&[a-zA-Z]+;', ' ', html)
    text = re.sub(r'\s+', ' ', html).strip()
    return text


def _get_company_content(company_name: str) -> str:
    """Find the company's homepage and fetch its text content."""
    homepage = _find_homepage_url(company_name)
    if not homepage:
        slug = re.sub(r'[^a-z0-9]', '', company_name.lower().split()[0])
        homepage = f"https://www.{slug}.com"
        print(f"[section1] Bing found no URL, trying fallback: {homepage}")
    else:
        print(f"[section1] Found homepage: {homepage}")
    try:
        content = _fetch_page_text(homepage)
        print(f"[section1] Fetched {len(content)} chars from {homepage}")
        return content[:4000].strip()
    except Exception as e:
        print(f"[section1] Fetch failed for {homepage}: {e}")
        return ""



_BACKGROUND_PROMPT = PromptTemplate.from_template(
    """Based on the following content from {company_name}'s website, 
write a concise 2-3 sentence background description of what the company does and their main business area.
Write in a professional, neutral tone suitable for a sales offer document.

Website content:
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


def generate_section1(project: ProjectData, enable_web_search: bool = True, language: str = "en") -> dict[str, str]:
    """
    Returns {'company_background': str, 'goals_text': str}
    """
    lang_note = "Write the entire response in Finnish." if language == "fi" else "Write the entire response in English."
    llm = get_llm()

    # --- Part A: Company background from crawl4ai ---
    company_background = ""
    if enable_web_search and project.company_name:
        try:
            results = _get_company_content(project.company_name)
            if not results:
                raise ValueError("No content retrieved from company website")
            prompt = _BACKGROUND_PROMPT.format(
                company_name=project.company_name,
                search_results=results[:3000],
            ) + f"\n\n{lang_note}"
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
        ) + f"\n\n{lang_note}"
        goals_text = llm.invoke(prompt).strip()
    else:
        goals_text = "[Goals and constraints not found in transcript. Please fill in manually.]"

    return {
        "company_background": company_background,
        "goals_text": goals_text,
    }
