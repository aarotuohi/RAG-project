"""
Model Benchmark — tests different Ollama LLMs on the three core AISALES tasks:

  1. EXTRACTION  — parse a transcript into structured JSON fields
  2. COST JSON   — produce a valid JSON cost estimation array
  3. RAG SECTION — generate a section using retrieved ChromaDB context

Run from project root:
    python benchmark_models.py
    python benchmark_models.py --models qwen2.5:7b qwen2.5:14b
    python benchmark_models.py --tests 1 2        # skip RAG test

Requires:
  - Ollama running with the models already pulled
  - nomic-embed-text pulled (for TEST 3 RAG)
  - At least one file indexed in cost_history collection (for TEST 3)

Output: a summary table + results saved to data/outputs/benchmark_results.json
"""
from __future__ import annotations
import argparse
import json
import time
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description="AISALES model benchmark")
parser.add_argument(
    "--models", nargs="+",
    default=["qwen2.5:7b", "qwen2.5:14b", "mistral:7b", "llama3.2:3b"],
    help="Ollama model names to benchmark",
)
parser.add_argument(
    "--tests", nargs="+", type=int, choices=[1, 2, 3], default=[1, 2, 3],
    metavar="N",
    help="Which tests to run (1=Extraction, 2=Cost JSON, 3=RAG Section). Default: all.",
)
args = parser.parse_args()
MODELS = args.models
RUN    = set(args.tests)

SEP = "=" * 70

# ── Sample transcript (short version for speed) ───────────────────────────────
SAMPLE_TRANSCRIPT = """
Meeting: Military Communication Helmet Project
Date: 2026-02-20
Participants: John Andersson (Patria Oyj), Alex Carter (Tech Solutions Ltd)

John: We need a military helmet with built-in communication hardware.
Alex: What is the expected timeline?
John: We want to start in April 2026 and finish by December 2026.
Alex: And the budget model — hourly or fixed price?
John: Fixed price preferred. The main deliverables are hardware prototype,
      software firmware, and technical documentation.
Alex: We will need electronics engineers and software developers.
John: Yes, and the project is for Patria Oyj, Lentokonetehtaantie 3, 01530 Vantaa.
      My name is John Andersson.
Alex Carter is the salesperson from our side.
"""

# ── Expected extraction fields (used for scoring) ────────────────────────────
EXPECTED_EXTRACTION = {
    "company_name": "patria",          # lowercase for fuzzy match
    "project_name": "helmet",
    "payment_type": "fixed",
    "first_name":   "john",
    "salesperson_name": "alex",
}

# ── Cost JSON prompt (same as section2_chain) ─────────────────────────────────
COST_PROMPT = """You are a project cost estimation expert.
Return ONLY a JSON array — no explanation, no markdown:
[
  {
    "step_id": "STEP 1",
    "name": "Electronics design",
    "category": "Electronics",
    "hourly_rate": 95,
    "hours": 120,
    "persons": 2
  }
]

Project: Military Communication Helmet
Goals: Build helmet with integrated communication hardware and firmware.
Required expertise: Electronics engineer, software developer.
Payment type: fixed

Return ONLY the JSON array."""

# ── Imports ───────────────────────────────────────────────────────────────────
try:
    import backend.config as cfg
    from langchain_ollama import OllamaLLM
    from langchain_core.prompts import PromptTemplate
except ImportError as e:
    sys.exit(f"[ERROR] {e}\nRun from project root with dependencies installed.")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_llm(model: str) -> OllamaLLM:
    return OllamaLLM(model=model, base_url=cfg.OLLAMA_BASE_URL, temperature=0.2)


def _clean_json(text: str) -> str:
    import re
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    return text.strip()


