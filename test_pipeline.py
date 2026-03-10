"""
Full pipeline test: Parse → Chunk → Embed → Store → Query
Tests .txt, .docx, and .xlsx file types separately.

Run from project root:
    python test_pipeline.py              # all tests
    python test_pipeline.py --tests 1 3  # only TXT + XLSX (skips slow Docling)
    python test_pipeline.py --tests 2    # only DOCX (Docling must be working)

Requires:
  - Ollama running with nomic-embed-text pulled
  - docling installed (for .docx / TEST 2)
  - pandas + openpyxl installed (for .xlsx / TEST 3)

NOTE: TEST 2 imports Docling which pulls in PyTorch/transformers.
      This can take 1-3 minutes on first run. If it hangs, press Ctrl+C
      and re-run with --tests 1 3 to skip it.
"""
import sys
import argparse
import textwrap
from pathlib import Path

parser = argparse.ArgumentParser(description="AISALES pipeline test")
parser.add_argument(
    "--tests", nargs="+", type=int, choices=[1, 2, 3], default=[1, 2, 3],
    metavar="N",
    help="Which tests to run (1=TXT, 2=DOCX/Docling, 3=XLSX). Default: all.",
)
args = parser.parse_args()
RUN = set(args.tests)

# ─────────────────────────────────────────────────────────────────────────────
# File paths
# ─────────────────────────────────────────────────────────────────────────────
TXT_FILE  = Path("transcript_example.txt")
DOCX_FILE = Path("data/raw/offers/offer_Military_Communication_Helmet_Project_2026-02-23.docx")
XLSX_FILE = Path("data/raw/offer_calculations/laskentapohja.xlsx")

# Temporary test collections — cleaned up at the end
TEST_COLLECTION_TXT  = "test_txt_pipeline"
TEST_COLLECTION_DOCX = "test_docx_pipeline"
TEST_COLLECTION_XLSX = "test_xlsx_pipeline"

SEP = "=" * 70


def _truncate(text: str, width: int = 180) -> str:
    return textwrap.shorten(text.strip(), width=width, placeholder=" ...")


def _print_chunks(docs, max_show: int = 5):
    for i, d in enumerate(docs[:max_show]):
        heading = d.metadata.get("heading", "")
        sheet   = d.metadata.get("sheet", "")
        tag     = f"heading={heading!r}" if heading else (f"sheet={sheet!r}" if sheet else "")
        pre     = "pre-chunked" if d.metadata.get("pre_chunked") else "splitter"
        print(f"  Chunk {i+1:02d}  [{pre}]  {len(d.page_content):4d} chars  {tag}")
        print(f"           {_truncate(d.page_content, 130)!r}")
    if len(docs) > max_show:
        print(f"  ... ({len(docs) - max_show} more chunks not shown)")
    print()


