"""
Section 1 chain — Background and goals.
  Part A: Company homepage + about page fetched with requests for background info.
  Part B: Goals and constraints extracted from the transcript.
"""
from __future__ import annotations
import logging
import re
import requests
from urllib.parse import quote, urlparse, urljoin
from langchain_core.prompts import PromptTemplate
from backend.ollama_client import get_llm
from backend.chains.extraction_chain import ProjectData

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fi;q=0.8",
}

# Domains that are definitely not the company's own site
_SKIP_DOMAINS = {
    "google.com", "bing.com", "duckduckgo.com", "yahoo.com",
    "linkedin.com", "facebook.com", "twitter.com", "instagram.com",
    "youtube.com", "wikipedia.org", "wikimedia.org",
    "clutch.co", "g2.com", "trustpilot.com", "glassdoor.com",
    "indeed.com", "bloomberg.com", "reuters.com", "forbes.com",
    "crunchbase.com", "zoominfo.com",
}

# Trailing legal-entity suffixes to strip before searching / slug-building
_LEGAL_SUFFIXES = re.compile(
    r"\s+(oyj|oy|ab|a/s|as|ltd\.?|limited|inc\.?|corp\.?|corporation|llc|gmbh|srl|b\.?v\.?|n\.?v\.?|plc|se|kg)\.?\s*$",
    re.IGNORECASE,
)


def _strip_legal_suffix(name: str) -> str:
    """Remove trailing legal-entity suffixes (Oy, Oyj, Ltd, GmbH …) from a company name."""
    return _LEGAL_SUFFIXES.sub("", name).strip()


def _ascii_slug(text: str) -> str:
    """Transliterate common accented / Nordic chars and return a hyphenated URL slug."""
    trans = str.maketrans("äöåüéèêàâ ÄÖÅÜÉÈÊÀÂ", "aoaueeea  AOAUEEEA ")
    text = text.translate(trans)
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _candidate_slugs(company_name: str) -> list[str]:
    """
    Return URL slug candidates derived from *company_name*.
    Tries both the stripped name and original, with hyphenated and compact forms.
    Example: "Patria Oyj" → ["patria", "patria-oyj", "patriaoyj"]
    """
    stripped = _strip_legal_suffix(company_name)
    slugs: list[str] = []
    for name in dict.fromkeys([stripped, company_name]):   # stripped first
        hyphen  = _ascii_slug(name)
        compact = re.sub(r"-", "", hyphen)
        for s in (hyphen, compact):
            if s and s not in slugs:
                slugs.append(s)
    return slugs


def _find_homepage_url(company_name: str) -> str | None:
    """Use DuckDuckGo HTML search to find the company's homepage."""
    stripped = _strip_legal_suffix(company_name)

    # Try multiple query variants in priority order; stop as soon as we get hits
    queries = list(dict.fromkeys([
        f"{stripped} official website",
        f"{company_name} official website",
        f"{stripped} homepage",
        f'"{stripped}"',
    ]))

    urls: list[str] = []
    for query in queries:
        try:
            resp = requests.get(
                f"https://html.duckduckgo.com/html/?q={quote(query)}",
                headers=_HEADERS, timeout=12,
            )
            resp.raise_for_status()
            raw_urls = re.findall(r'uddg=(https?[^&"]+)', resp.text)
            found = [requests.utils.unquote(u) for u in raw_urls]
            if not found:
                found = re.findall(r'class="result__url"[^>]*>\s*(https?://[^\s<"]+)', resp.text)
            urls.extend(found)
        except Exception as e:
            logger.warning("DuckDuckGo query %r failed: %s", query, e)
        if urls:
            break  # found something, no need for further queries

    for url in urls:
        try:
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").removeprefix("www.")
        except Exception:
            continue
        if any(skip in hostname for skip in _SKIP_DOMAINS):
            continue
        return f"{parsed.scheme}://{parsed.netloc}"

    # Fallback: probe common TLD + slug combinations directly
    for slug in _candidate_slugs(company_name):
        for tld in (".fi", ".com", ".eu", ".net", ".io", ".org"):
            candidate = f"https://www.{slug}{tld}"
            try:
                r = requests.head(candidate, headers=_HEADERS, timeout=5, allow_redirects=True)
                if r.status_code < 400:
                    logger.debug("Fallback probe succeeded: %s", candidate)
                    return candidate
            except Exception:
                continue
    return None