def _check_model_available(model: str) -> bool:
    import requests
    try:
        r = requests.get(f"{cfg.OLLAMA_BASE_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        # Match by prefix (ignore quantization suffix)
        base = model.split(":")[0]
        return any(base in m for m in models)
    except Exception:
        return False


def _score_extraction(result: dict) -> tuple[int, int]:
    """Return (fields_correct, fields_total) based on EXPECTED_EXTRACTION."""
    correct = 0
    for field, expected in EXPECTED_EXTRACTION.items():
        value = str(result.get(field, "")).lower()
        if expected.lower() in value:
            correct += 1
    return correct, len(EXPECTED_EXTRACTION)


def _score_cost_json(raw: str) -> tuple[bool, int, list]:
    """Return (valid_json, step_count, steps)."""
    try:
        data = json.loads(_clean_json(raw))
        if not isinstance(data, list):
            return False, 0, []
        required_keys = {"step_id", "name", "hourly_rate", "hours", "persons"}
        valid_steps = [s for s in data if required_keys.issubset(s.keys())]
        return True, len(valid_steps), valid_steps
    except json.JSONDecodeError:
        return False, 0, []


# ── Results storage ───────────────────────────────────────────────────────────
results: list[dict] = []


# ── Run benchmarks ─────────────────────────────────────────────────────────────
print(SEP)
print("AISALES — Model Benchmark")
print(SEP)
print(f"  Models : {MODELS}")
print(f"  Tests  : {sorted(RUN)}")
print()

for model in MODELS:
    print(f"\n{'─'*70}")
    print(f"  MODEL: {model}")
    print(f"{'─'*70}")

    if not _check_model_available(model):
        print(f"  [SKIP] Model '{model}' not found in Ollama. Pull it first:")
        print(f"         ollama pull {model}")
        results.append({"model": model, "available": False})
        continue

    llm = _get_llm(model)
    model_result: dict = {"model": model, "available": True, "tests": {}}

    # ── TEST 1: Extraction ────────────────────────────────────────────────────
    if 1 in RUN:
        print("\n  TEST 1 — Extraction (transcript → structured JSON)")
        extraction_prompt = f"""Extract the following fields from this transcript as JSON.
Use empty string for missing fields.
Fields: first_name, last_name, company_name, project_name, salesperson_name,
        project_start, project_end, payment_type, goals, required_expertise

TRANSCRIPT:
{SAMPLE_TRANSCRIPT}

Return ONLY a JSON object."""

        t0 = time.perf_counter()
        try:
            raw = llm.invoke(extraction_prompt)
            elapsed = time.perf_counter() - t0
            data = json.loads(_clean_json(raw))
            correct, total = _score_extraction(data)
            status = "PASS" if correct >= 4 else "PARTIAL" if correct >= 2 else "FAIL"
            print(f"    Time     : {elapsed:.1f}s")
            print(f"    Score    : {correct}/{total} fields correct  [{status}]")
            print(f"    company  : {data.get('company_name', '—')}")
            print(f"    project  : {data.get('project_name', '—')}")
            print(f"    payment  : {data.get('payment_type', '—')}")
            model_result["tests"]["extraction"] = {
                "time_s": round(elapsed, 2),
                "score": f"{correct}/{total}",
                "status": status,
                "fields": data,
            }
        except json.JSONDecodeError:
            elapsed = time.perf_counter() - t0
            print(f"    [FAIL] JSON parse error after {elapsed:.1f}s")
            print(f"    Raw output: {raw[:200]!r}")
            model_result["tests"]["extraction"] = {"time_s": round(elapsed, 2), "status": "FAIL", "error": "json_decode"}
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"    [ERROR] {e}")
            model_result["tests"]["extraction"] = {"time_s": round(elapsed, 2), "status": "ERROR", "error": str(e)}

    # ── TEST 2: Cost JSON ─────────────────────────────────────────────────────
    if 2 in RUN:
        print("\n  TEST 2 — Cost JSON (structured cost estimation)")
        t0 = time.perf_counter()
        try:
            raw = llm.invoke(COST_PROMPT)
            elapsed = time.perf_counter() - t0
            valid, step_count, steps = _score_cost_json(raw)
            status = "PASS" if valid and step_count >= 1 else "FAIL"
            grand_total = round(sum(
                float(s.get("hourly_rate", 0)) * float(s.get("hours", 0)) * int(s.get("persons", 1))
                for s in steps
            ), 2) if steps else 0
            print(f"    Time       : {elapsed:.1f}s")
            print(f"    Valid JSON  : {valid}")
            print(f"    Steps      : {step_count}  [{status}]")
            print(f"    Grand total: {grand_total:,.2f} €")
            model_result["tests"]["cost_json"] = {
                "time_s": round(elapsed, 2),
                "valid_json": valid,
                "step_count": step_count,
                "grand_total": grand_total,
                "status": status,
            }
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"    [ERROR] {e}")
            model_result["tests"]["cost_json"] = {"time_s": round(elapsed, 2), "status": "ERROR", "error": str(e)}

    # ── TEST 3: RAG + section generation ─────────────────────────────────────
    if 3 in RUN:
        print("\n  TEST 3 — RAG Section (ChromaDB retrieval + LLM generation)")
        try:
            from backend.vectorstore.chroma_client import get_collection
            from backend.config import CHROMA_COLLECTION_COST
            collection = get_collection(CHROMA_COLLECTION_COST)
            count = collection._collection.count()
            if count == 0:
                print("    [SKIP] cost_history collection is empty — ingest Excel files first.")
                model_result["tests"]["rag_section"] = {"status": "SKIP", "reason": "empty_collection"}
            else:
                query = "military electronics hardware firmware development hours"
                retrieved = collection.similarity_search(query, k=3)
                context = "\n\n".join(d.page_content for d in retrieved)
                rag_prompt = f"""You are a cost estimation expert. Based on this historical data:

{context[:3000]}

Write a 2-3 sentence professional description of the implementation approach for:
Project: Military Communication Helmet
Goals: Build helmet with integrated communication hardware and firmware.
Payment: fixed price

Implementation paragraph:"""
                t0 = time.perf_counter()
                raw = llm.invoke(rag_prompt)
                elapsed = time.perf_counter() - t0
                word_count = len(raw.split())
                status = "PASS" if word_count >= 20 else "FAIL"
                print(f"    Time       : {elapsed:.1f}s")
                print(f"    Chunks used: {len(retrieved)} from {count} total")
                print(f"    Word count : {word_count}  [{status}]")
                print(f"    Preview    : {raw[:200].strip()!r}")
                model_result["tests"]["rag_section"] = {
                    "time_s": round(elapsed, 2),
                    "chunks_retrieved": len(retrieved),
                    "word_count": word_count,
                    "status": status,
                    "preview": raw[:200].strip(),
                }
        except Exception as e:
            print(f"    [ERROR] {e}")
            model_result["tests"]["rag_section"] = {"status": "ERROR", "error": str(e)}

    results.append(model_result)


