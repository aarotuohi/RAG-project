"""
Quick test script: parse → chunk → embed → store one file, then query it.
Run from project root:  python test_ingestion.py
"""
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

FILE = Path("data/raw/offers/offer_Military_Communication_Helmet_Project_2026-02-23.docx")
COLLECTION = "boilerplate"   # store into 'boilerplate' for this test

# ── STEP 1: Parse + Chunk ─────────────────────────────────────────────────────
print("=" * 60)
print("STEP 1 — Parsing & Chunking  (Docling HybridChunker)")
print("=" * 60)

from backend.ingestion.document_loader import load_file
docs = load_file(FILE)

print(f"File         : {FILE.name}")
print(f"Total chunks : {len(docs)}")
print(f"Pre-chunked  : {docs[0].metadata.get('pre_chunked', False) if docs else 'N/A'}")
print()

for i, d in enumerate(docs):
    heading = d.metadata.get("heading", "(no heading)")
    print(f"  Chunk {i+1:02d}  |  {len(d.page_content):4d} chars  |  heading: {heading}")
    print(f"           {d.page_content[:160].strip()!r}")
    print()

# ── STEP 2: Embed + Store ─────────────────────────────────────────────────────
print("=" * 60)
print("STEP 2 — Embedding & Storing  (OpenAI → ChromaDB)")
print("=" * 60)

from backend.ingestion.document_loader import index_file
from backend.vectorstore.chroma_client import collection_count

before = collection_count(COLLECTION)
added  = index_file(FILE, COLLECTION)
after  = collection_count(COLLECTION)

print(f"Chunks before : {before}")
print(f"Chunks added  : {added}")
print(f"Chunks after  : {after}")
print()

# ── STEP 3: Similarity search ─────────────────────────────────────────────────
print("=" * 60)
print("STEP 3 — Similarity Search  (query the stored chunks)")
print("=" * 60)

from backend.vectorstore.chroma_client import get_collection
col = get_collection(COLLECTION)

for query in ["project goals and objectives", "timetable schedule", "payment terms"]:
    results = col.similarity_search(query, k=2)
    print(f"\nQuery: '{query}'")
    for j, r in enumerate(results):
        print(f"  Result {j+1}: {r.page_content[:200].strip()!r}")

print()
print("Done.")
