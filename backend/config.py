
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # loads .env from project root (if present)

# ── Base paths ────────────────────────────────────────────────────────────────
BASE_DIR = Path(os.environ.get("AISALES_BASE_DIR", Path(__file__).parent.parent / "data"))
DOCUMENTS_DIR   = BASE_DIR / "documents"
VECTORSTORE_DIR = BASE_DIR / "vectorstore"
OUTPUTS_DIR     = BASE_DIR / "outputs"
TEMPLATES_DIR   = Path(__file__).parent.parent / "templates"

# Sub-folders inside documents/
COST_HISTORY_DIR = DOCUMENTS_DIR / "cost_history"
CV_DIR           = DOCUMENTS_DIR / "cvs"
CONTACTS_DIR     = DOCUMENTS_DIR / "contacts"
BOILERPLATE_DIR  = DOCUMENTS_DIR / "boilerplate"
TRANSCRIPTS_DIR  = DOCUMENTS_DIR / "transcripts"

SETTINGS_FILE = BASE_DIR / "settings.json"

# Create all directories on import
for _d in [
    DOCUMENTS_DIR, VECTORSTORE_DIR, OUTPUTS_DIR,
    COST_HISTORY_DIR, CV_DIR, CONTACTS_DIR, BOILERPLATE_DIR, TRANSCRIPTS_DIR,
]:
    _d.mkdir(parents=True, exist_ok=True)

# Ollama settings
OLLAMA_BASE_URL    = os.environ.get("OLLAMA_BASE_URL",   "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL      = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251022")
ANTHROPIC_MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "4096"))

# Available Anthropic models exposed in the UI dropdown
AVAILABLE_ANTHROPIC_MODELS: list[dict] = [
    {"id": "claude-haiku-4-5-20251022",  "label": "Claude Haiku 4.5  (fast)"},
    {"id": "claude-sonnet-4-5-20251022", "label": "Claude Sonnet 4.5 (balanced)"},
    {"id": "claude-sonnet-4-20250514",   "label": "Claude Sonnet 4   (powerful)"},
    {"id": "claude-opus-4-20250514",     "label": "Claude Opus 4     (strongest)"},
]

# Runtime-mutable active model (changed via /api/set-model; starts from env/default above)
_active_anthropic_model: str = ANTHROPIC_MODEL

# ChromaDB settings 
CHROMA_COLLECTION_COST     = "cost_history"
CHROMA_COLLECTION_CV       = "cv_database"
CHROMA_COLLECTION_BOILER   = "boilerplate"
CHROMA_COLLECTION_CONTACTS = "sales_contacts"

# Text splitting
CHUNK_SIZE    = 400   # ~400 tokens — stays within nomic-embed-text's 512-token context window
CHUNK_OVERLAP = 80

# Cost estimation work categories and their standard hourly rates (€/h)
WORK_CATEGORIES = [
    "Project leading",
    "Research",
    "Service development",
    "Software development",
    "Electronics design",
    "Mechanics design",
    "Industrial design",
]

CATEGORY_RATES: dict[str, int] = {
    "Project leading":    110,
    "Research":           110,
    "Service development":  90,
    "Software development": 90,
    "Electronics design":   90,
    "Mechanics design":     90,
    "Industrial design":    90,
}

#Boilerplate filenames (inside BOILERPLATE_DIR) — one file per key per language.
# Lookup order: language-specific file first, then "en" fallback, then bare filename.
BOILERPLATE_FILES: dict[str, dict[str, str]] = {
    "documentation": {"fi": "documentation_fi.txt", "en": "documentation_en.txt"},
    "quality":       {"fi": "quality_assurance_fi.txt", "en": "quality_assurance_en.txt"},
    "delivery":      {"fi": "delivery_terms_fi.txt", "en": "delivery_terms_en.txt"},
    "payment":       {"fi": "payment_agreement_fi.txt", "en": "payment_agreement_en.txt"},
}