def _extract_text_from_html(html: str) -> str:
    """Extract meaningful text by targeting content tags and skipping chrome/boilerplate."""
    # Nuke non-content blocks entirely
    html = re.sub(
        r'<(script|style|nav|header|footer|aside|iframe|noscript|svg|form)[^>]*>.*?</\1>',
        " ", html, flags=re.DOTALL | re.IGNORECASE,
    )
    # Pull text out of content-bearing tags
    chunks = re.findall(
        r'<(?:p|h[1-6]|li|dd|blockquote|section|article|main)[^>]*>(.*?)</(?:p|h[1-6]|li|dd|blockquote|section|article|main)>',
        html, flags=re.DOTALL | re.IGNORECASE,
    )
    lines = []
    for chunk in chunks:
        text = re.sub(r"<[^>]+>", " ", chunk)
        text = re.sub(r"&(?:[a-zA-Z]+|#\d+);", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 40:
            lines.append(text)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result = []
    for line in lines:
        key = line[:80]
        if key not in seen:
            seen.add(key)
            result.append(line)
    return "\n".join(result)


def _find_about_url(homepage: str, html: str) -> str | None:
    """Detect a link to an About / Company page within the homepage HTML."""
    matches = re.findall(
        r'href="([^"#]{1,100}(?:about|yritys|meistä|meista|company|who-we-are|tietoa)[^"]{0,60})"',
        html, flags=re.IGNORECASE,
    )
    for m in matches:
        full = urljoin(homepage, m)
        # Stay on the same domain
        if urlparse(full).netloc == urlparse(homepage).netloc:
            return full
    return None


def _fetch_page(url: str) -> tuple[str, str]:
    """Fetch a page and return (raw_html, extracted_clean_text)."""
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    html = resp.text
    return html, _extract_text_from_html(html)


def _get_company_content(company_name: str) -> str:
    """Find homepage and about page; return combined clean text content."""
    homepage = _find_homepage_url(company_name)
    if not homepage:
        logger.warning("Could not find homepage for %r", company_name)
        return ""
    logger.info("Found homepage: %s", homepage)

    parts: list[str] = []
    try:
        html, text = _fetch_page(homepage)
        if text:
            parts.append(text[:2500])
        logger.debug("Homepage: %d chars extracted", len(text))

        about_url = _find_about_url(homepage, html)
        if about_url:
            try:
                _, about_text = _fetch_page(about_url)
                if about_text:
                    parts.append(about_text[:2500])
                logger.debug("About page (%s): %d chars extracted", about_url, len(about_text))
            except Exception as e:
                logger.warning("About page fetch failed (%s): %s", about_url, e)
    except Exception as e:
        logger.warning("Homepage fetch failed (%s): %s", homepage, e)

    return "\n\n---\n\n".join(parts)


_BACKGROUND_PROMPT = PromptTemplate.from_template(
    """{lang_note}

You are writing the opening paragraph of Section 1 (Background and Goals) of a professional B2B sales offer document.

Using the website content and project information below, produce exactly three sentences in this order:

1. One sentence describing what {company_name} does — focus only on their most important product or service offering. Write in third person, professional and neutral tone.
2. One sentence: "{company_name} (hereinafter referred to as the Client) is developing / planning / researching [1-2 clauses describing the project background and motivation based on the goals below]."
3. One sentence: "Against this background, the Client has requested an offer from LINK Design and Development Oy (hereinafter referred to as the Supplier) for the implementation of {project_name} (hereinafter referred to as the Project)."

Rules:
- Do NOT add headings, bullet points, or any text outside the three sentences.
- Do NOT start with "Based on the website" or "According to the content".
- Do NOT invent facts not present in the content or goals.
- Do NOT include cookie notices, navigation items, or marketing slogans.

Website content:
{search_results}

Project goals: {goals}

Opening paragraph (in the language specified above):"""
)

_GOALS_PROMPT = PromptTemplate.from_template(
    """{lang_note}

You are writing Section 1 (Background and Goals) of a professional B2B sales offer document.

Using the project information below, produce the section in this exact structure:

1. One sentence: "The goal of the Project is [1-2 sentences describing the concrete objective]."
2. A short lead-in sentence: "The following preliminary constraints were discussed between the Client and the Supplier:"
3. A lettered list (a., b., c., …) of the key constraints, one per line.
4. A closing sentence: "The preliminary constraints of the Project are presented in more detail in Appendix 3. The stated constraints will be refined during the phases of the Project."

Rules:
- Write in third person, professional and neutral tone.
- Do NOT add headings or extra commentary outside the structure above.
- Use only the information provided; do not invent facts.

Project name: {other_notes}
Goals: {goals}
Constraints: {constraints}

Section 1 text (in the language specified above):"""
)


def generate_section1(project: ProjectData, enable_web_search: bool = True, language: str = "en", user_prompt: str | None = None) -> dict[str, str]:
    """
    Returns {'company_background': str, 'goals_text': str}
    """
    lang_note = "Write the entire response in Finnish." if language == "fi" else "Write the entire response in English."
    llm = get_llm()
    user_instruction = f"\n\nAdditional instructions: {user_prompt.strip()}" if user_prompt and user_prompt.strip() else ""

    # --- Part A: Company background ---
    company_background = ""
    if enable_web_search and project.company_name:
        try:
            results = _get_company_content(project.company_name)
            if not results:
                raise ValueError("No content retrieved from company website")
            prompt = _BACKGROUND_PROMPT.format(
                lang_note=lang_note,
                company_name=project.company_name,
                project_name=project.project_name or "the Project",
                goals=project.goals or "Not specified",
                search_results=results[:5000],
            ) + user_instruction
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
            lang_note=lang_note,
            goals=project.goals or "Not specified",
            constraints=project.constraints or "Not specified",
            other_notes=project.other_notes or "None",
        ) + user_instruction
        goals_text = llm.invoke(prompt).strip()
    else:
        goals_text = "[Goals and constraints not found in transcript. Please fill in manually.]"

    return {
        "company_background": company_background,
        "goals_text": goals_text,
    }
