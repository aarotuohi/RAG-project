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

from backend.config import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_MAX_TOKENS
import backend.config as _cfg


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

# ── Anthropic connectivity probe ──────────────────────────────────────────────

_anthropic_probe_cache: tuple[float, bool, str] | None = None  # (timestamp, ok, detail)
_ANTHROPIC_PROBE_TTL = 60.0  # seconds


def is_anthropic_reachable() -> tuple[bool, str]:
    """
    Lightweight probe that validates the Anthropic API key and network reachability
    using the zero-cost `count_tokens` endpoint (no tokens are generated).
    Result is cached for 60 s so repeated /api/status polls are cheap.
    Returns (ok: bool, detail: str).
    """
    global _anthropic_probe_cache

    if not ANTHROPIC_API_KEY:
        return False, "ANTHROPIC_API_KEY is not set"

    # Return cached result if still fresh
    if _anthropic_probe_cache is not None:
        ts, ok, detail = _anthropic_probe_cache
        if time.monotonic() - ts < _ANTHROPIC_PROBE_TTL:
            return ok, detail

    try:
        import anthropic  # soft import — only needed here
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        client.messages.count_tokens(
            model=ANTHROPIC_MODEL,
            messages=[{"role": "user", "content": "ping"}],
        )
        result = (True, "ok")
    except Exception as exc:
        msg = str(exc)
        # Surface the most useful part of common errors without leaking the key
        if "401" in msg or "authentication" in msg.lower() or "invalid" in msg.lower():
            detail = "invalid API key (401)"
        elif "403" in msg:
            detail = "forbidden (403) — check org/project permissions"
        elif "Connection" in msg or "connect" in msg.lower():
            detail = "network unreachable"
        else:
            detail = msg[:120]  # truncate, never expose full traceback
        result = (False, detail)

    _anthropic_probe_cache = (time.monotonic(), *result)
    return result


def get_llm(**kwargs):
    global _llm
    # Rebuild if the active model changed since the last call
    current_model = _cfg._active_anthropic_model
    if _llm is None or getattr(_llm, "_aisales_model", None) != current_model:
        chain = ChatAnthropic(
            model=current_model,
            api_key=ANTHROPIC_API_KEY,
            temperature=0.2,
            max_tokens=ANTHROPIC_MAX_TOKENS,
        ) | StrOutputParser()
        chain._aisales_model = current_model  # type: ignore[attr-defined]
        _llm = chain
    return _llm


def set_active_model(model_id: str) -> None:
    """Switch the active Anthropic model at runtime and invalidate the cached LLM."""
    global _llm
    _cfg._active_anthropic_model = model_id
    _llm = None  # force rebuild on next get_llm() call


def get_embeddings() -> OllamaEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    return _embeddings
