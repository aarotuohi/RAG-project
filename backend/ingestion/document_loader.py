"""
Document loader — dispatches files to the correct parser and indexes them into ChromaDB.
Supported formats: .docx, .pptx, .xlsx, .xls, .txt, .md, .pdf
Docling is used for rich-format files (.docx, .pptx, .pdf, .txt, .md).
Excel files fall back to a pandas-based plain-text parser.
"""
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from backend.config import CHUNK_SIZE, CHUNK_OVERLAP
from backend.vectorstore.chroma_client import get_collection

# File types handled by Docling (rich formats only)
_DOCLING_TYPES = {".docx", ".pptx", ".pdf"}

# Plain-text types read directly (no native-library dependency)
_PLAINTEXT_TYPES = {".txt", ".md"}


def load_file(file_path: Path) -> list[Document]:
    """Load a file and return a list of LangChain Document objects."""
    suffix = file_path.suffix.lower()
    if suffix in _DOCLING_TYPES:
        return _load_with_docling(file_path)
    elif suffix in _PLAINTEXT_TYPES:
        return _load_plaintext(file_path)
    elif suffix in (".xlsx", ".xls"):
        return _load_excel_as_text(file_path)
    else:
        return []


def _load_plaintext(path: Path) -> list[Document]:
    """Read a .txt or .md file directly, without any native-library dependency."""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return []
    return [Document(page_content=text, metadata={"source": str(path), "type": path.suffix.lstrip(".")})]


def _load_with_docling(path: Path) -> list[Document]:
    """
    Convert a document with Docling and chunk it using HybridChunker.
    Returns pre-chunked LangChain Documents annotated with pre_chunked=True
    so that index_file() skips the secondary RecursiveCharacterTextSplitter pass.
    """
    from docling.document_converter import DocumentConverter
    from docling.chunking import HybridChunker

    converter = DocumentConverter()
    result = converter.convert(str(path))
    docling_doc = result.document

    chunker = HybridChunker(max_tokens=400)  # keep under nomic-embed-text's 512-token limit
    lc_docs: list[Document] = []
    for chunk in chunker.chunk(docling_doc):
        text = chunk.text.strip() if hasattr(chunk, "text") else str(chunk).strip()
        if not text:
            continue
        meta: dict = {
            "source": str(path),
            "type": path.suffix.lstrip("."),
            "pre_chunked": True,
        }
        # Attach nearest heading for retrieval context if available
        try:
            if chunk.meta and chunk.meta.headings:
                meta["heading"] = chunk.meta.headings[-1]
        except AttributeError:
            pass
        lc_docs.append(Document(page_content=text, metadata=meta))
    return lc_docs


