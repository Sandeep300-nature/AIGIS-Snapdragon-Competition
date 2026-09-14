"""
Unit tests for VectorSearchEngine and SQLite vector storage.
ai_engine/embeddings/vector_search.py & ai_engine/memory/local_memory_vault.py.
Covers:
1. Cosine similarity for identical vectors (1.0)
2. Cosine similarity for orthogonal vectors (0.0)
3. Cosine similarity for opposite vectors (-1.0)
4. Cosine similarity with zero vector (0.0 without NaN/div-by-zero)
5. Dimension mismatch handling (raises ValueError)
6. SQLite float32 BLOB serialization/deserialization roundtrip
7. SQLite batch_store_chunk_vectors transaction
8. Resilience against corrupt / truncated BLOB in database
9. Graceful skipping of chunks with missing vectors
10. Semantic search ranking order (descending similarity)
11. Hybrid search ranking combining lexical and semantic scores
12. Semantic search behavior when embedder is unavailable
13. Hybrid search graceful fallback to lexical search
14. Incremental embedding filtering via get_unembedded_chunks
"""

import os
import sys
import unittest
import tempfile
import numpy as np
from unittest.mock import MagicMock

# Ensure ai_engine is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI_ENGINE_DIR = os.path.join(BASE_DIR, "ai_engine")
if AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, AI_ENGINE_DIR)

from ai_engine.embeddings.vector_search import VectorSearchEngine, cosine_similarity
from ai_engine.memory.local_memory_vault import LocalMemoryVault


