"""
ChromaDB client — manages the four named collections used by AISALES.
"""
from __future__ import annotations
import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma
from backend.config import VECTORSTORE_DIR
from backend.ollama_client import get_embeddings

_client: chromadb.PersistentClient | None = None


def get_chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=str(VECTORSTORE_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_collection(name: str) -> Chroma:
    """Return a LangChain Chroma wrapper for the given collection name."""
    return Chroma(
        client=get_chroma_client(),
        collection_name=name,
        embedding_function=get_embeddings(),
    )


def delete_collection(name: str):
    client = get_chroma_client()
    try:
        client.delete_collection(name)
    except Exception:
        pass


def collection_count(name: str) -> int:
    client = get_chroma_client()
    try:
        col = client.get_collection(name)
        return col.count()
    except Exception:
        return 0


def source_exists(file_path, collection_name: str) -> bool:
    """Return True if at least one chunk with source==str(file_path) is already in the collection."""
    client = get_chroma_client()
    try:
        col = client.get_collection(collection_name)
        result = col.get(where={"source": str(file_path)}, limit=1, include=[])
        return len(result["ids"]) > 0
    except Exception:
        return False