def _load_excel_as_text(path: Path) -> list[Document]:
    """
    Load an Excel file as Documents for ChromaDB indexing.
    For cost-estimation files (laskentapohja format) the structured parser
    produces cleaner, more searchable text.  Any sheet with no recognised
    step rows falls back to a plain pandas dump.
    """
    import pandas as pd

    # Try structured cost-estimation parse first
    try:
        from backend.ingestion.excel_parser import (
            parse_excel, parse_excel_metadata, steps_by_phase, grand_total,
        )
        sheet_steps = parse_excel(path)
        if sheet_steps:
            metadata = parse_excel_metadata(path)

            # Build a short project-header block prepended to every phase doc so
            # that every chunk is self-contained and carries project context.
            header_lines = []
            for key, label in [
                ("offer_number", "Offer number"), ("project_name", "Project"),
                ("customer", "Customer"), ("salesperson", "Salesperson"),
                ("date", "Date"), ("description", "Description"),
            ]:
                if metadata.get(key):
                    header_lines.append(f"{label}: {metadata[key]}")
            header = "\n".join(header_lines)

            # Companion notes file — prepended to the first phase doc
            companion = path.with_suffix(".txt")
            if not companion.exists():
                companion = path.parent / (path.stem + "_notes.txt")
            notes_prefix = ""
            if companion.exists():
                notes_text = companion.read_text(encoding="utf-8", errors="replace").strip()
                if notes_text:
                    notes_prefix = f"Project notes:\n{notes_text}\n\n"

            docs = []
            for sheet, all_steps in sheet_steps.items():
                project_total = grand_total(all_steps)
                phases = steps_by_phase(all_steps)

                for phase_idx, (phase_name, phase_steps) in enumerate(phases.items()):
                    # Each line: step name + optional description + numbers
                    step_lines = []
                    for s in phase_steps:
                        desc_part = f" | Notes: {s.description}" if s.description else ""
                        step_lines.append(
                            f"  {s.name}{desc_part}"
                            f" | Category: {s.category}"
                            f" | Rate: {s.hourly_rate}€/h"
                            f" | Hours: {s.hours}h"
                            f" | Persons: {s.persons}"
                            f" | Total: {s.total}€"
                        )
                    phase_total = round(sum(s.total for s in phase_steps), 2)

                    prefix = (notes_prefix if phase_idx == 0 else "") + (header + "\n" if header else "")
                    text = (
                        f"{prefix}"
                        f"Phase: {phase_name} | Phase total: {phase_total}€ | Project grand total: {project_total}€\n"
                        + "\n".join(step_lines)
                    )
                    docs.append(Document(
                        page_content=text,
                        metadata={
                            "source": str(path),
                            "sheet": sheet,
                            "phase": phase_name,
                            "type": "xlsx",
                            "structured": True,
                            "pre_chunked": True,  # skip RecursiveCharacterTextSplitter
                        },
                    ))
            return docs
    except Exception:
        pass  # fall through to plain text

    # Fallback: plain pandas dump
    docs = []
    xl = pd.ExcelFile(str(path))
    for sheet in xl.sheet_names:
        df = xl.parse(sheet).fillna("")
        text = f"Sheet: {sheet}\n" + df.to_string(index=False)
        docs.append(Document(page_content=text, metadata={"source": str(path), "sheet": sheet, "type": "xlsx"}))
    return docs


async def _load_url(url: str) -> list[Document]:
    """Fetch a URL with crawl4ai and return a Document with markdown content."""
    from crawl4ai import AsyncWebCrawler
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        text = result.markdown or result.cleaned_html or ""
        if not text.strip():
            return []
        return [Document(page_content=text, metadata={"source": url, "type": "url"})]


async def index_url(url: str, collection_name: str, extra_metadata: dict | None = None) -> int:
    """
    Scrape a URL with crawl4ai, chunk the content, and index it into the specified ChromaDB collection.
    Returns the number of chunks added.
    """
    raw_docs = await _load_url(url)
    if not raw_docs:
        return 0

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(raw_docs)

    if extra_metadata:
        for chunk in chunks:
            chunk.metadata.update(extra_metadata)

    collection = get_collection(collection_name)
    collection.add_documents(chunks)
    return len(chunks)


def index_file(file_path: Path, collection_name: str, extra_metadata: dict | None = None) -> int:
    """
    Load, chunk, and index a file into the specified ChromaDB collection.
    Returns the number of chunks added.
    Files parsed by Docling are already chunked (pre_chunked=True) and skip re-splitting.
    """
    raw_docs = load_file(file_path)
    if not raw_docs:
        return 0

    # Docling's HybridChunker already produced optimal chunks — skip re-splitting
    if raw_docs[0].metadata.get("pre_chunked"):
        chunks = raw_docs
    else:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        chunks = splitter.split_documents(raw_docs)

    if extra_metadata:
        for chunk in chunks:
            chunk.metadata.update(extra_metadata)

    collection = get_collection(collection_name)
    collection.add_documents(chunks)
    return len(chunks)


def index_directory(directory: Path, collection_name: str, extra_metadata: dict | None = None) -> dict:
    """Index all supported files in a directory. Returns {filename: chunk_count}."""
    results = {}
    supported = {".docx", ".pptx", ".xlsx", ".xls", ".txt", ".md", ".pdf"}
    for f in directory.iterdir():
        if f.is_file() and f.suffix.lower() in supported:
            count = index_file(f, collection_name, extra_metadata)
            results[f.name] = count
    return results
