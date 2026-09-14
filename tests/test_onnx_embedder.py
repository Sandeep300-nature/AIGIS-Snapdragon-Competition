"""
Unit tests for LocalONNXEmbedder in ai_engine/embeddings/onnx_embedder.py.
Covers:
1. Unavailable state when model directory is missing
2. Unavailable state when ONNX file is missing
3. Unavailable state when tokenizer files are missing
4. Hardware provider detection (CPUExecutionProvider on x86_64)
5. Graceful query embedding failure when unavailable
6. Graceful batch embedding failure when unavailable
7. Mock inference dimensionality (384 dimensions)
8. Float32 data type precision
9. L2 normalization compliance (norm ~= 1.0)
10. Attention-mask-aware mean pooling accuracy
11. L2 normalization zero-vector safety (no NaN/inf)
12. Batch embedding consistency and ordering
13. Zero-network enforcement (no external socket connections)
14. Zero cloud / Groq dependency verification
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

# Ensure ai_engine is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI_ENGINE_DIR = os.path.join(BASE_DIR, "ai_engine")
if AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, AI_ENGINE_DIR)

from ai_engine.embeddings.onnx_embedder import LocalONNXEmbedder, EMBEDDING_DIMENSION


class TestLocalONNXEmbedder(unittest.TestCase):

    def setUp(self):
        # Ensure we test with non-existent model dir by default
        self.non_existent_dir = os.path.join(BASE_DIR, "ai_engine", "models", "non_existent_model_dir_xyz")

    def test_01_status_unavailable_when_model_dir_missing(self):
        embedder = LocalONNXEmbedder(model_dir=self.non_existent_dir)
        self.assertFalse(embedder.is_available())
        status = embedder.status()
        self.assertEqual(status["status"], "EMBEDDING_MODEL_UNAVAILABLE")
        self.assertEqual(status["dimension"], EMBEDDING_DIMENSION)

    def test_02_status_unavailable_when_onnx_file_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create tokenizer.json only, no .onnx
            with open(os.path.join(tmpdir, "tokenizer.json"), "w") as f:
                f.write("{}")
            embedder = LocalONNXEmbedder(model_dir=tmpdir)
            self.assertFalse(embedder.is_available())
            self.assertIn(embedder.status()["status"], ["EMBEDDING_MODEL_UNAVAILABLE", "EMBEDDING_MODEL_INVALID"])

    def test_03_status_unavailable_when_tokenizer_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create model.onnx only, no tokenizer
            with open(os.path.join(tmpdir, "model.onnx"), "w") as f:
                f.write("mock onnx")
            embedder = LocalONNXEmbedder(model_dir=tmpdir)
            self.assertFalse(embedder.is_available())
            self.assertIn(embedder.status()["status"], ["EMBEDDING_MODEL_UNAVAILABLE", "EMBEDDING_MODEL_INVALID"])

    def test_04_hardware_provider_detection_x86_64(self):
        embedder = LocalONNXEmbedder(model_dir=self.non_existent_dir)
        provider = embedder.hardware_provider
        self.assertIn(provider, ["CPUExecutionProvider", "QNNExecutionProvider"])
        if sys.platform == "win32" and "ARM" not in os.environ.get("PROCESSOR_ARCHITECTURE", ""):
            self.assertEqual(provider, "CPUExecutionProvider")

    def test_05_embed_query_fails_gracefully_when_unavailable(self):
        embedder = LocalONNXEmbedder(model_dir=self.non_existent_dir)
        with self.assertRaises(RuntimeError) as ctx:
            embedder.embed_query("Test query")
        self.assertIn("not available", str(ctx.exception).lower())

    def test_06_embed_batch_fails_gracefully_when_unavailable(self):
        embedder = LocalONNXEmbedder(model_dir=self.non_existent_dir)
        with self.assertRaises(RuntimeError) as ctx:
            embedder.embed_batch(["text1", "text2"])
        self.assertIn("not available", str(ctx.exception).lower())

    def test_07_offline_mock_inference_dimension(self):
        embedder = LocalONNXEmbedder(model_dir=self.non_existent_dir)
        mock_session = MagicMock()
        mock_tokenizer = MagicMock()
        
        mock_encoded = MagicMock()
        mock_encoded.ids = [101, 2054, 102]
        mock_encoded.attention_mask = [1, 1, 1]
        mock_tokenizer.encode_batch.return_value = [mock_encoded]
        mock_session.get_inputs.return_value = []
        
        mock_output = np.random.randn(1, 3, EMBEDDING_DIMENSION).astype(np.float32)
        mock_session.run.return_value = [mock_output]

        embedder.session = mock_session
        embedder.tokenizer = mock_tokenizer
        embedder.tokenizer_type = "tokenizers"
        embedder._status_code = "READY"

        vec = embedder.embed_query("Hello AIGIS local embedding")
        self.assertEqual(len(vec), 384)

    def test_08_offline_mock_inference_float32(self):
        embedder = LocalONNXEmbedder(model_dir=self.non_existent_dir)
        mock_session = MagicMock()
        mock_tokenizer = MagicMock()
        mock_encoded = MagicMock()
        mock_encoded.ids = [101, 102]
        mock_encoded.attention_mask = [1, 1]
        mock_tokenizer.encode_batch.return_value = [mock_encoded]
        mock_session.get_inputs.return_value = []
        
        mock_output = np.ones((1, 2, EMBEDDING_DIMENSION), dtype=np.float32)
        mock_session.run.return_value = [mock_output]

        embedder.session = mock_session
        embedder.tokenizer = mock_tokenizer
        embedder.tokenizer_type = "tokenizers"
        embedder._status_code = "READY"

        vec = embedder.embed_query("Type test")
        for val in vec:
            self.assertIsInstance(val, float)

    def test_09_offline_mock_inference_l2_normalized(self):
        embedder = LocalONNXEmbedder(model_dir=self.non_existent_dir)
        mock_session = MagicMock()
        mock_tokenizer = MagicMock()
        mock_encoded = MagicMock()
        mock_encoded.ids = [101, 2000, 102]
        mock_encoded.attention_mask = [1, 1, 1]
        mock_tokenizer.encode_batch.return_value = [mock_encoded]
        mock_session.get_inputs.return_value = []
        
        mock_output = np.random.randn(1, 3, EMBEDDING_DIMENSION).astype(np.float32)
        mock_session.run.return_value = [mock_output]

        embedder.session = mock_session
        embedder.tokenizer = mock_tokenizer
        embedder.tokenizer_type = "tokenizers"
        embedder._status_code = "READY"

        vec = embedder.embed_query("Normalization test")
        norm = np.linalg.norm(vec)
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_10_attention_mask_pooling_logic(self):
        embedder = LocalONNXEmbedder(model_dir=self.non_existent_dir)
        token_embeddings = np.array([[[2.0, 4.0], [100.0, 100.0]]], dtype=np.float32)
        attention_mask = np.array([[1, 0]], dtype=np.int64)

        pooled = embedder._mean_pooling(token_embeddings, attention_mask)
        np.testing.assert_allclose(pooled[0], [2.0, 4.0], rtol=1e-5)

    def test_11_l2_normalize_logic(self):
        embedder = LocalONNXEmbedder(model_dir=self.non_existent_dir)
        zero_vec = np.zeros((1, 4), dtype=np.float32)
        normalized_zero = embedder._l2_normalize(zero_vec)
        self.assertFalse(np.isnan(normalized_zero).any())
        self.assertFalse(np.isinf(normalized_zero).any())
        np.testing.assert_allclose(normalized_zero, zero_vec)

        vec = np.array([[3.0, 4.0]], dtype=np.float32)
        normalized = embedder._l2_normalize(vec)
        np.testing.assert_allclose(normalized, [[0.6, 0.8]], rtol=1e-5)

    def test_12_batch_embedding_consistency(self):
        embedder = LocalONNXEmbedder(model_dir=self.non_existent_dir)
        mock_session = MagicMock()
        mock_tokenizer = MagicMock()
        mock_encoded1 = MagicMock()
        mock_encoded1.ids = [101, 102]
        mock_encoded1.attention_mask = [1, 1]
        mock_encoded2 = MagicMock()
        mock_encoded2.ids = [101, 103]
        mock_encoded2.attention_mask = [1, 1]
        mock_tokenizer.encode_batch.return_value = [mock_encoded1, mock_encoded2]
        mock_session.get_inputs.return_value = []

        mock_output = np.random.randn(2, 2, EMBEDDING_DIMENSION).astype(np.float32)
        mock_session.run.return_value = [mock_output]

        embedder.session = mock_session
        embedder.tokenizer = mock_tokenizer
        embedder.tokenizer_type = "tokenizers"
        embedder._status_code = "READY"

        vectors = embedder.embed_batch(["text one", "text two"])
        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), EMBEDDING_DIMENSION)
        self.assertEqual(len(vectors[1]), EMBEDDING_DIMENSION)

    def test_13_zero_network_calls(self):
        import socket
        orig_socket = socket.socket

        def guarded_socket(*args, **kwargs):
            raise AssertionError("Network socket connection attempted by local embedder!")

        try:
            with patch("socket.socket", side_effect=guarded_socket):
                embedder = LocalONNXEmbedder(model_dir=self.non_existent_dir)
                status = embedder.status()
                self.assertEqual(status["status"], "EMBEDDING_MODEL_UNAVAILABLE")
        finally:
            socket.socket = orig_socket

    def test_14_no_groq_or_cloud_in_embedder(self):
        import inspect
        import ai_engine.embeddings.onnx_embedder as mod
        source = inspect.getsource(mod)
        self.assertNotIn("groq", source.lower())
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("anthropic", source.lower())
        self.assertNotIn("cohere", source.lower())


if __name__ == "__main__":
    unittest.main()