class TestVectorSearchEngine(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_vault.db")
        self.vault = LocalMemoryVault(db_path=self.db_path)

        # Setup mock embedder
        self.mock_embedder = MagicMock()
        self.mock_embedder.is_available.return_value = True
        self.mock_embedder.model_name = "all-MiniLM-L6-v2"
        self.mock_embedder.dimension = 4

    def tearDown(self):
        # Explicitly close SQLite connection to release file handle on Windows
        try:
            self.vault.close()
        except Exception:
            pass
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_01_cosine_similarity_identical_vectors(self):
        v1 = [0.5, 0.5, 0.5, 0.5]
        sim = cosine_similarity(v1, v1)
        self.assertAlmostEqual(sim, 1.0, places=4)

    def test_02_cosine_similarity_orthogonal_vectors(self):
        v1 = [1.0, 0.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0, 0.0]
        sim = cosine_similarity(v1, v2)
        self.assertAlmostEqual(sim, 0.0, places=4)

    def test_03_cosine_similarity_opposite_vectors(self):
        v1 = [1.0, 0.0, 0.0, 0.0]
        v2 = [-1.0, 0.0, 0.0, 0.0]
        sim = cosine_similarity(v1, v2)
        self.assertAlmostEqual(sim, -1.0, places=4)

    def test_04_cosine_similarity_zero_vector(self):
        v1 = [0.0, 0.0, 0.0, 0.0]
        v2 = [1.0, 2.0, 3.0, 4.0]
        sim = cosine_similarity(v1, v2)
        self.assertEqual(sim, 0.0)
        self.assertFalse(np.isnan(sim))

    def test_05_cosine_similarity_dimension_mismatch(self):
        v1 = [1.0, 2.0]
        v2 = [1.0, 2.0, 3.0]
        with self.assertRaises(ValueError) as ctx:
            cosine_similarity(v1, v2)
        self.assertIn("mismatch", str(ctx.exception).lower())

    def test_06_sqlite_vector_blob_roundtrip(self):
        self.vault.upsert_document("doc1", "/path/doc1.txt", "doc1.txt", ".txt", 100, 1000.0, "hash1")
        chunks = [{
            "id": "c1",
            "document_id": "doc1",
            "chunk_index": 0,
            "content": "Sample content",
            "token_count": 5,
            "section_heading": "Intro"
        }]
        self.vault.store_document_chunks("doc1", chunks)

        original_vector = [0.1, 0.2, 0.3, 0.4]
        stored = self.vault.store_chunk_vector("c1", original_vector, model_name="test-model", dimension=4)
        self.assertTrue(stored)

        retrieved = self.vault.get_chunks_with_vectors()
        self.assertEqual(len(retrieved), 1)
        r_item = retrieved[0]
        self.assertEqual(r_item["id"], "c1")
        self.assertEqual(r_item["embedding_model"], "test-model")
        self.assertEqual(r_item["embedding_dimension"], 4)
        np.testing.assert_allclose(r_item["vector"], original_vector, rtol=1e-5)

    def test_07_sqlite_batch_store_chunk_vectors(self):
        self.vault.upsert_document("doc1", "/path/doc1.txt", "doc1.txt", ".txt", 100, 1000.0, "hash1")
        chunks = [
            {"id": "c1", "document_id": "doc1", "chunk_index": 0, "content": "Text 1", "token_count": 2},
            {"id": "c2", "document_id": "doc1", "chunk_index": 1, "content": "Text 2", "token_count": 2}
        ]
        self.vault.store_document_chunks("doc1", chunks)

        batch = [
            ("c1", [0.1, 0.2, 0.3, 0.4]),
            ("c2", [0.5, 0.6, 0.7, 0.8])
        ]
        count = self.vault.batch_store_chunk_vectors(batch, model_name="batch-model", dimension=4)
        self.assertEqual(count, 2)

        retrieved = self.vault.get_chunks_with_vectors()
        self.assertEqual(len(retrieved), 2)

    def test_08_corrupt_vector_blob_resilience(self):
        self.vault.upsert_document("doc1", "/path/doc1.txt", "doc1.txt", ".txt", 100, 1000.0, "hash1")
        chunks = [{"id": "c_corrupt", "document_id": "doc1", "chunk_index": 0, "content": "Bad BLOB", "token_count": 2}]
        self.vault.store_document_chunks("doc1", chunks)

        with self.vault._lock:
            cursor = self.vault._conn.cursor()
            cursor.execute(
                "UPDATE document_chunks SET vector_blob = ?, embedding_model = ?, embedding_dimension = ? WHERE id = ?",
                (b"\x00\x01\x02", "corrupt-model", 4, "c_corrupt")
            )
            self.vault._conn.commit()

        # Corrupted vector is skipped gracefully without crashing
        retrieved = self.vault.get_chunks_with_vectors()
        self.assertEqual(len(retrieved), 0)

    def test_09_missing_vector_blob_skips_gracefully(self):
        self.vault.upsert_document("doc1", "/path/doc1.txt", "doc1.txt", ".txt", 100, 1000.0, "hash1")
        chunks = [
            {"id": "c_no_vec", "document_id": "doc1", "chunk_index": 0, "content": "No vector", "token_count": 2},
            {"id": "c_with_vec", "document_id": "doc1", "chunk_index": 1, "content": "Has vector", "token_count": 2}
        ]
        self.vault.store_document_chunks("doc1", chunks)
        self.vault.store_chunk_vector("c_with_vec", [1.0, 0.0, 0.0, 0.0], model_name="test", dimension=4)

        retrieved = self.vault.get_chunks_with_vectors()
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0]["id"], "c_with_vec")

    def test_10_semantic_ranking_order(self):
        self.vault.upsert_document("doc1", "/path/doc1.txt", "doc1.txt", ".txt", 100, 1000.0, "hash1")
        chunks = [
            {"id": "c_low", "document_id": "doc1", "chunk_index": 0, "content": "Low similarity", "token_count": 2},
            {"id": "c_high", "document_id": "doc1", "chunk_index": 1, "content": "High similarity", "token_count": 2},
            {"id": "c_med", "document_id": "doc1", "chunk_index": 2, "content": "Med similarity", "token_count": 2}
        ]
        self.vault.store_document_chunks("doc1", chunks)

        # Query vector: [1.0, 0.0, 0.0, 0.0]
        self.mock_embedder.embed.return_value = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        # Vectors with dimension 4:
        self.vault.store_chunk_vector("c_high", [0.9, 0.1, 0.0, 0.0], dimension=4)
        self.vault.store_chunk_vector("c_med", [0.5, 0.5, 0.0, 0.0], dimension=4)
        self.vault.store_chunk_vector("c_low", [0.1, 0.9, 0.0, 0.0], dimension=4)

        search_engine = VectorSearchEngine(vault=self.vault, embedder=self.mock_embedder)
        res = search_engine.search_semantic("test query", top_k=3)

        self.assertEqual(res["status"], "SUCCESS")
        results = res["results"]
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["id"], "c_high")
        self.assertEqual(results[1]["id"], "c_med")
        self.assertEqual(results[2]["id"], "c_low")
        self.assertGreater(results[0]["score"], results[1]["score"])
        self.assertGreater(results[1]["score"], results[2]["score"])

    def test_11_hybrid_ranking_weights(self):
        self.vault.upsert_document("doc1", "/path/doc1.txt", "doc1.txt", ".txt", 100, 1000.0, "hash1")
        chunks = [
            {"id": "c1", "document_id": "doc1", "chunk_index": 0, "content": "Alpha beta security", "token_count": 3},
            {"id": "c2", "document_id": "doc1", "chunk_index": 1, "content": "Gamma delta security", "token_count": 3}
        ]
        self.vault.store_document_chunks("doc1", chunks)

        self.mock_embedder.embed.return_value = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        self.vault.store_chunk_vector("c1", [0.2, 0.8, 0.0, 0.0], dimension=4)
        self.vault.store_chunk_vector("c2", [0.9, 0.1, 0.0, 0.0], dimension=4)

        search_engine = VectorSearchEngine(vault=self.vault, embedder=self.mock_embedder)
        res = search_engine.search_hybrid("Alpha security", top_k=2, lexical_weight=0.3, semantic_weight=0.7)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["retrieval_mode"], "HYBRID")
        for r in res["results"]:
            self.assertEqual(r["retrieval_mode"], "HYBRID")
            self.assertIn("score", r)

    def test_12_semantic_search_unavailable_model(self):
        self.mock_embedder.is_available.return_value = False
        search_engine = VectorSearchEngine(vault=self.vault, embedder=self.mock_embedder)

        res = search_engine.search_semantic("query", top_k=5)
        self.assertEqual(res["status"], "EMBEDDING_MODEL_UNAVAILABLE")
        self.assertEqual(res["results"], [])
        self.assertEqual(res["count"], 0)

    def test_13_hybrid_fallback_to_lexical(self):
        self.mock_embedder.is_available.return_value = False
        self.vault.upsert_document("doc1", "/path/doc1.txt", "doc1.txt", ".txt", 100, 1000.0, "hash1")
        chunks = [{"id": "c1", "document_id": "doc1", "chunk_index": 0, "content": "Snapdragon NPU architecture", "token_count": 3}]
        self.vault.store_document_chunks("doc1", chunks)

        search_engine = VectorSearchEngine(vault=self.vault, embedder=self.mock_embedder)
        res = search_engine.search_hybrid("Snapdragon", top_k=5)

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["retrieval_mode"], "LEXICAL_FALLBACK")
        self.assertEqual(len(res["results"]), 1)
        self.assertEqual(res["results"][0]["retrieval_mode"], "LEXICAL_FALLBACK")

    def test_14_incremental_unembedded_chunks(self):
        self.vault.upsert_document("doc1", "/path/doc1.txt", "doc1.txt", ".txt", 100, 1000.0, "hash1")
        chunks = [
            {"id": "c1", "document_id": "doc1", "chunk_index": 0, "content": "Unembedded one", "token_count": 2},
            {"id": "c2", "document_id": "doc1", "chunk_index": 1, "content": "Embedded one", "token_count": 2},
            {"id": "c3", "document_id": "doc1", "chunk_index": 2, "content": "Unembedded two", "token_count": 2}
        ]
        self.vault.store_document_chunks("doc1", chunks)
        # Store vector only for c2
        self.vault.store_chunk_vector("c2", [0.1, 0.2, 0.3, 0.4], dimension=4)

        unembedded = self.vault.get_unembedded_chunks()
        self.assertEqual(len(unembedded), 2)
        unembedded_ids = [c["id"] for c in unembedded]
        self.assertIn("c1", unembedded_ids)
        self.assertIn("c3", unembedded_ids)
        self.assertNotIn("c2", unembedded_ids)


if __name__ == "__main__":
    unittest.main()
