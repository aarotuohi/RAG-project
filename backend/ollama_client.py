"""
Ollama client — wraps LangChain OllamaLLM + OllamaEmbeddings.
Provides helpers for startup checks and automatic model selection.
"""
import subprocess
import time
import requests
import platform
from langchain_ollama import OllamaLLM, OllamaEmbeddings

import backend.config as _cfg
from backend.config import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL


def _get_vram_gb() -> float:
    """Return available VRAM in GB from the first NVIDIA GPU, or 0 if none."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            text=True, timeout=5,
        )
        return float(out.strip().split("\n")[0]) / 1024
    except Exception:
        return 0.0


def recommend_model() -> str:
    """Choose the best Ollama LLM model based on detected VRAM.

    Conservative thresholds include a ~20% safety margin above model weight size:
      14b q4_K_M needs ~9 GB  → require 10 GB
      32b q4_K_M needs ~20 GB → require 24 GB
      70b q4_K_M needs ~40 GB → require 48 GB
    """
    vram = _get_vram_gb()
    if vram >= 48:
        return "llama3.3:70b-instruct-q4_K_M"
    elif vram >= 24:
        return "qwen2.5:32b-instruct-q4_K_M"
    elif vram >= 10:
        return "qwen2.5:14b-instruct-q4_K_M"
    else:
        return "qwen2.5:7b-instruct-q4_K_M"

 
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


_llm: OllamaLLM | None = None
_embeddings: OllamaEmbeddings | None = None


def get_llm(model: str | None = None) -> OllamaLLM:
    global _llm
    # Use live cfg value so main.py startup model selection takes effect
    resolved = model or _cfg.OLLAMA_LLM_MODEL
    if _llm is None or _llm.model != resolved:
        # num_ctx cap prevents Ollama from allocating a massive KV-cache
        # (Qwen2.5 defaults to 128k context which exhausts VRAM and causes
        # "llama runner process has terminated" even when model weights fit)
        _llm = OllamaLLM(model=resolved, base_url=OLLAMA_BASE_URL, temperature=0.2, num_ctx=8192)
    return _llm


def get_embeddings() -> OllamaEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    return _embeddings
