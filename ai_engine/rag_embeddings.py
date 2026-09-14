import numpy as np
from typing import List, Dict

class RAGEmbeddingEngine:
    """
    RAG & Vector Memory Retrieval Engine for AIGIS Python AI Engine.
    Provides similarity search and semantic memory filtering across conversation turns.
    """
    def __init__(self):
        self.vector_cache = {}

    def simple_text_embedding(self, text: str) -> np.ndarray:
        """Generates a normalized character/word n-gram vector for fast similarity ranking."""
        words = text.lower().split()
        hash_vec = np.zeros(64)
        for w in words:
            idx = sum(ord(c) for c in w) % 64
            hash_vec[idx] += 1
        norm = np.linalg.norm(hash_vec)
        return hash_vec / norm if norm > 0 else hash_vec

    def retrieve_relevant_context(self, query: str, history: List[Dict[str, str]], top_k: int = 3) -> List[Dict[str, str]]:
        """RAG Search: Ranks and returns top_k most relevant past messages matching the query."""
        if not history:
            return []

        query_vec = self.simple_text_embedding(query)
        scored_messages = []

        for msg in history:
            content = msg.get("content", "")
            msg_vec = self.simple_text_embedding(content)
            similarity = float(np.dot(query_vec, msg_vec))
            scored_messages.append((similarity, msg))

        # Sort by highest semantic similarity score
        scored_messages.sort(key=lambda x: x[0], reverse=True)
        return [msg for score, msg in scored_messages[:top_k] if score > 0.1]
