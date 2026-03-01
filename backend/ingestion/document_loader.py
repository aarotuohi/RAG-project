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

    chunker = HybridChunker()
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
    import pandas as pd
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
