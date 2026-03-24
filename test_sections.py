"""
Section test script — tests transcript extraction, company summary, and cost estimation.

Run from project root:
  python test_sections.py --transcript data/documents/transcripts/my_meeting.txt
  python test_sections.py --transcript data/documents/transcripts/my_meeting.txt --company "Patria Oyj"
  python test_sections.py --company "Patria Oyj"          # company summary only
  python test_sections.py --cost                           # cost estimation with dummy data
"""
import argparse
import json
import sys
from pathlib import Path


def _separator(title: str):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_extraction(transcript_path: Path):
    _separator("TEST 1 — Transcript Extraction")
    from backend.chains.extraction_chain import extract_from_transcript, project_data_to_dict
    from backend.ingestion.document_loader import load_file

    docs = load_file(transcript_path)
    full_text = "\n".join(d.page_content for d in docs)
    print(f"Transcript   : {transcript_path.name}")
    print(f"Total chars  : {len(full_text)}")
    print(f"Sending first 8000 chars to LLM…\n")

    # Temporarily patch get_llm to capture raw output
    from backend import ollama_client
    original_get_llm = ollama_client.get_llm
    captured_raw = []

    class CaptureLLM:
        def __init__(self, inner): self._inner = inner
        def __getattr__(self, name): return getattr(self._inner, name)
        def invoke(self, prompt):
            out = self._inner.invoke(prompt)
            captured_raw.append(out)
            return out

    ollama_client.get_llm = lambda model=None: CaptureLLM(original_get_llm(model))
    try:
        result = extract_from_transcript(full_text)
    finally:
        ollama_client.get_llm = original_get_llm

    print("── Raw LLM output ──")
    print(captured_raw[0] if captured_raw else "(not captured)")
    print()
    print("── Parsed fields ──")
    data = project_data_to_dict(result)
    for k, v in data.items():
        if v:
            print(f"  {k:<28} {v}")
    return result


def test_company_summary(company_name: str, language: str = "en"):
    _separator(f"TEST 2 — Company Summary: {company_name}")
    from backend.chains.section1_chain import _get_company_content, _BACKGROUND_PROMPT
    from backend.ollama_client import get_llm

    print(f"Searching homepage for: {company_name}")
    content = _get_company_content(company_name)

    if not content:
        print("ERROR: Could not retrieve company content.")
        return ""

    print(f"\nFetched {len(content)} chars. Sending to LLM…\n")
    lang_note = "Write the entire response in Finnish." if language == "fi" else "Write the entire response in English."
    llm = get_llm()
    prompt = _BACKGROUND_PROMPT.format(
        company_name=company_name,
        search_results=content[:3000],
    ) + f"\n\n{lang_note}"
    summary = llm.invoke(prompt).strip()

    print("── Company Summary ──")
    print(summary)
    return summary


def test_cost_estimation(project_data=None, language: str = "en"):
    _separator("TEST 3 — Cost Estimation (Section 2)")
    from backend.chains.section2_chain import generate_section2
    from backend.chains.extraction_chain import ProjectData

    if project_data is None:
        # Use dummy data for standalone testing
        project_data = ProjectData(
            project_name="Test Software Project",
            goals="Develop a custom CRM integration with ERP system",
            constraints="Must be completed within 6 months, budget up to 150k",
            required_expertise="Backend developer, solution architect, project manager",
            payment_type="hourly",
            material_deliverables="Software, documentation, test reports",
        )
        print("Using dummy project data (no transcript provided).\n")
    else:
        print(f"Using extracted project: {project_data.project_name}\n")

    result = generate_section2(project_data, language=language)

    print("── Description paragraph ──")
    print(result.get("description_text", ""))
    print()
    print("── Cost steps ──")
    steps = result.get("steps", [])
    if steps:
        total = 0.0
        for s in steps:
            cost = getattr(s, "total", 0) if hasattr(s, "total") else (
                s.get("total", 0) if isinstance(s, dict) else 0
            )
            total += cost
            name = getattr(s, "name", "") if not isinstance(s, dict) else s.get("name", "")
            category = getattr(s, "category", "") if not isinstance(s, dict) else s.get("category", "")
            hours = getattr(s, "hours", 0) if not isinstance(s, dict) else s.get("hours", 0)
            rate = getattr(s, "hourly_rate", 0) if not isinstance(s, dict) else s.get("hourly_rate", 0)
            persons = getattr(s, "persons", 1) if not isinstance(s, dict) else s.get("persons", 1)
            print(f"  {name:<40} {category:<15} {hours}h × {rate}€ × {persons}p = {cost:.0f}€")
        print(f"\n  GRAND TOTAL: {result.get('grand_total', total):.0f}€")
    else:
        print("  No steps generated — check LLM output above.")
    return result


def main():
    parser = argparse.ArgumentParser(description="Test AISALES section chains")
    parser.add_argument("--transcript", type=Path, help="Path to transcript file")
    parser.add_argument("--company", type=str, help="Company name for summary test")
    parser.add_argument("--cost", action="store_true", help="Run cost estimation test with dummy data")
    parser.add_argument("--lang", choices=["en", "fi"], default="en", help="Output language")
    args = parser.parse_args()

    if not any([args.transcript, args.company, args.cost]):
        parser.print_help()
        sys.exit(0)

    extracted = None

    if args.transcript:
        if not args.transcript.exists():
            print(f"ERROR: File not found: {args.transcript}")
            sys.exit(1)
        extracted = test_extraction(args.transcript)

    company_name = args.company or (extracted.company_name if extracted else None)
    if company_name:
        test_company_summary(company_name, language=args.lang)

    if args.cost or args.transcript:
        test_cost_estimation(extracted, language=args.lang)

    print()
    print("=" * 70)
    print("  All tests completed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
