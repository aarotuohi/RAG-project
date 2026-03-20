"""
Full pipeline test: Parse → Chunk → Embed → Store → Query
Tests .txt/.md, .docx/.pptx/.pdf, and .xlsx/.xls files from directories.

── TEST MODE (temporary collections, cleaned up after) ──────────────────────
    python test_pipeline.py              # all tests
    python test_pipeline.py --tests 1 3  # only TXT + XLSX (skips slow Docling)
    python test_pipeline.py --tests 2    # only DOCX (Docling must be working)

── PRODUCTION MODE (real collections, data persisted) ───────────────────────
    python test_pipeline.py --production            # all 3, real dirs & collections
    python test_pipeline.py --production --tests 3  # Excel only
    python test_pipeline.py --production --tests 1  # TXT/MD only → boilerplate
    python test_pipeline.py --production --tests 2  # DOCX/PDF only → cv_database
    python test_pipeline.py --production --keep     # append, don't clear first

── OVERRIDE DIRECTORIES ─────────────────────────────────────────────────────
    python test_pipeline.py --production --txt-dir  path/to/txt_files
    python test_pipeline.py --production --docx-dir path/to/docx_files
    python test_pipeline.py --production --dir      path/to/excel_files

Production defaults:
    TEST 1 (TXT/MD)       → data/documents/boilerplate/  → boilerplate collection
    TEST 2 (DOCX/PDF/PPTX)→ data/documents/cvs/          → cv_database collection
    TEST 3 (XLSX/XLS)     → data/documents/cost_history/ → cost_history collection

Requires:
  - Ollama running with nomic-embed-text pulled
  - docling installed (for .docx/.pdf/.pptx / TEST 2)
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
    help="Which tests to run (1=TXT/MD, 2=DOCX/PDF/PPTX, 3=XLSX). Default: all.",
)
parser.add_argument(
    "--all-chunks", action="store_true",
    help="Print every chunk in full (no count limit, no content truncation).",
)
parser.add_argument(
    "--production", action="store_true",
    help="Store into REAL collections (no cleanup). Uses real document dirs by default.",
)
parser.add_argument(
    "--txt-dir", default=None, metavar="DIR",
    help="Directory of .txt/.md files for TEST 1. "
         "Production default: data/documents/boilerplate  "
         "Test default: data/documents/boilerplate",
)
parser.add_argument(
    "--docx-dir", default=None, metavar="DIR",
    help="Directory of .docx/.pptx/.pdf files for TEST 2. "
         "Production default: data/documents/cvs  "
         "Test default: data/documents/cvs",
)
parser.add_argument(
    "--dir", default=None, metavar="DIR",
    help="Directory of .xlsx/.xls files for TEST 3. "
         "Production default: data/documents/cost_history  "
         "Test default: data/raw/offer_calculations",
)
parser.add_argument(
    "--keep", action="store_true",
    help="Do NOT clear collections before ingesting (append mode). Only affects --production.",
)
args = parser.parse_args()
RUN = set(args.tests)

# ─────────────────────────────────────────────────────────────────────────────
# Resolve directories
# ─────────────────────────────────────────────────────────────────────────────
from backend.config import BOILERPLATE_DIR, CV_DIR, COST_HISTORY_DIR  # noqa: E402

TXT_DIR  = Path(args.txt_dir)  if args.txt_dir  else BOILERPLATE_DIR
DOCX_DIR = Path(args.docx_dir) if args.docx_dir else CV_DIR
XLSX_DIR = Path(args.dir)      if args.dir       else (COST_HISTORY_DIR if args.production else Path("data/raw/offer_calculations"))

# Temporary test collections — cleaned up at the end
TEST_COLLECTION_TXT  = "test_txt_pipeline"
TEST_COLLECTION_DOCX = "test_docx_pipeline"
TEST_COLLECTION_XLSX = "test_xlsx_pipeline"

SEP = "=" * 70


def _truncate(text: str, width: int = 180) -> str:
    return textwrap.shorten(text.strip(), width=width, placeholder=" ...")


def _print_chunks(docs, max_show: int = 5):
    show_all = max_show is None
    limit = len(docs) if show_all else max_show
    for i, d in enumerate(docs[:limit]):
        heading = d.metadata.get("heading", "")
        sheet   = d.metadata.get("sheet", "")
        tag     = f"heading={heading!r}" if heading else (f"sheet={sheet!r}" if sheet else "")
        pre     = "pre-chunked" if d.metadata.get("pre_chunked") else "splitter"
        print(f"  Chunk {i+1:02d}  [{pre}]  {len(d.page_content):4d} chars  {tag}")
        content = d.page_content.strip() if show_all else _truncate(d.page_content, 130)
        print(f"           {content!r}")
    if not show_all and len(docs) > max_show:
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
    from backend.config import CHUNK_SIZE, CHUNK_OVERLAP, CHROMA_COLLECTION_BOILER, CHROMA_COLLECTION_CV, CHROMA_COLLECTION_COST
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError as exc:
    sys.exit(
        f"[ERROR] Could not import backend modules: {exc}\n"
        "Make sure you run from the project root and the virtualenv is active."
    )

print(SEP)
if args.production:
    print("AISALES -- Production Ingestion  (Parse -> Chunk -> Embed -> Store)")
    print("  Mode: PRODUCTION  →  real collections, data persisted")
else:
    print("AISALES -- Pipeline Test  (Parse -> Chunk -> Embed -> Store -> Query)")
    print("  Mode: TEST  →  temporary collections (cleaned up after)")
print(SEP)
print(f"  Running tests : {sorted(RUN)}")
print(f"  TXT/MD  dir   : {TXT_DIR}")
print(f"  DOCX/PDF dir  : {DOCX_DIR}")
print(f"  XLSX dir      : {XLSX_DIR}")
print(f"  CHUNK_SIZE    : {CHUNK_SIZE}")
print(f"  CHUNK_OVERLAP : {CHUNK_OVERLAP}")
print()


# ===========================================================================
# TEST 1 -- Plain-text / Markdown (.txt, .md) from a directory
# ===========================================================================
if 1 not in RUN:
    print(f"{SEP}\nTEST 1 -- [SKIPPED]\n")
else:
    print(SEP)
    print(f"TEST 1 -- TXT/MD files  --  {TXT_DIR}")
    print(SEP)

    if not TXT_DIR.exists() or not TXT_DIR.is_dir():
        print(f"[SKIP] Directory not found: {TXT_DIR}\n")
    else:
        txt_files = sorted(TXT_DIR.glob("*.txt")) + sorted(TXT_DIR.glob("*.md"))
        if not txt_files:
            print(f"[SKIP] No .txt/.md files found in {TXT_DIR}\n")
        else:
            print(f"  Found {len(txt_files)} file(s):")
            for f in txt_files:
                print(f"    {f.name}")
            print()

            txt_collection = CHROMA_COLLECTION_BOILER if args.production else TEST_COLLECTION_TXT

            if args.production:
                if not args.keep:
                    delete_collection(txt_collection)
                    print(f"  Collection '{txt_collection}' cleared (use --keep to append).")
                else:
                    print(f"  Appending to existing collection '{txt_collection}'.")
            else:
                delete_collection(txt_collection)
            print()

            total_chunks = 0
            splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

            for file_idx, txt_file in enumerate(txt_files, 1):
                file_sep = "-" * 60
                print(file_sep)
                print(f"  [{file_idx}/{len(txt_files)}] {txt_file.name}")
                print(file_sep)

                print("  Step 1a: Parsing ...")
                raw_docs = load_file(txt_file)
                if not raw_docs:
                    print("    [SKIP] No content parsed.\n")
                    continue
                print(f"    Characters: {sum(len(d.page_content) for d in raw_docs)}")

                print("  Step 1b: Chunking ...")
                chunks = splitter.split_documents(raw_docs)
                print(f"    Chunks produced: {len(chunks)}")
                _print_chunks(chunks, max_show=None if args.all_chunks else 3)

                print(f"  Step 1c: Embedding & Storing → [{txt_collection}]")
                added = index_file(txt_file, txt_collection)
                total_chunks += added
                print(f"    Chunks added : {added}")
                print(f"    Status       : {'PASS' if added > 0 else 'FAIL — 0 chunks stored'}")
                print()

            stored = collection_count(txt_collection)
            print(file_sep)
            print(f"  SUMMARY")
            print(f"    Files processed   : {len(txt_files)}")
            print(f"    Total chunks added: {total_chunks}")
            print(f"    Chunks in DB now  : {stored}")
            print()

            print("  Step 1d: Similarity Search (across all ingested files) ...")
            _similarity_search(get_collection(txt_collection), [
                "project goals and requirements",
                "delivery schedule and timeline",
                "pricing and costs",
            ])


# ===========================================================================
# TEST 2 -- Word / PDF / PowerPoint (.docx, .pptx, .pdf) from a directory
# ===========================================================================
if 2 not in RUN:
    print(f"{SEP}\nTEST 2 -- [SKIPPED]\n")
else:
    print(SEP)
    print(f"TEST 2 -- DOCX/PPTX/PDF files  --  {DOCX_DIR}")
    print(SEP)
    print("NOTE: Docling imports PyTorch/transformers -- first run can take 1-3 min.")
    print()

    if not DOCX_DIR.exists() or not DOCX_DIR.is_dir():
        print(f"[SKIP] Directory not found: {DOCX_DIR}\n")
    else:
        docx_files = (
            sorted(DOCX_DIR.glob("*.docx")) +
            sorted(DOCX_DIR.glob("*.pptx")) +
            sorted(DOCX_DIR.glob("*.pdf"))
        )
        if not docx_files:
            print(f"[SKIP] No .docx/.pptx/.pdf files found in {DOCX_DIR}\n")
        else:
            print(f"  Found {len(docx_files)} file(s):")
            for f in docx_files:
                print(f"    {f.name}")
            print()

            docx_collection = CHROMA_COLLECTION_CV if args.production else TEST_COLLECTION_DOCX

            if args.production:
                if not args.keep:
                    delete_collection(docx_collection)
                    print(f"  Collection '{docx_collection}' cleared (use --keep to append).")
                else:
                    print(f"  Appending to existing collection '{docx_collection}'.")
            else:
                delete_collection(docx_collection)
            print()

            total_chunks = 0

            for file_idx, docx_file in enumerate(docx_files, 1):
                file_sep = "-" * 60
                print(file_sep)
                print(f"  [{file_idx}/{len(docx_files)}] {docx_file.name}")
                print(file_sep)

                try:
                    print("  Step 2a: Parsing & Chunking (Docling HybridChunker) ...")
                    raw_docs    = load_file(docx_file)
                    if not raw_docs:
                        print("    [SKIP] No content parsed.\n")
                        continue
                    pre_chunked = raw_docs[0].metadata.get("pre_chunked", False)
                    print(f"    Chunks     : {len(raw_docs)}")
                    print(f"    Pre-chunked: {pre_chunked}")
                    _print_chunks(raw_docs, max_show=None if args.all_chunks else 3)

                    print(f"  Step 2b: Embedding & Storing → [{docx_collection}]")
                    added = index_file(docx_file, docx_collection)
                    total_chunks += added
                    print(f"    Chunks added : {added}")
                    print(f"    Status       : {'PASS' if added > 0 else 'FAIL — 0 chunks stored'}")
                    print()

                except KeyboardInterrupt:
                    print("\n[INTERRUPTED] Docling aborted (Ctrl+C).")
                    print("  Re-run with: python test_pipeline.py --tests 1 3  (skip DOCX)\n")
                    break
                except Exception as e:
                    print(f"    [ERROR/SKIP] {type(e).__name__}: {e}\n")

            stored = collection_count(docx_collection)
            print(file_sep)
            print(f"  SUMMARY")
            print(f"    Files processed   : {len(docx_files)}")
            print(f"    Total chunks added: {total_chunks}")
            print(f"    Chunks in DB now  : {stored}")
            print()

            print("  Step 2c: Similarity Search (across all ingested files) ...")
            _similarity_search(get_collection(docx_collection), [
                "project goals and objectives",
                "timetable and schedule",
                "payment terms and conditions",
            ])


# ===========================================================================
# TEST 3 -- Excel files (.xlsx/.xls) from a directory
# ===========================================================================
if 3 not in RUN:
    print(f"{SEP}\nTEST 3 -- [SKIPPED]\n")
else:
    print(SEP)
    print(f"TEST 3 -- Excel files (.xlsx/.xls)  --  {XLSX_DIR}")
    print(SEP)

    if not XLSX_DIR.exists() or not XLSX_DIR.is_dir():
        print(f"[SKIP] Directory not found: {XLSX_DIR}\n")
    else:
        xlsx_files = sorted(XLSX_DIR.glob("*.xlsx")) + sorted(XLSX_DIR.glob("*.xls"))
        if not xlsx_files:
            print(f"[SKIP] No .xlsx/.xls files found in {XLSX_DIR}\n")
        else:
            print(f"  Found {len(xlsx_files)} file(s):")
            for f in xlsx_files:
                print(f"    {f.name}")
            print()

            try:
                from backend.config import CHROMA_COLLECTION_COST
                xlsx_collection = CHROMA_COLLECTION_COST if args.production else TEST_COLLECTION_XLSX

                # Clear collection once before processing all files
                if args.production:
                    if not args.keep:
                        delete_collection(xlsx_collection)
                        print(f"  Collection '{xlsx_collection}' cleared (use --keep to append).")
                    else:
                        print(f"  Appending to existing collection '{xlsx_collection}'.")
                else:
                    delete_collection(xlsx_collection)
                print()

                total_chunks = 0
                splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

                for file_idx, XLSX_FILE in enumerate(xlsx_files, 1):
                    file_sep = "-" * 60
                    print(f"{file_sep}")
                    print(f"  [{file_idx}/{len(xlsx_files)}] {XLSX_FILE.name}")
                    print(f"{file_sep}")

                    # 3a. Parse
                    print("  Step 3a: Parsing ...")
                    raw_docs   = load_file(XLSX_FILE)
                    if not raw_docs:
                        print("    [SKIP] No documents parsed from this file.\n")
                        continue
                    structured = any(d.metadata.get("structured") for d in raw_docs)
                    sheets     = [d.metadata.get("sheet", "?") for d in raw_docs]
                    print(f"    Documents loaded: {len(raw_docs)}")
                    print(f"    Structured parse: {structured}")
                    print(f"    Sheets          : {sheets}")

                    # 3b. Parsed text snippets
                    print("  Step 3b: Parsed text snippets ...")
                    for d in raw_docs:
                        sheet = d.metadata.get("sheet", "?")
                        print(f"    Sheet={sheet!r}  {len(d.page_content)} chars")
                        print(f"      {_truncate(d.page_content, 180)!r}")
                    print()

                    # 3c. Chunk
                    print("  Step 3c: Chunking ...")
                    chunks = splitter.split_documents(raw_docs)
                    print(f"    Chunks produced : {len(chunks)}")
                    _print_chunks(chunks, max_show=None if args.all_chunks else 3)

                    # 3d. Embed + Store (append — collection already cleared above)
                    print(f"  Step 3d: Embedding & Storing → [{xlsx_collection}]")
                    added = index_file(XLSX_FILE, xlsx_collection)
                    total_chunks += added
                    print(f"    Chunks added : {added}")
                    print(f"    Status       : {'PASS' if added > 0 else 'FAIL — 0 chunks stored'}")
                    print()

                stored = collection_count(xlsx_collection)
                print(file_sep)
                print(f"  SUMMARY")
                print(f"    Files processed   : {len(xlsx_files)}")
                print(f"    Total chunks added: {total_chunks}")
                print(f"    Chunks in DB now  : {stored}")
                print()

                # 3e. Similarity search across all ingested files
                print("  Step 3e: Similarity Search (across all ingested files) ...")
                _similarity_search(get_collection(xlsx_collection), [
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
_cleanup = []
if not args.production:
    _cleanup = [TEST_COLLECTION_TXT, TEST_COLLECTION_DOCX, TEST_COLLECTION_XLSX]
for _coll in _cleanup:
    delete_collection(_coll)
    print(f"  Deleted: {_coll}")
if args.production:
    print(f"  Kept: {CHROMA_COLLECTION_BOILER}, {CHROMA_COLLECTION_CV}, {CHROMA_COLLECTION_COST}  (production — not deleted)")
print()
print("All tests completed.")
print(SEP)