# ── Summary table ─────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("SUMMARY")
print(SEP)

header = f"{'Model':<35} {'Available':<10}"
if 1 in RUN: header += f" {'Extraction':<14} {'Time':<8}"
if 2 in RUN: header += f" {'Cost JSON':<12} {'Time':<8}"
if 3 in RUN: header += f" {'RAG':<10} {'Time':<8}"
print(header)
print("─" * len(header))

for r in results:
    row = f"{r['model']:<35} {'YES' if r['available'] else 'NOT FOUND':<10}"
    if not r.get("available"):
        print(row)
        continue
    tests = r.get("tests", {})
    if 1 in RUN:
        t1 = tests.get("extraction", {})
        row += f" {t1.get('status','—'):<14} {str(t1.get('time_s','—'))+'s':<8}"
    if 2 in RUN:
        t2 = tests.get("cost_json", {})
        row += f" {t2.get('status','—'):<12} {str(t2.get('time_s','—'))+'s':<8}"
    if 3 in RUN:
        t3 = tests.get("rag_section", {})
        row += f" {t3.get('status','—'):<10} {str(t3.get('time_s','—'))+'s':<8}"
    print(row)

# ── Save results ──────────────────────────────────────────────────────────────
out = Path("data/outputs/benchmark_results.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nFull results saved to: {out}")
print(SEP)
