"""
Inspect what is stored in the 'cost_history' ChromaDB collection.

Run from the project root:
    python inspect_cost_history.py                     # show all chunks
    python inspect_cost_history.py software_development  # filter by folder
    python inspect_cost_history.py --summary             # folder summary only
"""
import sys
from collections import defaultdict

from backend.vectorstore.chroma_client import get_chroma_client
from backend.config import CHROMA_COLLECTION_COST

def main():
    args = sys.argv[1:]
    summary_only = "--summary" in args
    folder_filter = next((a for a in args if not a.startswith("--")), None)

    client = get_chroma_client()
    try:
        col = client.get_collection(CHROMA_COLLECTION_COST)
    except Exception as e:
        print(f"Collection not found: {e}")
        return

    total = col.count()
    print(f"Collection '{CHROMA_COLLECTION_COST}' — {total} chunk(s) stored\n")

    result = col.get(include=["documents", "metadatas", "embeddings"])
    ids        = result["ids"]
    docs       = result["documents"]
    metas      = result["metadatas"]
    embeddings = result["embeddings"]

    # Group by project_category for the summary
    by_cat: dict[str, list] = defaultdict(list)
    for doc_id, content, meta, emb in zip(ids, docs, metas, embeddings):
        cat = meta.get("project_category") or meta.get("source", "?").replace("\\", "/").split("/")[-2]
        by_cat[cat].append((doc_id, content, meta, emb))

    print("=== FOLDER SUMMARY ===")
    for cat in sorted(by_cat):
        label = cat if cat else "(root / no category)"
        print(f"  {label:<40} {len(by_cat[cat])} chunk(s)")
    print()

    if summary_only:
        return

    # Filter to requested folder if given
    if folder_filter:
        if folder_filter not in by_cat:
            print(f"Folder '{folder_filter}' not found. Available: {sorted(by_cat.keys())}")
            return
        subset = {folder_filter: by_cat[folder_filter]}
        print(f"Showing chunks for folder: {folder_filter}\n")
    else:
        subset = by_cat

    chunk_num = 0
    for cat in sorted(subset):
        entries = subset[cat]
        label = cat if cat else "(root / no category)"
        print(f"\n{'#' * 70}")
        print(f"FOLDER: {label}  ({len(entries)} chunk(s))")
        print(f"{'#' * 70}")
        for doc_id, content, meta, emb in entries:
            chunk_num += 1
            print("=" * 70)
            print(f"CHUNK {chunk_num}")
            print(f"  ID       : {doc_id}")
            print(f"  Source   : {meta.get('source', '?').replace(chr(92), '/').split('/')[-1]}")
            print(f"  Sheet    : {meta.get('sheet', '?')}")
            print(f"  Phase    : {meta.get('phase', '?')}")
            print(f"  Category : {meta.get('project_category', '?')}")
            print(f"  Type     : {meta.get('type', '?')}  |  structured={meta.get('structured', False)}")
            print(f"  Embedding: {len(emb)} dimensions  first 5 values: {[round(v,4) for v in emb[:5]]}")
            print()
            print("  --- CONTENT ---")
            for line in content.splitlines():
                print("  " + line)
            print()

if __name__ == "__main__":
    main()
