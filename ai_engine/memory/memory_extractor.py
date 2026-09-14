import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

class MemoryExtractor:
    """
    Zero-Cloud Deterministic Memory Extractor for AIGIS.
    Extracts high-confidence structured memories (User Preferences, Project Context,
    Tasks, General Knowledge, and Temporary News) using deterministic local heuristics.

    Absolute Privacy Guardrail:
    - NEVER calls Groq, Tavily, RSS, requests, httpx, urllib, or any remote network service.
    - Zero network egress.
    - Rejects conversational noise and small talk.
    - Scrubs sensitive credentials before persisting to memory store.
    """

    # High-confidence explicit declaration patterns
    PREFERENCE_PATTERNS = [
        r'\b(?:i\s+prefer|i\s+prefer\s+using)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:i\s+like|i\s+love)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:i\s+always\s+use|i\s+use)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:my\s+favorite|my\s+preferred)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:from\s+now\s+on[,\s]+call\s+me|always\s+call\s+me|call\s+me)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:i\s+hate|i\s+dislike|i\s+don\'?t\s+like)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:my\s+name\s+is|i\s+am)\s+([A-Za-z0-9_\s]{2,30})',
    ]

    PROJECT_PATTERNS = [
        r'\b(?:(?:my|our)\s+project\s+is\s+called|project\s+name\s+is)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:(?:my|our|the)\s+project\s+is)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:(?:the|our|my)\s+project\s+uses|our\s+stack\s+is|we\s+use)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:the\s+architecture\s+is|architecture\s+uses)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:we\s+are\s+building|i\s+am\s+building|building\s+a)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:project\s+deadline\s+is|deadline\s+for\s+my\s+project\s+is)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
    ]

    TASK_PATTERNS = [
        r'\b(?:remember\s+to|don\'?t\s+forget\s+to|remind\s+me\s+to)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:i\s+need\s+to|i\s+have\s+to|i\s+must)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
    ]

    FACT_PATTERNS = [
        r'\b(?:remember\s+that|note\s+that|keep\s+in\s+mind\s+that)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
        r'\b(?:the\s+rule\s+is|fact\s*:)\s+(.+?)(?:(?<!\d)[.!?](?:\s|$)|$)',
    ]

    # Conversational non-memory phrases that must never become memories
    DISQUALIFYING_PHRASES = [
        "what is", "who is", "where is", "when is", "why is", "how do", "how is",
        "can you", "could you", "would you", "will you", "please tell me",
        "hello", "hey", "hi", "good morning", "good evening", "thank you", "thanks",
        "bye", "ok", "okay", "sure", "cool", "test", "testing"
    ]

    def __init__(self, memory_store, groq_api_key: str = "", *args, **kwargs):
        self.memory_store = memory_store
        # Note: groq_api_key accepted purely for constructor compatibility, but NEVER used.
        self._cloud_calls_made = 0

    def extract_and_store(
        self,
        user_prompt: str,
        ai_reply: str,
        intent: str = "GENERAL_AI"
    ) -> List[Dict[str, Any]]:
        """
        Deterministically extracts meaningful user memories without any remote network calls.
        Returns a list of created/updated memory records.
        """
        if not user_prompt or not user_prompt.strip():
            return []

        prompt_clean = user_prompt.strip()
        lowered_prompt = prompt_clean.lower()
        extracted_memories = []

        # Disqualify trivial questions and small talk
        if any(lowered_prompt.startswith(p) for p in self.DISQUALIFYING_PHRASES) and not any(kw in lowered_prompt for kw in ["remember", "call me", "my favorite", "my project"]):
            return []

        # 1. TEMPORARY_NEWS heuristic for verified LIVE_WEB results
        if intent == "LIVE_WEB" and ai_reply and len(ai_reply) > 50:
            if any(kw in lowered_prompt for kw in ["news", "latest", "winner", "champion", "release", "event", "final"]):
                first_sentence = ai_reply.split(".")[0].strip()
                if len(first_sentence) > 20 and not self.memory_store.contains_secrets(first_sentence):
                    expires_str = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
                    mem = self.memory_store.add_memory(
                        category="TEMPORARY_NEWS",
                        content=f"Recent Verified Event: {first_sentence}",
                        importance="MEDIUM",
                        expires_at=expires_str
                    )
                    if mem:
                        extracted_memories.append(mem)

        # 2. USER_PREFERENCE Extraction
        for pattern in self.PREFERENCE_PATTERNS:
            match = re.search(pattern, prompt_clean, re.IGNORECASE)
            if match:
                fact = match.group(0).strip()
                # Clean prefix trailing punctuation
                fact = re.sub(r'^[,\s]+|[,\s]+$', '', fact)
                if self._is_valid_memory_content(fact):
                    # Format into clear preference statement
                    pref_statement = f"User preference: {fact}"
                    mem = self.memory_store.add_memory(
                        category="USER_PREFERENCE",
                        content=pref_statement,
                        importance="HIGH"
                    )
                    if mem:
                        extracted_memories.append(mem)
                break

        # 3. PROJECT_CONTEXT Extraction
        for pattern in self.PROJECT_PATTERNS:
            match = re.search(pattern, prompt_clean, re.IGNORECASE)
            if match:
                fact = match.group(0).strip()
                fact = re.sub(r'^[,\s]+|[,\s]+$', '', fact)
                if self._is_valid_memory_content(fact):
                    proj_statement = f"Project fact: {fact}"
                    mem = self.memory_store.add_memory(
                        category="PROJECT_CONTEXT",
                        content=proj_statement,
                        importance="HIGH"
                    )
                    if mem:
                        extracted_memories.append(mem)
                break

        # 4. TASK Extraction
        for pattern in self.TASK_PATTERNS:
            match = re.search(pattern, prompt_clean, re.IGNORECASE)
            if match:
                item = match.group(1).strip()
                if self._is_valid_memory_content(item):
                    task_statement = f"User task: {item}"
                    mem = self.memory_store.add_memory(
                        category="TASK",
                        content=task_statement,
                        importance="MEDIUM"
                    )
                    if mem:
                        extracted_memories.append(mem)
                break

        # 5. GENERAL_KNOWLEDGE / FACT Extraction
        for pattern in self.FACT_PATTERNS:
            match = re.search(pattern, prompt_clean, re.IGNORECASE)
            if match:
                fact = match.group(1).strip()
                if self._is_valid_memory_content(fact):
                    fact_statement = f"User note: {fact}"
                    mem = self.memory_store.add_memory(
                        category="GENERAL_KNOWLEDGE",
                        content=fact_statement,
                        importance="HIGH"
                    )
                    if mem:
                        extracted_memories.append(mem)
                break

        return extracted_memories

    def _is_valid_memory_content(self, text: str) -> bool:
        """Validates that candidate content is non-empty, non-trivial, and secret-free."""
        if not text or len(text.strip()) < 5:
            return False
        if self.memory_store.contains_secrets(text):
            return False
        if self.memory_store.is_trivial(text):
            return False
        return True
