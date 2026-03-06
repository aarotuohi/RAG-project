"""
OpenAI client — wraps LangChain ChatOpenAI + OpenAIEmbeddings.
Provides the same public interface as the former Ollama client so that
all chain files work without modification.

Required environment variable:
    OPENAI_API_KEY  — your OpenAI secret key

Optional environment variables:
    OPENAI_LLM_MODEL    — chat model to use          (default: gpt-4o-mini)
    OPENAI_EMBED_MODEL  — embedding model to use     (default: text-embedding-3-small)
"""
from __future__ import annotations
import os
import requests
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.output_parsers import StrOutputParser

from backend.config import OPENAI_LLM_MODEL, OPENAI_EMBED_MODEL


# ── String-returning LLM wrapper ──────────────────────────────────────────────

class _StrLLM:
    """
    Wraps ChatOpenAI so that .invoke() returns a plain str, matching the
    interface that the former OllamaLLM provided.
    All chain files call  llm.invoke(prompt).strip()  and expect a string.
    """

    def __init__(self, model: str, temperature: float, api_key: str):
        self.model_name = model
        self._chain = (
            ChatOpenAI(model=model, temperature=temperature, openai_api_key=api_key)
            | StrOutputParser()
        )

    def invoke(self, prompt: str) -> str:
        return self._chain.invoke(prompt)


# ── Status helpers (mirror old Ollama helpers used by api.py) ─────────────────

def is_openai_configured() -> bool:
    """Return True if OPENAI_API_KEY is set and reachable."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return False
    try:
        r = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=5,
        )
        return r.status_code == 200
    except Exception:
        return False


# Keep old names so api.py doesn't need to change its imports.
def is_ollama_running() -> bool:
    """Alias for is_openai_configured() — kept for backward compatibility."""
    return is_openai_configured()


def recommend_model() -> str:
    """Return the configured OpenAI chat model name."""
    return OPENAI_LLM_MODEL


def list_local_models() -> list[str]:
    """Return available OpenAI model IDs (or empty list on error)."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return []
    try:
        r = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=5,
        )
        data = r.json()
        return [m["id"] for m in data.get("data", [])]
    except Exception:
        return []


# ── LLM / Embeddings singletons ───────────────────────────────────────────────

_llm: _StrLLM | None = None
_embeddings: OpenAIEmbeddings | None = None


def get_llm(model: str | None = None) -> _StrLLM:
    global _llm
    resolved = model or OPENAI_LLM_MODEL
    if _llm is None or _llm.model_name != resolved:
        _llm = _StrLLM(
            model=resolved,
            temperature=0.2,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
        )
    return _llm


def get_embeddings() -> OpenAIEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            model=OPENAI_EMBED_MODEL,
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        )
    return _embeddings
