"""
Quick test script: parse → chunk → embed → store one file, then query it.

Run from project root:
    python test_ingestion.py                          # default: laskentapohja.xlsx → cost_history
    python test_ingestion.py --file path/to/file.xlsx --collection cost_history
    python test_ingestion.py --file path/to/file.docx --collection boilerplate
    python test_ingestion.py --all-chunks             # print full chunk content

Supported formats : .xlsx, .xls, .docx, .pptx, .pdf, .txt, .md
Collections       : cost_history | cv | boilerplate | contacts

Requires Ollama to be running with nomic-embed-text pulled.
"""
import sys
import argparse
import textwrap
from pathlib import Path

# ── CLI arguments ─────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="AISALES single-file ingestion test")
parser.add_argument(
    "--file", "-f",
    default="data/raw/offer_calculations/laskentapohja.xlsx",
    help="Path to the file to ingest (default: laskentapohja.xlsx)",
)
parser.add_argument(
    "--collection", "-c",
    default="cost_history",
    choices=["cost_history", "cv", "boilerplate", "contacts"],
    help="Target ChromaDB collection (default: cost_history)",
)
parser.add_argument(
    "--keep", action="store_true",
    help="Do NOT delete the collection before ingesting (append mode).",
)
parser.add_argument(
    "--all-chunks", action="store_true",
    help="Print every chunk in full (no truncation). Useful for Excel inspection.",
)
args = parser.parse_args()

FILE       = Path(args.file)
COLLECTION = args.collection
SEP        = "=" * 60

# ── Imports ───────────────────────────────────────────────────────────────────
try:
    from backend.ingestion.document_loader import load_file, index_file
    from backend.vectorstore.chroma_client import get_collection, collection_count, delete_collection
except ImportError as exc:
    sys.exit(
        f"[ERROR] Could not import backend modules: {exc}\n"
        "Make sure you run from the project root and the virtualenv is active."
    )

if not FILE.exists():
    sys.exit(f"[ERROR] File not found: {FILE}")

print(SEP)
print(f"AISALES — Single-file Ingestion Test")
print(SEP)
print(f"  File       : {FILE}")
print(f"  Collection : {COLLECTION}")
print(f"  Keep existing data: {args.keep}")
print()

# ── STEP 1: Parse ─────────────────────────────────────────────────────────────
print(SEP)
print("STEP 1 — Parsing")
print(SEP)

docs = load_file(FILE)

if not docs:
    sys.exit("[ERROR] load_file() returned no documents. Check the file format.")

suffix = FILE.suffix.lower()
is_excel      = suffix in (".xlsx", ".xls")
is_pre_chunked = docs[0].metadata.get("pre_chunked", False)
is_structured  = any(d.metadata.get("structured") for d in docs)

print(f"  Documents loaded : {len(docs)}")
if is_excel:
    sheets = [d.metadata.get("sheet", "?") for d in docs]
    print(f"  Structured parse : {is_structured}")
    print(f"  Sheets           : {sheets}")
elif is_pre_chunked:
    print(f"  Pre-chunked      : True  (Docling HybridChunker)")
else:
    print(f"  Total characters : {sum(len(d.page_content) for d in docs)}")
print()

# ── STEP 2: Chunk ─────────────────────────────────────────────────────────────
print(SEP)
print("STEP 2 — Chunking")
print(SEP)

from backend.config import CHUNK_SIZE, CHUNK_OVERLAP
from langchain_text_splitters import RecursiveCharacterTextSplitter

if is_pre_chunked:
    chunks = docs
    print(f"  Skipped (Docling already produced {len(chunks)} pre-chunked docs)")
else:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = splitter.split_documents(docs)
    print(f"  CHUNK_SIZE    : {CHUNK_SIZE}")
    print(f"  CHUNK_OVERLAP : {CHUNK_OVERLAP}")
    print(f"  Chunks produced : {len(chunks)}")
print()

max_show = None if args.all_chunks else 5
show_limit = len(chunks) if max_show is None else max_show
for i, d in enumerate(chunks[:show_limit]):
    heading = d.metadata.get("heading", "")
    sheet   = d.metadata.get("sheet", "")
    tag     = f"heading={heading!r}" if heading else (f"sheet={sheet!r}" if sheet else "")
    pre     = "pre-chunked" if d.metadata.get("pre_chunked") else "splitter"
    print(f"  Chunk {i+1:02d}  [{pre}]  {len(d.page_content):4d} chars  {tag}")
    content = d.page_content.strip() if args.all_chunks else textwrap.shorten(d.page_content.strip(), 140, placeholder=" ...")
    print(f"           {content!r}")
if not args.all_chunks and len(chunks) > 5:
    print(f"  ... ({len(chunks) - 5} more chunks — use --all-chunks to see all)")
print()

# ── STEP 3: Embed + Store ─────────────────────────────────────────────────────
print(SEP)
print("STEP 3 — Embedding & Storing  (Ollama → ChromaDB)")
print(SEP)

if not args.keep:
    delete_collection(COLLECTION)
    print(f"  Collection '{COLLECTION}' cleared.")

added = index_file(FILE, COLLECTION)
after = collection_count(COLLECTION)

print(f"  Chunks added  : {added}")
print(f"  Chunks in DB  : {after}")
print(f"  Status        : {'PASS' if added > 0 else 'FAIL — no chunks were stored'}")
print()

# ── STEP 4: Similarity search ─────────────────────────────────────────────────
print(SEP)
print("STEP 4 — Similarity Search  (query the stored chunks)")
print(SEP)

# Pick queries relevant to the collection / file type
_QUERIES = {
    "cost_history": ["labor hours and cost estimate", "software development work", "total project cost"],
    "cv":           ["programming skills and experience", "education background", "work history"],
    "boilerplate":  ["payment terms and conditions", "delivery schedule", "quality assurance"],
    "contacts":     ["contact person and email", "company name", "sales representative"],
}
queries = _QUERIES.get(COLLECTION, ["main topic", "key details", "summary"])

col = get_collection(COLLECTION)
for query in queries:
    results = col.similarity_search(query, k=2)
    print(f"\n  Query: {query!r}")
    for j, r in enumerate(results):
        snippet = textwrap.shorten(r.page_content.strip(), 200, placeholder=" ...")
        print(f"    Result {j+1}: {snippet!r}")

print()
print("Done.")
