import os
import re
import zlib
import zipfile
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

# Attempt optional import of pypdf (not required; pure-python fallback provided)
try:
    import pypdf
    _HAS_PYPDF = True
except ImportError:
    pypdf = None
    _HAS_PYPDF = False

SUPPORTED_EXTENSIONS = {
    ".txt", ".md",
    ".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".cpp", ".c", ".h", ".json", ".css", ".html",
    ".docx",
    ".pdf"
}

CODE_EXTENSIONS = {
    ".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".cpp", ".c", ".h", ".json", ".css", ".html"
}

LANGUAGE_MAP = {
    ".py": "Python",
    ".java": "Java",
    ".js": "JavaScript",
    ".jsx": "React (JSX)",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (TSX)",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".json": "JSON",
    ".css": "CSS",
    ".html": "HTML"
}


@dataclass
class ExtractedDocument:
    """
    Standardized extracted document container.
    """
    path: str
    filename: str
    extension: str
    size_bytes: int
    content_hash: str
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "SUCCESS"  # "SUCCESS", "WARNING", "ERROR"
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def compute_file_hash(path: str) -> str:
    """Computes SHA-256 hash of file content."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_file(path: str) -> ExtractedDocument:
    """
    Extracts text and structured metadata from local documents and source code files.
    100% On-Device & Zero-Cloud: No remote API or network calls are ever made.
    """
    if not os.path.exists(path):
        return ExtractedDocument(
            path=path,
            filename=os.path.basename(path),
            extension=os.path.splitext(path)[1].lower(),
            size_bytes=0,
            content_hash="",
            status="ERROR",
            error_message=f"File does not exist: {path}"
        )

    filename = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    size_bytes = os.path.getsize(path)

    # Validate extension
    if ext not in SUPPORTED_EXTENSIONS:
        return ExtractedDocument(
            path=path,
            filename=filename,
            extension=ext,
            size_bytes=size_bytes,
            content_hash="",
            status="ERROR",
            error_message=f"Unsupported file extension '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    try:
        content_hash = compute_file_hash(path)
    except Exception as e:
        return ExtractedDocument(
            path=path,
            filename=filename,
            extension=ext,
            size_bytes=size_bytes,
            content_hash="",
            status="ERROR",
            error_message=f"Failed to read file hash: {str(e)}"
        )

    # Empty file handling
    if size_bytes == 0:
        return ExtractedDocument(
            path=path,
            filename=filename,
            extension=ext,
            size_bytes=0,
            content_hash=content_hash,
            text="",
            metadata={"empty": True},
            status="SUCCESS",
            warnings=["File is empty (0 bytes)."]
        )

    # Route by file category
    if ext in [".txt", ".md"]:
        return _extract_plain_text(path, filename, ext, size_bytes, content_hash)
    elif ext in CODE_EXTENSIONS:
        return _extract_code_file(path, filename, ext, size_bytes, content_hash)
    elif ext == ".docx":
        return _extract_docx_file(path, filename, ext, size_bytes, content_hash)
    elif ext == ".pdf":
        return _extract_pdf_file(path, filename, ext, size_bytes, content_hash)

    return ExtractedDocument(
        path=path,
        filename=filename,
        extension=ext,
        size_bytes=size_bytes,
        content_hash=content_hash,
        status="ERROR",
        error_message=f"Unrecognized handler for extension: {ext}"
    )


def _extract_plain_text(
    path: str, filename: str, ext: str, size_bytes: int, content_hash: str
) -> ExtractedDocument:
    """Extracts text from .txt and .md files with encoding fallback."""
    raw_text = ""
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    success = False
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                raw_text = f.read()
            success = True
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if not success:
        return ExtractedDocument(
            path=path,
            filename=filename,
            extension=ext,
            size_bytes=size_bytes,
            content_hash=content_hash,
            status="ERROR",
            error_message=f"Failed to decode text file with supported encodings ({', '.join(encodings)})"
        )

    # Detect Markdown headings
    headings = []
    if ext == ".md":
        headings = re.findall(r'^(#{1,6}\s+.+)$', raw_text, re.MULTILINE)

    return ExtractedDocument(
        path=path,
        filename=filename,
        extension=ext,
        size_bytes=size_bytes,
        content_hash=content_hash,
        text=raw_text,
        metadata={"headings": headings, "line_count": len(raw_text.splitlines())},
        status="SUCCESS"
    )


def _extract_code_file(
    path: str, filename: str, ext: str, size_bytes: int, content_hash: str
) -> ExtractedDocument:
    """Extracts source code and analyzes classes, methods, and functions."""
    raw_text = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw_text = f.read()
    except Exception as e:
        return ExtractedDocument(
            path=path, filename=filename, extension=ext, size_bytes=size_bytes,
            content_hash=content_hash, status="ERROR", error_message=str(e)
        )

    language = LANGUAGE_MAP.get(ext, "Code")
    class_names = []
    function_names = []

    if ext == ".py":
        class_names = re.findall(r'^\s*class\s+([A-Za-z0-9_]+)', raw_text, re.MULTILINE)
        function_names = re.findall(r'^\s*def\s+([A-Za-z0-9_]+)', raw_text, re.MULTILINE)
    elif ext == ".java":
        class_names = re.findall(r'(?:class|interface|record|enum)\s+([A-Za-z0-9_]+)', raw_text)
        function_names = re.findall(
            r'(?:public|private|protected|static|final|\s)+[\w<>\[\], ]+\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{',
            raw_text
        )
    elif ext in [".js", ".jsx", ".ts", ".tsx"]:
        class_names = re.findall(r'class\s+([A-Za-z0-9_]+)', raw_text)
        func_defs = re.findall(r'(?:function\s+([A-Za-z0-9_]+)|(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)', raw_text)
        for pair in func_defs:
            name = pair[0] or pair[1]
            if name:
                function_names.append(name)
    elif ext in [".c", ".cpp", ".h"]:
        class_names = re.findall(r'(?:class|struct)\s+([A-Za-z0-9_]+)', raw_text)
        function_names = re.findall(r'[\w*&]+\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{', raw_text)

    # Deduplicate while preserving order
    class_names = list(dict.fromkeys(class_names))
    function_names = list(dict.fromkeys(function_names))

    return ExtractedDocument(
        path=path,
        filename=filename,
        extension=ext,
        size_bytes=size_bytes,
        content_hash=content_hash,
        text=raw_text,
        metadata={
            "language": language,
            "class_names": class_names,
            "function_names": function_names,
            "line_count": len(raw_text.splitlines())
        },
        status="SUCCESS"
    )


def _extract_docx_file(
    path: str, filename: str, ext: str, size_bytes: int, content_hash: str
) -> ExtractedDocument:
    """
    Extracts text and structure from Word .docx files using standard library zipfile
    and xml.etree.ElementTree DOM parsing. No regex hacks or external dependencies.
    """
    if not zipfile.is_zipfile(path):
        return ExtractedDocument(
            path=path, filename=filename, extension=ext, size_bytes=size_bytes,
            content_hash=content_hash, status="ERROR",
            error_message="Corrupted or invalid DOCX archive (not a valid zip file)."
        )

    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns = {"w": w_ns}

    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "word/document.xml" not in zf.namelist():
                return ExtractedDocument(
                    path=path, filename=filename, extension=ext, size_bytes=size_bytes,
                    content_hash=content_hash, status="ERROR",
                    error_message="Invalid DOCX structure: word/document.xml missing."
                )
            xml_bytes = zf.read("word/document.xml")

        root = ET.fromstring(xml_bytes)
    except Exception as e:
        return ExtractedDocument(
            path=path, filename=filename, extension=ext, size_bytes=size_bytes,
            content_hash=content_hash, status="ERROR",
            error_message=f"Failed to parse DOCX XML: {str(e)}"
        )

    paragraphs = []
    headings = []

    for elem in root.iter():
        tag = elem.tag
        if tag == f"{{{w_ns}}}p":
            p_style = ""
            style_elem = elem.find(".//w:pStyle", ns)
            if style_elem is not None:
                p_style = style_elem.attrib.get(f"{{{w_ns}}}val", "")

            p_text_parts = []
            for text_elem in elem.iter():
                if text_elem.tag == f"{{{w_ns}}}t":
                    if text_elem.text:
                        p_text_parts.append(text_elem.text)
                elif text_elem.tag == f"{{{w_ns}}}tab":
                    p_text_parts.append("\t")
                elif text_elem.tag == f"{{{w_ns}}}br":
                    p_text_parts.append("\n")

            p_text = "".join(p_text_parts).strip()
            if p_text:
                paragraphs.append(p_text)
                if "heading" in p_style.lower() or "title" in p_style.lower():
                    headings.append(p_text)

        elif tag == f"{{{w_ns}}}tbl":
            # Extract table rows
            for tr in elem.findall(".//w:tr", ns):
                row_cells = []
                for tc in tr.findall(".//w:tc", ns):
                    cell_text = "".join(tc.itertext()).strip()
                    row_cells.append(cell_text)
                if any(row_cells):
                    paragraphs.append(" | ".join(row_cells))

    full_text = "\n\n".join(paragraphs)

    return ExtractedDocument(
        path=path,
        filename=filename,
        extension=ext,
        size_bytes=size_bytes,
        content_hash=content_hash,
        text=full_text,
        metadata={
            "headings": headings,
            "paragraph_count": len(paragraphs)
        },
        status="SUCCESS"
    )


def _extract_pdf_file(
    path: str, filename: str, ext: str, size_bytes: int, content_hash: str
) -> ExtractedDocument:
    """
    Extracts text from PDF files using local pure-Python stream/FlateDecode decompression.
    If pypdf is installed, uses it for accelerated parsing; otherwise uses built-in zlib parser.
    """
    # Quick header check
    try:
        with open(path, "rb") as f:
            header = f.read(5)
            if not header.startswith(b"%PDF-"):
                return ExtractedDocument(
                    path=path, filename=filename, extension=ext, size_bytes=size_bytes,
                    content_hash=content_hash, status="ERROR",
                    error_message="Invalid or corrupted PDF file (missing %PDF- header)."
                )
    except Exception as e:
        return ExtractedDocument(
            path=path, filename=filename, extension=ext, size_bytes=size_bytes,
            content_hash=content_hash, status="ERROR",
            error_message=f"Could not read PDF header: {str(e)}"
        )

    # Strategy 1: pypdf if available
    if _HAS_PYPDF and pypdf:
        try:
            reader = pypdf.PdfReader(path)
            extracted_pages = []
            for idx, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    extracted_pages.append(page_text.strip())

            full_text = "\n\n".join(extracted_pages)
            return ExtractedDocument(
                path=path,
                filename=filename,
                extension=ext,
                size_bytes=size_bytes,
                content_hash=content_hash,
                text=full_text,
                metadata={
                    "parser": "pypdf",
                    "page_count": len(reader.pages)
                },
                status="SUCCESS"
            )
        except Exception as e:
            # Fall back to pure-python parser on error
            pass

    # Strategy 2: Robust Built-In Pure Python Stream Parser
    try:
        with open(path, "rb") as f:
            pdf_bytes = f.read()

        # Extract streams
        stream_pattern = re.compile(rb'stream\r?\n(.*?)\r?\nendstream', re.DOTALL)
        dict_pattern = re.compile(rb'<<([^>]*)>>\s*stream', re.DOTALL)

        extracted_text_blocks = []
        stream_matches = list(stream_pattern.finditer(pdf_bytes))

        for match in stream_matches:
            raw_stream = match.group(1)
            stream_start = match.start()

            # Inspect preceding dictionary for /Filter /FlateDecode
            preceding_chunk = pdf_bytes[max(0, stream_start - 256):stream_start]
            is_flate = b'/FlateDecode' in preceding_chunk

            decompressed_data = None
            if is_flate:
                try:
                    decompressed_data = zlib.decompress(raw_stream)
                except Exception:
                    # Some streams omit zlib headers; try raw inflate
                    try:
                        decompressed_data = zlib.decompress(raw_stream, -zlib.MAX_WBITS)
                    except Exception:
                        decompressed_data = None
            else:
                decompressed_data = raw_stream

            if decompressed_data:
                # Parse text operators: BT ... ET
                text_content = _parse_pdf_content_stream(decompressed_data)
                if text_content.strip():
                    extracted_text_blocks.append(text_content.strip())

        full_text = "\n\n".join(extracted_text_blocks)

        warnings = []
        if not full_text.strip():
            warnings.append("No extractable text found in PDF (may be scanned image or complex font encoding).")

        return ExtractedDocument(
            path=path,
            filename=filename,
            extension=ext,
            size_bytes=size_bytes,
            content_hash=content_hash,
            text=full_text,
            metadata={
                "parser": "builtin_pure_python_flate",
                "stream_count": len(stream_matches)
            },
            status="SUCCESS" if full_text.strip() else "WARNING",
            warnings=warnings
        )
    except Exception as e:
        return ExtractedDocument(
            path=path,
            filename=filename,
            extension=ext,
            size_bytes=size_bytes,
            content_hash=content_hash,
            status="ERROR",
            error_message=f"PDF extraction error: {str(e)}"
        )


def _parse_pdf_content_stream(stream_bytes: bytes) -> str:
    """Parses text operators (Tj, TJ, ', \") within BT...ET blocks in PDF content stream."""
    text_pieces = []
    # Find all BT ... ET text blocks
    bt_et_blocks = re.findall(rb'BT\s*(.*?)\s*ET', stream_bytes, re.DOTALL)

    for block in bt_et_blocks:
        # Match single text show: (Text) Tj, (Text) ', (Text) "
        tj_matches = re.findall(rb'\((.*?)\)\s*(?:Tj|\'|")', block, re.DOTALL)
        for m in tj_matches:
            decoded = _decode_pdf_string(m)
            if decoded:
                text_pieces.append(decoded)

        # Match array text show: [(Text)-120(More)] TJ
        array_matches = re.findall(rb'\[(.*?)\]\s*TJ', block, re.DOTALL)
        for arr in array_matches:
            items = re.findall(rb'\((.*?)\)', arr, re.DOTALL)
            row = "".join(_decode_pdf_string(item) for item in items)
            if row.strip():
                text_pieces.append(row.strip())

    return " ".join(text_pieces)


def _decode_pdf_string(raw: bytes) -> str:
    """Decodes standard PDF string escapes (octal escapes, parens, newlines)."""
    try:
        s = raw.decode("latin-1", errors="ignore")
    except Exception:
        return ""

    # Replace octal escapes \ooo
    def replace_octal(match):
        oct_str = match.group(1)
        return chr(int(oct_str, 8))

    s = re.sub(r'\\([0-7]{1,3})', replace_octal, s)
    s = s.replace(r'\(', '(').replace(r'\)', ')').replace(r'\\', '\\')
    s = s.replace(r'\n', '\n').replace(r'\r', '\r').replace(r'\t', '\t')
    return s
