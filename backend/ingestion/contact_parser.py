"""
Contact parser — reads salesperson contact details from Excel, Word, or PDF.
Returns a dict: { normalized_name: {name, title, phone, email} }
"""
from __future__ import annotations
import re
from pathlib import Path


SalespersonRecord = dict  # keys: name, title, phone, email


def _normalize(name: str) -> str:
    return name.strip().lower()


def parse_excel(path: Path) -> dict[str, SalespersonRecord]:
    import pandas as pd

    xl = pd.ExcelFile(str(path))
    records: dict[str, SalespersonRecord] = {}

    for sheet in xl.sheet_names:
        df = xl.parse(sheet).fillna("")
        # Normalise column names
        df.columns = [str(c).strip().lower() for c in df.columns]

        col_map = {
            "name":  next((c for c in df.columns if "name" in c or "nimi" in c), None),
            "title": next((c for c in df.columns if "title" in c or "titteli" in c or "rooli" in c or "role" in c), None),
            "phone": next((c for c in df.columns if "phone" in c or "puh" in c or "puhelin" in c), None),
            "email": next((c for c in df.columns if "email" in c or "mail" in c or "sähkö" in c), None),
        }

        for _, row in df.iterrows():
            name = str(row.get(col_map["name"], "")).strip() if col_map["name"] else ""
            if not name or name.lower() in ("nan", "name", "nimi"):
                continue
            records[_normalize(name)] = {
                "name":  name,
                "title": str(row.get(col_map["title"], "")).strip() if col_map["title"] else "",
                "phone": str(row.get(col_map["phone"], "")).strip() if col_map["phone"] else "",
                "email": str(row.get(col_map["email"], "")).strip() if col_map["email"] else "",
            }
    return records


def parse_docx(path: Path) -> dict[str, SalespersonRecord]:
    from docx import Document
    doc = Document(str(path))

    # Try table-based format first
    records: dict[str, SalespersonRecord] = {}
    for table in doc.tables:
        headers = [cell.text.strip().lower() for cell in table.rows[0].cells]
        col_name  = next((i for i, h in enumerate(headers) if "name" in h or "nimi" in h), None)
        col_title = next((i for i, h in enumerate(headers) if "title" in h or "rooli" in h), None)
        col_phone = next((i for i, h in enumerate(headers) if "phone" in h or "puh" in h), None)
        col_email = next((i for i, h in enumerate(headers) if "email" in h or "mail" in h), None)

        if col_name is None:
            continue
        for row in table.rows[1:]:
            cells = row.cells
            name = cells[col_name].text.strip()
            if not name:
                continue
            records[_normalize(name)] = {
                "name":  name,
                "title": cells[col_title].text.strip() if col_title is not None else "",
                "phone": cells[col_phone].text.strip() if col_phone is not None else "",
                "email": cells[col_email].text.strip() if col_email is not None else "",
            }

    if records:
        return records

    # Fallback: paragraph-based "Name: John Smith\nEmail: ..." blocks
    email_re = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
    phone_re = re.compile(r"[\+\d][\d\s\-]{6,}")
    full_text = "\n".join(p.text for p in doc.paragraphs)
    # Group into blocks separated by blank lines
    blocks = [b.strip() for b in re.split(r"\n{2,}", full_text) if b.strip()]
    for block in blocks:
        email_m = email_re.search(block)
        phone_m = phone_re.search(block)
        lines = block.splitlines()
        name = lines[0].strip() if lines else ""
        if not name or not (email_m or phone_m):
            continue
        records[_normalize(name)] = {
            "name":  name,
            "title": "",
            "phone": phone_m.group(0).strip() if phone_m else "",
            "email": email_m.group(0).strip() if email_m else "",
        }
    return records


def parse_pdf(path: Path) -> dict[str, SalespersonRecord]:
    import pdfplumber
    records: dict[str, SalespersonRecord] = {}
    email_re = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
    phone_re = re.compile(r"[\+\d][\d\s\-]{6,}")

    with pdfplumber.open(str(path)) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    blocks = [b.strip() for b in re.split(r"\n{2,}", full_text) if b.strip()]
    for block in blocks:
        email_m = email_re.search(block)
        phone_m = phone_re.search(block)
        lines = block.splitlines()
        name = lines[0].strip() if lines else ""
        if not name or not (email_m or phone_m):
            continue
        records[_normalize(name)] = {
            "name":  name,
            "title": "",
            "phone": phone_m.group(0).strip() if phone_m else "",
            "email": email_m.group(0).strip() if email_m else "",
        }
    return records


def parse_contact_file(path: Path) -> dict[str, SalespersonRecord]:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return parse_excel(path)
    elif suffix == ".docx":
        return parse_docx(path)
    elif suffix == ".pdf":
        return parse_pdf(path)
    else:
        raise ValueError(f"Unsupported contact file format: {suffix}")


def lookup(records: dict[str, SalespersonRecord], name: str) -> SalespersonRecord | None:
    """Case-insensitive lookup by name. Returns None if not found."""
    key = _normalize(name)
    if key in records:
        return records[key]
    # Partial match
    for k, v in records.items():
        if key in k or k in key:
            return v
    return None
