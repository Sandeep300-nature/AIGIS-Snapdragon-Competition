import json
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from .onnx_embedder import LocalONNXEmbedder


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Computes cosine similarity between two 1D float32 vectors locally using NumPy.

    Safety:
    - Rejects dimension mismatch.
    - Handles zero vectors safely without division by zero.
    - Deterministic float output rounded to 4 decimals.
    """
    if vec1 is None or vec2 is None:
        return 0.0

    a = np.asarray(vec1, dtype=np.float32).flatten()
    b = np.asarray(vec2, dtype=np.float32).flatten()

    if a.shape != b.shape:
        raise ValueError(f"Vector dimension mismatch: {a.shape} vs {b.shape}")

    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))

    if norm_a == 0.0 or norm_b == 0.0 or np.isnan(norm_a) or np.isnan(norm_b):
        return 0.0

    dot = float(np.dot(a, b))
    sim = dot / (norm_a * norm_b)
    # Clip to valid cosine interval [-1.0, 1.0]
    sim = max(-1.0, min(1.0, sim))
    return round(sim, 4)


class VectorSearchEngine:
    """
    Local Vector & Hybrid Search Engine for AIGIS.
    100% On-Device & Zero-Cloud: Evaluates semantic vectors directly from SQLite.

    Features:
    - Semantic Search: Pure NumPy cosine similarity over on-device float32 vectors.
    - Hybrid Search: Configurable weighted combination of lexical and semantic scores.
    - Truthful fallback: Falls back gracefully to lexical search if embedding model is unavailable.
    """

    DEFAULT_SEMANTIC_WEIGHT = 0.70
    DEFAULT_LEXICAL_WEIGHT = 0.30

    def __init__(self, vault, embedder: Optional[LocalONNXEmbedder] = None):
        self.vault = vault
        self.embedder = embedder or LocalONNXEmbedder()

    def search_semantic(
        self,
        query: str,
        top_k: int = 5,
        collection: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes semantic vector similarity search across document chunks stored in SQLite.
        """
        if not self.embedder.is_available():
            return {
                "status": "EMBEDDING_MODEL_UNAVAILABLE",
                "retrieval_mode": "SEMANTIC",
                "message": "Local ONNX embedding model is not available. Please configure all-MiniLM-L6-v2.",
                "results": [],
                "count": 0
            }

        query_vec = self.embedder.embed(query)
        if query_vec is None:
            return {
                "status": "EMBEDDING_ERROR",
                "retrieval_mode": "SEMANTIC",
                "message": "Failed to generate embedding for query.",
                "results": [],
                "count": 0
            }

        # Load candidate chunks with vectors from SQLite vault
        chunks_with_vectors = self.vault.get_chunks_with_vectors(collection=collection)
        if not chunks_with_vectors:
            return {
                "status": "SUCCESS",
                "retrieval_mode": "SEMANTIC",
                "results": [],
                "count": 0
            }

        scored = []
        for chunk in chunks_with_vectors:
            chunk_vec = chunk.get("vector")
            if chunk_vec is None:
                continue

            try:
                sim = cosine_similarity(query_vec, chunk_vec)
                if sim > 0.05:
                    item = dict(chunk)
                    item["score"] = sim
                    item["semanticScore"] = sim
                    item["title"] = chunk.get("filename")
                    item["path"] = chunk.get("doc_path")
                    item["collection"] = chunk.get("metadata", {}).get("collection", "Projects")
                    item["codeMeta"] = chunk.get("metadata", {}).get("codeMeta", {})
                    item["text"] = chunk.get("content")
                    scored.append(item)
            except ValueError:
                continue

        scored.sort(key=lambda x: x["score"], reverse=True)
        limit = min(max(top_k, 1), 20)
        final_results = scored[:limit]

        return {
            "status": "SUCCESS",
            "retrieval_mode": "SEMANTIC",
            "results": final_results,
            "count": len(final_results)
        }

    def search_hybrid(
        self,
        query: str,
        top_k: int = 5,
        collection: Optional[str] = None,
        lexical_weight: float = DEFAULT_LEXICAL_WEIGHT,
        semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT
    ) -> Dict[str, Any]:
        """
        Executes hybrid retrieval combining lexical token matching and semantic vector similarity.
        Gracefully falls back to lexical search if embedding model is unavailable.
        """
        limit = min(max(top_k, 1), 20)

        # Fallback case: If embedding model is unavailable, return lexical search with honest provenance
        if not self.embedder.is_available():
            lexical_results = self.vault.search_document_chunks(query=query, limit=limit, collection=collection)
            for r in lexical_results:
                r["retrieval_mode"] = "LEXICAL_FALLBACK"
                r["lexicalScore"] = r.get("score", 0.0)
                r["semanticScore"] = 0.0

            return {
                "status": "SUCCESS",
                "retrieval_mode": "LEXICAL_FALLBACK",
                "embedding_status": "EMBEDDING_MODEL_UNAVAILABLE",
                "results": lexical_results,
                "count": len(lexical_results)
            }

        # Step A: Perform semantic vector search
        sem_res = self.search_semantic(query, top_k=limit * 2, collection=collection)
        sem_chunks = sem_res.get("results", [])

        # Step B: Perform lexical search
        lex_chunks = self.vault.search_document_chunks(query=query, limit=limit * 2, collection=collection)

        # Step C: Normalize and merge scores
        max_lex = max((c.get("score", 0.0) for c in lex_chunks), default=1.0)
        if max_lex == 0.0:
            max_lex = 1.0

        merged_dict: Dict[str, Dict[str, Any]] = {}

        for c in lex_chunks:
            cid = c.get("id")
            norm_lex = c.get("score", 0.0) / max_lex
            merged_dict[cid] = {
                "chunk": c,
                "lex_score": norm_lex,
                "sem_score": 0.0
            }

        for c in sem_chunks:
            cid = c.get("id")
            sem_score = max(0.0, c.get("score", 0.0))  # Cosine similarity [0, 1]
            if cid in merged_dict:
                merged_dict[cid]["sem_score"] = sem_score
                # Preserve richer chunk metadata
                merged_dict[cid]["chunk"] = c
            else:
                merged_dict[cid] = {
                    "chunk": c,
                    "lex_score": 0.0,
                    "sem_score": sem_score
                }

        # Calculate combined weighted score
        final_list = []
        for cid, data in merged_dict.items():
            chunk_item = dict(data["chunk"])
            lex_s = data["lex_score"]
            sem_s = data["sem_score"]
            comb_score = round(lexical_weight * lex_s + semantic_weight * sem_s, 4)

            chunk_item["score"] = comb_score
            chunk_item["lexicalScore"] = round(lex_s, 4)
            chunk_item["semanticScore"] = round(sem_s, 4)
            chunk_item["retrieval_mode"] = "HYBRID"
            final_list.append(chunk_item)

        final_list.sort(key=lambda x: x["score"], reverse=True)
        results = final_list[:limit]

        return {
            "status": "SUCCESS",
            "retrieval_mode": "HYBRID",
            "embedding_status": "READY",
            "weights": {"lexical": lexical_weight, "semantic": semantic_weight},
            "results": results,
            "count": len(results)
        }
