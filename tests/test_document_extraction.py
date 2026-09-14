import os
import sys
import unittest
import tempfile
import json
import zipfile
import socket
import urllib.request
from unittest.mock import patch

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.documents.extractors import extract_file, compute_file_hash, ExtractedDocument


def create_minimal_docx(filepath: str, heading: str = "Test Heading", paragraph: str = "Test paragraph content."):
    """Creates a minimal valid OpenXML .docx file without third-party dependencies."""
    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="xml" ContentType="application/xml"/>\n'
        '  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>\n'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>\n'
        '</Relationships>'
    )
    doc_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:document xmlns:w="{w_ns}">\n'
        f'  <w:body>\n'
        f'    <w:p>\n'
        f'      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>\n'
        f'      <w:r><w:t>{heading}</w:t></w:r>\n'
        f'    </w:p>\n'
        f'    <w:p>\n'
        f'      <w:r><w:t>{paragraph}</w:t></w:r>\n'
        f'    </w:p>\n'
        f'  </w:body>\n'
        f'</w:document>'
    )

    with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', rels)
        zf.writestr('word/document.xml', doc_xml)


def create_minimal_pdf(filepath: str, text: str = "Hello AIGIS Local Document Ingestion"):
    """Creates a minimal valid text PDF file without external dependencies."""
    stream_content = f"BT\n/F1 12 Tf\n72 712 Td\n({text}) Tj\nET\n"
    stream_len = len(stream_content.encode("latin-1"))

    pdf_content = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        f"4 0 obj\n<< /Length {stream_len} >>\nstream\n{stream_content}endstream\nendobj\n"
        "xref\n0 5\n"
        "0000000000 65535 f \n"
        "0000000009 00000 n \n"
        "0000000058 00000 n \n"
        "0000000115 00000 n \n"
        "0000000204 00000 n \n"
        "trailer\n<< /Size 5 /Root 1 0 R >>\n"
        "startxref\n350\n%%EOF\n"
    )

    with open(filepath, "wb") as f:
        f.write(pdf_content.encode("latin-1"))