def _similarity_search(collection, queries):
    for q in queries:
        results = collection.similarity_search(q, k=2)
        print(f"\n  Query: {q!r}")
        for j, r in enumerate(results):
            print(f"    Result {j+1}: {_truncate(r.page_content, 160)!r}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Imports
# ─────────────────────────────────────────────────────────────────────────────
try:
    from backend.ingestion.document_loader import load_file, index_file
    from backend.vectorstore.chroma_client import get_collection, delete_collection, collection_count
    from backend.config import CHUNK_SIZE, CHUNK_OVERLAP
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError as exc:
    sys.exit(
        f"[ERROR] Could not import backend modules: {exc}\n"
        "Make sure you run from the project root and the virtualenv is active."
    )

print(SEP)
print("AISALES -- Pipeline Test  (Parse -> Chunk -> Embed -> Store -> Query)")
print(SEP)
print(f"  Running tests : {sorted(RUN)}")
print(f"  CHUNK_SIZE    : {CHUNK_SIZE}")
print(f"  CHUNK_OVERLAP : {CHUNK_OVERLAP}")
print()


# ===========================================================================
# TEST 1 -- Plain-text (.txt)
# ===========================================================================
if 1 not in RUN:
    print(f"{SEP}\nTEST 1 -- [SKIPPED]\n")
else:
    print(SEP)
    print("TEST 1 -- Plain-text (.txt)  --  transcript_example.txt")
    print(SEP)

    if not TXT_FILE.exists():
        print(f"[SKIP] {TXT_FILE} not found.\n")
    else:
        # 1a. Parse
        print("Step 1a: Parsing ...")
        raw_docs = load_file(TXT_FILE)
        print(f"  Raw documents loaded : {len(raw_docs)}")
        print(f"  Total characters     : {sum(len(d.page_content) for d in raw_docs)}")
        print()

        # 1b. Chunk
        print("Step 1b: Chunking (RecursiveCharacterTextSplitter) ...")
        splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        chunks = splitter.split_documents(raw_docs)
        print(f"  Chunks produced : {len(chunks)}")
        _print_chunks(chunks)

        # 1c. Embed + Store
        print("Step 1c: Embedding & Storing (Ollama -> ChromaDB) ...")
        delete_collection(TEST_COLLECTION_TXT)
        added  = index_file(TXT_FILE, TEST_COLLECTION_TXT)
        stored = collection_count(TEST_COLLECTION_TXT)
        print(f"  Chunks added : {added}")
        print(f"  Chunks in DB : {stored}")
        print(f"  Status       : {'PASS' if added > 0 and stored == added else 'FAIL'}")
        print()

        # 1d. Similarity search
        print("Step 1d: Similarity Search ...")
        _similarity_search(get_collection(TEST_COLLECTION_TXT), [
            "project goals and requirements",
            "delivery schedule and timeline",
            "pricing and costs",
        ])


# ===========================================================================
# TEST 2 -- Word document (.docx) -- Docling HybridChunker
# ===========================================================================
if 2 not in RUN:
    print(f"{SEP}\nTEST 2 -- [SKIPPED]\n")
else:
    print(SEP)
    print("TEST 2 -- Word document (.docx)  --  Docling HybridChunker")
    print(SEP)
    print("NOTE: Docling imports PyTorch/transformers -- first run can take 1-3 min.")
    print()

    if not DOCX_FILE.exists():
        print(f"[SKIP] {DOCX_FILE} not found.\n")
    else:
        try:
            # 2a. Parse + pre-chunk via Docling
            print("Step 2a: Parsing & Chunking with Docling HybridChunker ...")
            raw_docs    = load_file(DOCX_FILE)
            pre_chunked = raw_docs[0].metadata.get("pre_chunked", False) if raw_docs else False
            print(f"  File       : {DOCX_FILE.name}")
            print(f"  Chunks     : {len(raw_docs)}")
            print(f"  Pre-chunked: {pre_chunked}")
            print()
            _print_chunks(raw_docs)

            # 2b. Embed + Store
            print("Step 2b: Embedding & Storing (Ollama -> ChromaDB) ...")
            delete_collection(TEST_COLLECTION_DOCX)
            added  = index_file(DOCX_FILE, TEST_COLLECTION_DOCX)
            stored = collection_count(TEST_COLLECTION_DOCX)
            print(f"  Chunks added : {added}")
            print(f"  Chunks in DB : {stored}")
            print(f"  Status       : {'PASS' if added > 0 and stored == added else 'FAIL'}")
            print()

            # 2c. Similarity search
            print("Step 2c: Similarity Search ...")
            _similarity_search(get_collection(TEST_COLLECTION_DOCX), [
                "project goals and objectives",
                "timetable and schedule",
                "payment terms and conditions",
            ])

        except KeyboardInterrupt:
            print("\n[INTERRUPTED] Docling import was aborted (Ctrl+C).")
            print("  Re-run with: python test_pipeline.py --tests 1 3  (skip DOCX)\n")
        except Exception as e:
            print(f"[ERROR/SKIP] {type(e).__name__}: {e}")
            print("  Docling test skipped -- broken dependency or import error.\n")


# ===========================================================================
# TEST 3 -- Excel file (.xlsx) -- structured + fallback parser
# ===========================================================================
if 3 not in RUN:
    print(f"{SEP}\nTEST 3 -- [SKIPPED]\n")
else:
    print(SEP)
    print("TEST 3 -- Excel file (.xlsx)  --  laskentapohja.xlsx")
    print(SEP)

    if not XLSX_FILE.exists():
        print(f"[SKIP] {XLSX_FILE} not found.\n")
    else:
        try:
            # 3a. Parse
            print("Step 3a: Parsing (excel_parser -> structured, fallback to pandas) ...")
            raw_docs   = load_file(XLSX_FILE)
            structured = any(d.metadata.get("structured") for d in raw_docs)
            sheets     = [d.metadata.get("sheet", "?") for d in raw_docs]
            print(f"  File            : {XLSX_FILE.name}")
            print(f"  Documents loaded: {len(raw_docs)}")
            print(f"  Structured parse: {structured}")
            print(f"  Sheets          : {sheets}")
            print()

            # 3b. Parsed text snippets per sheet
            print("Step 3b: Parsed text snippets ...")
            for d in raw_docs:
                sheet = d.metadata.get("sheet", "?")
                print(f"  Sheet={sheet!r}  {len(d.page_content)} chars")
                print(f"    {_truncate(d.page_content, 200)!r}")
            print()

            # 3c. Chunk
            print("Step 3c: Chunking (RecursiveCharacterTextSplitter) ...")
            splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
            chunks = splitter.split_documents(raw_docs)
            print(f"  Chunks produced : {len(chunks)}")
            _print_chunks(chunks)

            # 3d. Embed + Store
            print("Step 3d: Embedding & Storing (Ollama -> ChromaDB) ...")
            delete_collection(TEST_COLLECTION_XLSX)
            added  = index_file(XLSX_FILE, TEST_COLLECTION_XLSX)
            stored = collection_count(TEST_COLLECTION_XLSX)
            print(f"  Chunks added : {added}")
            print(f"  Chunks in DB : {stored}")
            print(f"  Status       : {'PASS' if added > 0 and stored == added else 'FAIL'}")
            print()

            # 3e. Similarity search
            print("Step 3e: Similarity Search ...")
            _similarity_search(get_collection(TEST_COLLECTION_XLSX), [
                "labor hours and cost estimate",
                "software development work",
                "total project cost",
            ])

        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print("Cleanup -- removing temporary test collections ...")
for _coll in [TEST_COLLECTION_TXT, TEST_COLLECTION_DOCX, TEST_COLLECTION_XLSX]:
    delete_collection(_coll)
    print(f"  Deleted: {_coll}")
print()
print("All tests completed.")
print(SEP)
