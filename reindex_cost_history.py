"""
Re-index cost history files into ChromaDB.

Deletes the existing 'cost_history' collection and re-ingests every
supported file from data/documents/cost_history/ (and all sub-folders)
with the current parser.  Each sub-folder is treated as a project category
(e.g. software_development/, electronics_design/) and the folder name is
stored as 'project_category' metadata on every chunk.

Run from the project root:
    python reindex_cost_history.py
"""
from pathlib import Path

from backend.config import COST_HISTORY_DIR, CHROMA_COLLECTION_COST
from backend.vectorstore.chroma_client import delete_collection
from backend.ingestion.document_loader import index_file

SUPPORTED = {".xlsx", ".xls", ".docx", ".pdf", ".txt", ".md"}

def main():
    print(f"Cost history directory: {COST_HISTORY_DIR}")

    # Delete old collection so stale chunks from the old format are gone
    print("Deleting existing 'cost_history' collection …")
    delete_collection(CHROMA_COLLECTION_COST)
    print("  Done.")

    # rglob scans all sub-folders (one sub-folder = one project category)
    files = [
        f for f in COST_HISTORY_DIR.rglob("*")
        if f.is_file()
        and f.suffix.lower() in SUPPORTED
        and not f.name.startswith("~$")   # skip Office temp/lock files
    ]
    if not files:
        print("No files found in cost_history directory or its sub-folders. Nothing to index.")
        return

    total_chunks = 0
    for f in sorted(files):
        rel = f.relative_to(COST_HISTORY_DIR)
        chunks = index_file(f, CHROMA_COLLECTION_COST)
        print(f"  {str(rel):<60} → {chunks} chunks")
        total_chunks += chunks

    print(f"\nDone. {len(files)} file(s), {total_chunks} total chunks indexed.")

if __name__ == "__main__":
    main()
