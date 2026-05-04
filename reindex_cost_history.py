"""
Re-index cost history files into ChromaDB.

By default only NEW files (not yet in the collection) are indexed, so running
this script repeatedly on a large library is fast.

Use --force to delete the existing collection and re-ingest every file from
scratch (useful after changing the parser or chunk settings).

Each sub-folder is treated as a project category (e.g. software_development/,
electronics_design/) and the folder name is stored as 'project_category'
metadata on every chunk.

Run from the project root:
    python reindex_cost_history.py            # index new files only
    python reindex_cost_history.py --force    # full re-index
"""
import argparse
from pathlib import Path

from backend.config import COST_HISTORY_DIR, CHROMA_COLLECTION_COST
from backend.vectorstore.chroma_client import delete_collection
from backend.ingestion.document_loader import index_file

SUPPORTED = {".xlsx", ".xls", ".docx", ".pdf", ".txt", ".md"}

def main():
    parser = argparse.ArgumentParser(description="Index cost-history files into ChromaDB.")
    parser.add_argument(
        "--force", action="store_true",
        help="Delete the existing collection and re-index every file from scratch.",
    )
    args = parser.parse_args()

    print(f"Cost history directory: {COST_HISTORY_DIR}")

    if args.force:
        print("--force: deleting existing 'cost_history' collection …")
        delete_collection(CHROMA_COLLECTION_COST)
        print("  Done.")
    else:
        print("Incremental mode: only new files will be indexed (use --force to re-index everything).")

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
    skipped = 0
    for f in sorted(files):
        rel = f.relative_to(COST_HISTORY_DIR)
        # Sub-folder name becomes the project_category; files in the root get no category
        category = rel.parts[0] if len(rel.parts) > 1 else None
        extra = {"project_category": category} if category else {}
        chunks = index_file(
            f, CHROMA_COLLECTION_COST,
            extra_metadata=extra or None,
            skip_if_indexed=not args.force,
        )
        if chunks == 0 and not args.force:
            skipped += 1
        else:
            print(f"  {str(rel):<60} → {chunks} chunks  [category: {category or '(root)'}]")
            total_chunks += chunks

    print(f"\nDone. {len(files)} file(s) found — {len(files) - skipped} indexed, {skipped} skipped (already indexed).")
    if total_chunks:
        print(f"Total new chunks added: {total_chunks}")

if __name__ == "__main__":
    main()
