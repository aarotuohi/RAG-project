"""
Ollama client — wraps LangChain OllamaLLM + OllamaEmbeddings.
Provides helpers for startup checks and automatic model selection.
"""
import subprocess
import time
import requests
import platform
from langchain_ollama import OllamaEmbeddings
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import StrOutputParser

from backend.config import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_MAX_TOKENS, ANTHROPIC_MAX_TOKENS


def _get_available_ram_gb() -> float:
    """Return available (free) system RAM in GB."""
    try:
        import psutil
        return psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        return 999.0  # assume enough if psutil not installed


def recommend_model() -> str:
    """Return the configured LLM model."""
    return "qwen2.5:14b-instruct-q4_K_M"


def is_ollama_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def ensure_ollama_running():
    """Start Ollama server as a background process if not already running."""
    if is_ollama_running():
        return
    if platform.system() == "Windows":
        subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        time.sleep(1)
        if is_ollama_running():
            return
    raise RuntimeError("Ollama did not start within 20 seconds.")


def list_local_models() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        data = r.json()
        # Ollama <0.3 used "name", ≥0.3 uses "model" — support both
        return [
            m.get("name") or m.get("model", "")
            for m in data.get("models", [])
            if m.get("name") or m.get("model")
        ]
    except Exception:
        return []


def pull_model_if_missing(model_name: str):
    """Pull an Ollama model if it is not already downloaded."""
    local = list_local_models()
    # Match by prefix (ignore quantization tag differences)
    if any(model_name.split(":")[0] in m for m in local):
        return
    subprocess.run(["ollama", "pull", model_name], check=True)


_llm = None
_embeddings: OllamaEmbeddings | None = None


def get_llm(**kwargs):
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(
            model=ANTHROPIC_MODEL,
            api_key=ANTHROPIC_API_KEY,
            temperature=0.2,
            max_tokens=ANTHROPIC_MAX_TOKENS,
        ) | StrOutputParser()
    return _llm


def get_embeddings() -> OllamaEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    return _embeddings
