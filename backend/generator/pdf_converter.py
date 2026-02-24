"""
PDF converter — converts a .docx file to .pdf using Microsoft Word COM automation (Windows only).
Falls back to LibreOffice headless if Word is not installed.
"""
from __future__ import annotations
from pathlib import Path
import subprocess
import sys


def convert_to_pdf(docx_path: Path) -> Path:
    """Convert a .docx file to .pdf. Returns the path of the generated .pdf."""
    pdf_path = docx_path.with_suffix(".pdf")

    if sys.platform == "win32":
        if _convert_with_word(docx_path, pdf_path):
            return pdf_path
    if _convert_with_libreoffice(docx_path, pdf_path):
        return pdf_path

    raise RuntimeError(
        "PDF conversion failed. Please install Microsoft Word or LibreOffice."
    )


def _convert_with_word(docx_path: Path, pdf_path: Path) -> bool:
    """Use Word COM automation (Windows only)."""
    try:
        import comtypes.client  # type: ignore
        word = comtypes.client.CreateObject("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(docx_path.resolve()))
        doc.SaveAs(str(pdf_path.resolve()), FileFormat=17)  # 17 = wdFormatPDF
        doc.Close()
        word.Quit()
        return pdf_path.exists()
    except Exception:
        return False


def _convert_with_libreoffice(docx_path: Path, pdf_path: Path) -> bool:
    """Use LibreOffice headless as a fallback."""
    try:
        result = subprocess.run(
            [
                "soffice", "--headless", "--convert-to", "pdf",
                "--outdir", str(docx_path.parent),
                str(docx_path),
            ],
            capture_output=True,
            timeout=60,
        )
        return result.returncode == 0 and pdf_path.exists()
    except Exception:
        return False
