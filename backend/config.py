
import os
from pathlib import Path

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
OLLAMA_LLM_MODEL   = os.environ.get("OLLAMA_LLM_MODEL",  "qwen2.5:14b")   # overridden at startup
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# ChromaDB settings 
CHROMA_COLLECTION_COST     = "cost_history"
CHROMA_COLLECTION_CV       = "cv_database"
CHROMA_COLLECTION_BOILER   = "boilerplate"
CHROMA_COLLECTION_CONTACTS = "sales_contacts"

# Text splitting
CHUNK_SIZE    = 400   # ~400 tokens — stays within nomic-embed-text's 512-token context window
CHUNK_OVERLAP = 80

# Cost estimation work categories
WORK_CATEGORIES = ["Services", "Mechanics", "Software", "Research", "Electronics", "Design"]

#Boilerplate filenames (inside BOILERPLATE_DIR) 
BOILERPLATE_FILES = {
    "documentation": "documentation.txt",
    "quality":       "quality_assurance.txt",
    "delivery":      "delivery_terms.txt",
    "payment":       "payment_agreement.txt",
}
