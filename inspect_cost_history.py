"""
Inspect what is stored in the 'cost_history' ChromaDB collection.

Run from the project root:
    python inspect_cost_history.py
"""
from backend.vectorstore.chroma_client import get_chroma_client
from backend.config import CHROMA_COLLECTION_COST

def main():
    client = get_chroma_client()
    try:
        col = client.get_collection(CHROMA_COLLECTION_COST)
    except Exception as e:
        print(f"Collection not found: {e}")
        return

    total = col.count()
    print(f"Collection '{CHROMA_COLLECTION_COST}' — {total} chunk(s) stored\n")

    result = col.get(include=["documents", "metadatas", "embeddings"])
    ids       = result["ids"]
    docs      = result["documents"]
    metas     = result["metadatas"]
    embeddings = result["embeddings"]

    for i, (doc_id, content, meta, emb) in enumerate(zip(ids, docs, metas, embeddings), 1):
        print("=" * 70)
        print(f"CHUNK {i} / {total}")
        print(f"  ID       : {doc_id}")
        print(f"  Source   : {meta.get('source', '?').replace(chr(92), '/').split('/')[-1]}")
        print(f"  Sheet    : {meta.get('sheet', '?')}")
        print(f"  Phase    : {meta.get('phase', '?')}")
        print(f"  Type     : {meta.get('type', '?')}  |  structured={meta.get('structured', False)}")
        print(f"  Embedding: {len(emb)} dimensions  first 5 values: {[round(v,4) for v in emb[:5]]}")
        print()
        print("  --- CONTENT ---")
        for line in content.splitlines():
            print("  " + line)
        print()

if __name__ == "__main__":
    main()
