import os
import sys
import unittest
import tempfile
import sqlite3
import socket
import urllib.request
from unittest.mock import patch

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.documents.normalizer import normalize_text
from ai_engine.documents.chunker import DocumentChunker, chunk_document, estimate_tokens
from ai_engine.documents.extractors import compute_file_hash
from ai_engine.memory.local_memory_vault import LocalMemoryVault
from ai_engine.deep_doc_search import DeepDocSearchEngine


class TestDocumentChunking(unittest.TestCase):
    """
    Test suite for Milestone 7 Step 3: Semantic-Aware Chunking, Normalization,
    SQLite Persistence, Content Hashing, and Zero-Cloud Search.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_vault.db")
        self.vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        self.engine = DeepDocSearchEngine(data_dir=self.temp_dir.name, vault=self.vault)
        # Stop background watcher loop during tests
        self.engine.stop_file_watcher()

    def tearDown(self):
        try:
            self.engine.stop_file_watcher()
            self.vault.close()
            self.temp_dir.cleanup()
        except Exception:
            pass

    # 1. Text normalization
    def test_01_text_normalization(self):
        messy_text = "Line 1\r\nLine 2\rLine 3\x00\x07\x0b\n\n\n\n\nLine 4 after blank lines.\t"
        cleaned = normalize_text(messy_text, is_code=False)

        self.assertNotIn("\r", cleaned)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\x07", cleaned)
        self.assertNotIn("\x0b", cleaned)
        self.assertNotIn("\n\n\n", cleaned)  # Excessive newlines collapsed
        self.assertIn("Line 1\nLine 2\nLine 3", cleaned)
        self.assertIn("Line 4 after blank lines.", cleaned)

    # 2. Heading detection
    def test_02_heading_detection(self):
        doc_text = (
            "# Section 1: Introduction\n\n"
            "This is the introduction text of the document.\n\n"
            "## Section 2: Technical Specifications\n\n"
            "Here are the technical details and architecture."
        )
        chunks = chunk_document(
            document_id="doc_test_heading",
            text=doc_text,
            filename="spec.md",
            path="/docs/spec.md",
            extension=".md"
        )
        self.assertGreaterEqual(len(chunks), 1)
        self.assertIsNotNone(chunks[0].heading)
        self.assertIn("Section 1", chunks[0].heading)

    # 3. Paragraph boundaries
    def test_03_paragraph_boundaries(self):
        para1 = "This is paragraph number one explaining initial concepts in detail."
        para2 = "This is paragraph number two exploring secondary considerations and design."
        full_text = f"{para1}\n\n{para2}"

        chunks = chunk_document(
            document_id="doc_paras",
            text=full_text,
            max_tokens=500
        )
        self.assertEqual(len(chunks), 1)
        self.assertIn(para1, chunks[0].content)
        self.assertIn(para2, chunks[0].content)

    # 4. Sentence boundaries
    def test_04_sentence_boundaries(self):
        # Create a giant paragraph that exceeds max tokens to force sentence boundary splitting
        sentences = [
            f"Sentence number {i} provides essential context for the system operations."
            for i in range(100)
        ]
        giant_para = " ".join(sentences)

        chunker = DocumentChunker(target_tokens=150, max_tokens=200, overlap_tokens=30)
        chunks = chunker.chunk(document_id="doc_sentences", text=giant_para)

        self.assertGreater(len(chunks), 1)
        # Verify that chunks end cleanly with a period
        for c in chunks:
            self.assertTrue(c.content.endswith("."))

    # 5. Code block chunking
    def test_05_code_block_chunking(self):
        code = (
            "class MemoryController:\n"
            "    def __init__(self):\n"
            "        self.ready = True\n\n"
            "    def process(self, data):\n"
            "        return data.upper()\n\n"
            "class HardwareDetector:\n"
            "    def detect_npu(self):\n"
            "        return False\n"
        )
        chunker = DocumentChunker(target_tokens=40, max_tokens=60, overlap_tokens=10)
        chunks = chunker.chunk(
            document_id="doc_code",
            text=code,
            extension=".py"
        )
        self.assertGreaterEqual(len(chunks), 1)
        first_content = chunks[0].content
        self.assertTrue("class MemoryController" in first_content or "class HardwareDetector" in first_content)

    # 6. Chunk target size
    def test_06_chunk_target_size(self):
        text = "\n\n".join([f"Paragraph {i} has substantive content regarding local file intelligence." for i in range(150)])
        chunker = DocumentChunker(target_tokens=350, max_tokens=500, overlap_tokens=50)
        chunks = chunker.chunk(document_id="doc_size", text=text)

        self.assertGreater(len(chunks), 1)
        for c in chunks:
            toks = estimate_tokens(c.content)
            # Must not exceed max_tokens
            self.assertLessEqual(toks, 500)

    # 7. Chunk overlap
    def test_07_chunk_overlap(self):
        text = "\n\n".join([f"Distinct unit {i} includes unique information string." for i in range(80)])
        chunker = DocumentChunker(target_tokens=100, max_tokens=150, overlap_tokens=40)
        chunks = chunker.chunk(document_id="doc_overlap", text=text)

        self.assertGreater(len(chunks), 1)
        # Check that trailing text of chunk 0 overlaps with start of chunk 1
        words_chunk_0 = set(chunks[0].content.split()[-10:])
        words_chunk_1 = set(chunks[1].content.split()[:20])
        common = words_chunk_0.intersection(words_chunk_1)
        self.assertGreater(len(common), 0)

    # 8. Chunk ordering
    def test_08_chunk_ordering(self):
        text = "\n\n".join([f"Order unit {i} is sequentially numbered." for i in range(100)])
        chunker = DocumentChunker(target_tokens=80, max_tokens=120, overlap_tokens=20)
        chunks = chunker.chunk(document_id="doc_order", text=text)

        self.assertGreater(len(chunks), 2)
        for i, c in enumerate(chunks):
            self.assertEqual(c.chunk_index, i)
            self.assertEqual(c.id, f"doc_order_{i}")

    # 9. Metadata preservation & offsets
    def test_09_metadata_and_offsets(self):
        text = "First paragraph content.\n\nSecond paragraph content with details."
        chunks = chunk_document(
            document_id="doc_meta",
            text=text,
            filename="notes.txt",
            path="/home/notes.txt",
            extension=".txt",
            extra_metadata={"category": "Notes"}
        )
        self.assertEqual(len(chunks), 1)
        c = chunks[0]
        self.assertEqual(c.metadata["filename"], "notes.txt")
        self.assertEqual(c.metadata["extension"], ".txt")
        self.assertEqual(c.metadata["category"], "Notes")
        self.assertEqual(c.start_offset, 0)
        self.assertGreater(c.end_offset, 10)

    # 10. Content hashing
    def test_10_content_hashing(self):
        path = os.path.join(self.temp_dir.name, "hash_test.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Deterministic content hash.")

        h1 = compute_file_hash(path)
        h2 = compute_file_hash(path)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    # 11. Re-index unchanged file does not duplicate chunks
    def test_11_reindex_unchanged_file(self):
        path = os.path.join(self.temp_dir.name, "stable.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Stable document content that does not change across index runs.")

        res1 = self.engine.index_file(path)
        self.assertEqual(res1["status"], "INDEXED")
        initial_chunk_count = self.vault.count_document_chunks()
        self.assertGreater(initial_chunk_count, 0)

        # Second indexing call without modifying file
        res2 = self.engine.index_file(path)
        self.assertEqual(res2["status"], "SKIPPED")
        self.assertEqual(self.vault.count_document_chunks(), initial_chunk_count)

    # 12. Re-index modified file replaces chunks
    def test_12_reindex_modified_file(self):
        path = os.path.join(self.temp_dir.name, "modifiable.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Initial file version.")

        self.engine.index_file(path)
        doc = self.vault.get_document_by_path(path)
        chunks_v1 = self.vault.get_document_chunks(doc["id"])
        self.assertEqual(chunks_v1[0]["content"], "Initial file version.")

        # Modify file
        with open(path, "w", encoding="utf-8") as f:
            f.write("Updated file version with revised content.")

        res2 = self.engine.index_file(path)
        self.assertEqual(res2["status"], "INDEXED")
        chunks_v2 = self.vault.get_document_chunks(doc["id"])
        self.assertEqual(len(chunks_v2), 1)
        self.assertEqual(chunks_v2[0]["content"], "Updated file version with revised content.")

    # 13. Extraction failure does not destroy valid prior index
    def test_13_extraction_failure_preserves_prior_index(self):
        path = os.path.join(self.temp_dir.name, "resilient.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Valid first version.")

        self.engine.index_file(path)
        doc = self.vault.get_document_by_path(path)
        prior_chunks = self.vault.get_document_chunks(doc["id"])
        self.assertEqual(len(prior_chunks), 1)

        # Simulate extraction failure by patching extract_file to return ERROR
        from ai_engine.documents.extractors import ExtractedDocument
        with patch("ai_engine.deep_doc_search.extract_file", return_value=ExtractedDocument(
            path=path, filename="resilient.txt", extension=".txt", size_bytes=100,
            content_hash="", status="ERROR", error_message="I/O Error"
        )):
            res = self.engine.index_file(path)
            self.assertEqual(res["status"], "WARNING")
            # Verify valid prior index was preserved
            preserved_chunks = self.vault.get_document_chunks(doc["id"])
            self.assertEqual(len(preserved_chunks), 1)
            self.assertEqual(preserved_chunks[0]["content"], "Valid first version.")

    # 14. SQLite persistence & lexical search integration
    def test_14_sqlite_persistence_and_search(self):
        doc1_path = os.path.join(self.temp_dir.name, "architecture.md")
        with open(doc1_path, "w", encoding="utf-8") as f:
            f.write("# AIGIS Architecture\n\nLocal Memory Vault uses SQLite for authoritative persistence.")

        doc2_path = os.path.join(self.temp_dir.name, "hardware.txt")
        with open(doc2_path, "w", encoding="utf-8") as f:
            f.write("Hexagon NPU hardware target on Qualcomm Snapdragon platforms.")

        self.engine.index_file(doc1_path)
        self.engine.index_file(doc2_path)

        docs = self.engine.list_documents()
        self.assertEqual(len(docs), 2)

        # Search for architecture
        results = self.engine.search("SQLite Memory Vault")
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("SQLite for authoritative persistence", results[0]["text"])

        # Search for NPU
        npu_results = self.engine.search("Hexagon NPU")
        self.assertGreaterEqual(len(npu_results), 1)
        self.assertIn("Hexagon NPU", npu_results[0]["text"])


if __name__ == "__main__":
    unittest.main()