class TestDocumentExtraction(unittest.TestCase):
    """
    Test suite for Milestone 7 Step 3: Local Document & Code Extraction.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # 1. TXT extraction
    def test_01_txt_extraction(self):
        path = os.path.join(self.temp_dir.name, "sample.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("AIGIS local document intelligence pipeline.\nLine two of plain text.")

        doc = extract_file(path)
        self.assertEqual(doc.status, "SUCCESS")
        self.assertEqual(doc.extension, ".txt")
        self.assertIn("AIGIS local document intelligence", doc.text)
        self.assertEqual(doc.metadata.get("line_count"), 2)
        self.assertTrue(len(doc.content_hash) > 10)

    # 2. Markdown extraction
    def test_02_markdown_extraction(self):
        path = os.path.join(self.temp_dir.name, "readme.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Architecture Overview\n\nThis is a Markdown doc.\n\n## Subheading Details\nMore notes.")

        doc = extract_file(path)
        self.assertEqual(doc.status, "SUCCESS")
        self.assertEqual(doc.extension, ".md")
        self.assertIn("# Architecture Overview", doc.text)
        self.assertIn("# Architecture Overview", doc.metadata.get("headings", []))
        self.assertIn("## Subheading Details", doc.metadata.get("headings", []))

    # 3. Python extraction
    def test_03_python_extraction(self):
        path = os.path.join(self.temp_dir.name, "service.py")
        code = (
            "class LocalMemoryManager:\n"
            "    def __init__(self):\n"
            "        self.active = True\n\n"
            "    def store_item(self, key, val):\n"
            "        return True\n\n"
            "def standalone_function():\n"
            "    return 'ready'\n"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)

        doc = extract_file(path)
        self.assertEqual(doc.status, "SUCCESS")
        self.assertEqual(doc.metadata.get("language"), "Python")
        self.assertIn("LocalMemoryManager", doc.metadata.get("class_names", []))
        self.assertIn("__init__", doc.metadata.get("function_names", []))
        self.assertIn("store_item", doc.metadata.get("function_names", []))
        self.assertIn("standalone_function", doc.metadata.get("function_names", []))

    # 4. Java extraction
    def test_04_java_extraction(self):
        path = os.path.join(self.temp_dir.name, "ChatService.java")
        code = (
            "package com.aigis.service;\n\n"
            "public class ChatService {\n"
            "    public String generateReply(String prompt) {\n"
            "        return \"AIGIS reply\";\n"
            "    }\n"
            "}\n"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)

        doc = extract_file(path)
        self.assertEqual(doc.status, "SUCCESS")
        self.assertEqual(doc.metadata.get("language"), "Java")
        self.assertIn("ChatService", doc.metadata.get("class_names", []))
        self.assertIn("generateReply", doc.metadata.get("function_names", []))

    # 5. JSON extraction
    def test_05_json_extraction(self):
        path = os.path.join(self.temp_dir.name, "data.json")
        payload = {"app": "AIGIS", "version": "1.2.0", "offline": True}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        doc = extract_file(path)
        self.assertEqual(doc.status, "SUCCESS")
        self.assertEqual(doc.extension, ".json")
        self.assertIn('"app": "AIGIS"', doc.text)

    # 6. DOCX extraction
    def test_06_docx_extraction(self):
        path = os.path.join(self.temp_dir.name, "document.docx")
        create_minimal_docx(path, heading="System Specifications", paragraph="AIGIS operates on-device.")

        doc = extract_file(path)
        self.assertEqual(doc.status, "SUCCESS")
        self.assertEqual(doc.extension, ".docx")
        self.assertIn("System Specifications", doc.text)
        self.assertIn("AIGIS operates on-device.", doc.text)
        self.assertIn("System Specifications", doc.metadata.get("headings", []))

    # 7. PDF extraction
    def test_07_pdf_extraction(self):
        path = os.path.join(self.temp_dir.name, "document.pdf")
        create_minimal_pdf(path, text="AIGIS Robust Local PDF Reader")

        doc = extract_file(path)
        self.assertEqual(doc.status, "SUCCESS")
        self.assertEqual(doc.extension, ".pdf")
        self.assertIn("AIGIS Robust Local PDF Reader", doc.text)

    # 8. Unicode content
    def test_08_unicode_content(self):
        path = os.path.join(self.temp_dir.name, "multilingual.txt")
        unicode_str = "English text, Café résumé, 日本語テキスト, 中文, 🚀⚡🔒"
        with open(path, "w", encoding="utf-8") as f:
            f.write(unicode_str)

        doc = extract_file(path)
        self.assertEqual(doc.status, "SUCCESS")
        self.assertIn("Café résumé", doc.text)
        self.assertIn("日本語テキスト", doc.text)
        self.assertIn("🚀⚡🔒", doc.text)

    # 9. Empty file
    def test_09_empty_file(self):
        path = os.path.join(self.temp_dir.name, "empty.txt")
        with open(path, "w", encoding="utf-8") as f:
            pass

        doc = extract_file(path)
        self.assertEqual(doc.status, "SUCCESS")
        self.assertEqual(doc.text, "")
        self.assertEqual(doc.size_bytes, 0)
        self.assertTrue(doc.metadata.get("empty"))

    # 10. Large file
    def test_10_large_file(self):
        path = os.path.join(self.temp_dir.name, "large.txt")
        large_content = "\n".join([f"Line {i}: Standard system documentation paragraph." for i in range(1000)])
        with open(path, "w", encoding="utf-8") as f:
            f.write(large_content)

        doc = extract_file(path)
        self.assertEqual(doc.status, "SUCCESS")
        self.assertEqual(doc.metadata.get("line_count"), 1000)
        self.assertIn("Line 999", doc.text)

    # 11. Corrupt DOCX
    def test_11_corrupt_docx(self):
        path = os.path.join(self.temp_dir.name, "corrupt.docx")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Not a zip file content.")

        doc = extract_file(path)
        self.assertEqual(doc.status, "ERROR")
        self.assertIn("Corrupted or invalid DOCX archive", doc.error_message)

    # 12. Corrupt PDF
    def test_12_corrupt_pdf(self):
        path = os.path.join(self.temp_dir.name, "corrupt.pdf")
        with open(path, "wb") as f:
            f.write(b"Not a PDF file content.")

        doc = extract_file(path)
        self.assertEqual(doc.status, "ERROR")
        self.assertIn("missing %PDF- header", doc.error_message)

    # 13. Unsupported extension
    def test_13_unsupported_extension(self):
        path = os.path.join(self.temp_dir.name, "binary.exe")
        with open(path, "wb") as f:
            f.write(b"MZ\x90\x00")

        doc = extract_file(path)
        self.assertEqual(doc.status, "ERROR")
        self.assertIn("Unsupported file extension", doc.error_message)

    # 14. Zero network calls guarantee
    def test_14_zero_network_calls(self):
        path = os.path.join(self.temp_dir.name, "privacy_check.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Highly Confidential Internal Note\nMust remain 100% on device.")

        def mock_forbidden_network(*args, **kwargs):
            raise AssertionError("NETWORK VIOLATION: Document extraction attempted an external call!")

        with patch.object(socket.socket, "connect", side_effect=mock_forbidden_network), \
             patch.object(urllib.request, "urlopen", side_effect=mock_forbidden_network):
            doc = extract_file(path)
            self.assertEqual(doc.status, "SUCCESS")
            self.assertIn("Confidential Internal Note", doc.text)


if __name__ == "__main__":
    unittest.main()
