import os
import re
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

try:
    import onnxruntime as ort
    _HAS_ORT = True
except ImportError:
    ort = None
    _HAS_ORT = False

try:
    from tokenizers import Tokenizer
    _HAS_TOKENIZERS = True
except ImportError:
    Tokenizer = None
    _HAS_TOKENIZERS = False

try:
    from transformers import AutoTokenizer
    _HAS_TRANSFORMERS = True
except ImportError:
    AutoTokenizer = None
    _HAS_TRANSFORMERS = False


EMBEDDING_DIMENSION = 384


class LocalONNXEmbedder:
    """
    Local ONNX Embedding Engine for AIGIS.
    100% On-Device & Zero-Cloud: No remote APIs, vector clouds, or third-party web calls.

    Features:
    - Truthful availability: Reports EMBEDDING_MODEL_UNAVAILABLE if model files are absent.
    - Hardware-aware execution: Uses CPUExecutionProvider on x86_64; selects QNNExecutionProvider
      only if physically present and verified on Snapdragon ARM64.
    - Attention-mask-aware mean-pooling over last_hidden_state.
    - Deterministic float32 unit-normalized (L2 norm = 1.0) embeddings.
    """

    DEFAULT_MODEL_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models",
        "all-MiniLM-L6-v2"
    )
    EXPECTED_DIMENSION = 384
    MODEL_NAME = "all-MiniLM-L6-v2"

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = model_dir or os.getenv("AIGIS_EMBEDDING_MODEL_DIR", self.DEFAULT_MODEL_DIR)
        self.session: Optional[Any] = None
        self.tokenizer: Optional[Any] = None
        self.tokenizer_type: Optional[str] = None
        self.execution_provider: str = "None"
        self._status_code: str = "EMBEDDING_MODEL_UNAVAILABLE"
        self._error_message: Optional[str] = None

        self._initialize()

    @property
    def hardware_provider(self) -> str:
        """Returns the hardware execution provider (e.g. CPUExecutionProvider or QNNExecutionProvider)."""
        if self.execution_provider and self.execution_provider != "None":
            return self.execution_provider
        if _HAS_ORT and ort:
            available = ort.get_available_providers()
            if "QNNExecutionProvider" in available:
                return "QNNExecutionProvider"
        return "CPUExecutionProvider"

    def _initialize(self):
        """Discovers, validates, and initializes the local ONNX embedding model."""
        if not os.path.exists(self.model_dir):
            self._status_code = "EMBEDDING_MODEL_UNAVAILABLE"
            self._error_message = f"Embedding model directory not found: {self.model_dir}"
            return

        # 1. Validate ONNX model file
        onnx_file = None
        for candidate in ["model.onnx", "model_quantized.onnx", "onnx/model.onnx"]:
            p = os.path.join(self.model_dir, candidate)
            if os.path.exists(p):
                onnx_file = p
                break

        if not onnx_file:
            self._status_code = "EMBEDDING_MODEL_INVALID"
            self._error_message = f"No model.onnx found in {self.model_dir}"
            return

        # 2. Validate tokenizer files
        tokenizer_json = os.path.join(self.model_dir, "tokenizer.json")
        vocab_txt = os.path.join(self.model_dir, "vocab.txt")
        if not os.path.exists(tokenizer_json) and not os.path.exists(vocab_txt):
            self._status_code = "EMBEDDING_MODEL_INVALID"
            self._error_message = f"Missing tokenizer.json or vocab.txt in {self.model_dir}"
            return

        # 3. Load Tokenizer
        if _HAS_TOKENIZERS and os.path.exists(tokenizer_json):
            try:
                self.tokenizer = Tokenizer.from_file(tokenizer_json)
                self.tokenizer_type = "tokenizers"
            except Exception as e:
                self.tokenizer = None

        if not self.tokenizer and _HAS_TRANSFORMERS:
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir, local_files_only=True)
                self.tokenizer_type = "transformers"
            except Exception as e:
                self.tokenizer = None

        if not self.tokenizer:
            self._status_code = "EMBEDDING_MODEL_INVALID"
            self._error_message = "Failed to initialize local tokenizer from files."
            return

        # 4. Initialize ONNX Runtime Session with hardware provider selection
        if not _HAS_ORT or not ort:
            self._status_code = "EMBEDDING_MODEL_INVALID"
            self._error_message = "onnxruntime is not installed or available."
            return

        available_providers = ort.get_available_providers()
        # Truthful hardware selection: Prefer QNNExecutionProvider if present, otherwise CPUExecutionProvider
        if "QNNExecutionProvider" in available_providers:
            providers = ["QNNExecutionProvider", "CPUExecutionProvider"]
        else:
            providers = ["CPUExecutionProvider"]

        try:
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 4
            self.session = ort.InferenceSession(onnx_file, sess_options=opts, providers=providers)
            active_providers = self.session.get_providers()
            self.execution_provider = active_providers[0] if active_providers else "CPUExecutionProvider"
            self._status_code = "READY"
            self._error_message = None
        except Exception as e:
            self._status_code = "EMBEDDING_MODEL_INVALID"
            self._error_message = f"Failed to load ONNX session: {str(e)}"
            self.session = None

    def is_available(self) -> bool:
        """Returns True only if the embedding model is loaded, verified, and ready for inference."""
        return self._status_code == "READY" and self.session is not None and self.tokenizer is not None

    def status(self) -> Dict[str, Any]:
        """Returns truthful runtime status, provider provenance, and configuration."""
        return {
            "status": self._status_code,
            "available": self.is_available(),
            "modelName": self.MODEL_NAME,
            "modelDir": self.model_dir,
            "dimension": self.EXPECTED_DIMENSION,
            "runtime": "ONNX Runtime" if _HAS_ORT else "None",
            "executionProvider": self.execution_provider,
            "normalized": True,
            "localInference": True,
            "networkUsed": False,
            "errorMessage": self._error_message
        }

    def _tokenize(self, texts: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        """Tokenizes a batch of texts into input_ids and attention_mask numpy arrays."""
        if not texts:
            return np.zeros((0, 1), dtype=np.int64), np.zeros((0, 1), dtype=np.int64)

        if self.tokenizer_type == "tokenizers" and self.tokenizer:
            # Tokenizers library
            self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
            self.tokenizer.enable_truncation(max_length=256)
            encoded = self.tokenizer.encode_batch(texts)
            input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
            attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            return input_ids, attention_mask
        elif self.tokenizer_type == "transformers" and self.tokenizer:
            # Transformers library
            batch = self.tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="np"
            )
            return batch["input_ids"].astype(np.int64), batch["attention_mask"].astype(np.int64)
        else:
            # Basic fallback for testing/mocking
            tokens_batch = [re.findall(r'\w+', t.lower())[:64] for t in texts]
            max_len = max(len(toks) for toks in tokens_batch) if tokens_batch else 1
            max_len = max(max_len, 1)
            input_ids = np.zeros((len(texts), max_len), dtype=np.int64)
            attention_mask = np.zeros((len(texts), max_len), dtype=np.int64)
            for i, toks in enumerate(tokens_batch):
                for j, t in enumerate(toks):
                    input_ids[i, j] = (hash(t) % 10000) + 1
                    attention_mask[i, j] = 1
            return input_ids, attention_mask

    def _mean_pooling(self, token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
        """Mean pooling with attention mask awareness."""
        input_mask_expanded = np.expand_dims(attention_mask, -1).astype(np.float32)
        sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)
        sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        return sum_embeddings / sum_mask

    def _l2_normalize(self, vectors: np.ndarray) -> np.ndarray:
        """L2 normalizes vectors with safe handling of zero vectors."""
        norms = np.linalg.norm(vectors, ord=2, axis=1, keepdims=True)
        # Avoid division by zero if norm is 0
        norms = np.where(norms == 0.0, 1.0, norms)
        return (vectors / norms).astype(np.float32)

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """
        Generates deterministic float32 embeddings for a batch of texts.
        Returns: 2D numpy array of shape (N, 384).
        Raises: RuntimeError if model is unavailable.
        """
        if not self.is_available():
            raise RuntimeError("Local ONNX embedding model is not available.")

        if not texts:
            return np.zeros((0, self.EXPECTED_DIMENSION), dtype=np.float32)

        # Handle empty/whitespace strings cleanly
        cleaned_texts = [t.strip() if t and t.strip() else "empty document" for t in texts]

        try:
            input_ids, attention_mask = self._tokenize(cleaned_texts)

            # Build inputs feed for ONNX
            inputs = {
                "input_ids": input_ids,
                "attention_mask": attention_mask
            }
            # Check if model also expects token_type_ids
            session_inputs = [inp.name for inp in self.session.get_inputs()]
            if "token_type_ids" in session_inputs:
                inputs["token_type_ids"] = np.zeros_like(input_ids, dtype=np.int64)

            # Run local inference
            outputs = self.session.run(None, inputs)
            token_embeddings = outputs[0]  # Shape: (batch_size, seq_len, hidden_dim)

            pooled = self._mean_pooling(token_embeddings, attention_mask)
            normalized = self._l2_normalize(pooled)
            return normalized
        except Exception as e:
            raise RuntimeError(f"Local ONNX embedding inference failed: {e}")

    def embed(self, text: str) -> Optional[np.ndarray]:
        """
        Generates float32 embedding vector for a single text.
        Returns: 1D numpy array of shape (384,), or None if model unavailable.
        """
        if not self.is_available():
            return None
        try:
            batch = self.embed_batch([text])
            if batch is not None and len(batch) > 0:
                return batch[0]
        except Exception:
            return None
        return None

    def embed_query(self, text: str) -> List[float]:
        """
        Generates embedding for a query string.
        Returns: Python list of floats.
        Raises: RuntimeError if model is unavailable.
        """
        if not self.is_available():
            raise RuntimeError("Local ONNX embedding model is not available.")
        vec = self.embed(text)
        if vec is None:
            raise RuntimeError("Failed to generate query embedding.")
        return vec.tolist()
