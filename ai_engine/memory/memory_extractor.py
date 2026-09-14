import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List

class MemoryExtractor:
    """
    Part 3 & Part 4 — Memory Extractor
    Analyzes completed user-assistant interaction turns and automatically extracts
    structured memories (User preferences, Project facts, News, Improvements).
    """

    def __init__(self, memory_store, groq_api_key: str = ""):
        self.memory_store = memory_store
        self.groq_api_key = groq_api_key

    def extract_and_store(self, user_prompt: str, ai_reply: str, intent: str = "GENERAL_AI"):
        """
        Extracts meaningful information from interaction and saves to LongTermMemoryStore.
        Can run non-blocking or lightweight post-turn execution.
        """
        if not user_prompt or not ai_reply:
            return

        # 1. Automatic Fast Rule-Based Extraction for TEMPORARY_NEWS
        if intent == "LIVE_WEB" and len(ai_reply) > 50:
            lowered_p = user_prompt.lower()
            if any(kw in lowered_p for kw in ["news", "latest", "winner", "champion", "release", "event", "final"]):
                first_sentence = ai_reply.split(".")[0].strip()
                if len(first_sentence) > 20 and not self.memory_store.contains_secrets(first_sentence):
                    # Expiration date: 14 days from today
                    expires_str = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
                    self.memory_store.add_memory(
                        category="TEMPORARY_NEWS",
                        content=f"Recent Verified Event: {first_sentence}",
                        importance="MEDIUM",
                        expires_at=expires_str
                    )

        # 2. LLM Extraction (Fast JSON payload call if GROQ API Key available)
        if not self.groq_api_key:
            return

        extraction_system_prompt = (
            "Analyze the conversation exchange between user and AI assistant.\n"
            "Extract ONLY important facts, user preferences, or project details useful for future conversations.\n"
            "Ignore trivial greetings, small talk, passwords, tokens, or API keys.\n\n"
            "Respond ONLY with a valid JSON object matching this exact schema:\n"
            "{\n"
            '  "memories": [\n'
            '    {\n'
            '      "category": "USER_PREFERENCE" | "PROJECT_CONTEXT" | "GENERAL_KNOWLEDGE" | "TEMPORARY_NEWS" | "IMPROVEMENT",\n'
            '      "importance": "HIGH" | "MEDIUM" | "LOW",\n'
            '      "content": "Fact description"\n'
            '    }\n'
            '  ]\n'
            "}"
        )

        user_content = f"USER: {user_prompt}\nASSISTANT: {ai_reply}"

        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": extraction_system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.0,
                "max_tokens": 150,
                "response_format": {"type": "json_object"}
            }
            res = requests.post(url, headers=headers, json=payload, timeout=2.0)
            if res.status_code == 200:
                parsed = json.loads(res.json()["choices"][0]["message"]["content"])
                extracted_items = parsed.get("memories", [])
                for item in extracted_items:
                    cat = item.get("category", "GENERAL_KNOWLEDGE")
                    content = item.get("content", "")
                    imp = item.get("importance", "MEDIUM")
                    if content and not self.memory_store.contains_secrets(content):
                        exp_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d") if cat == "TEMPORARY_NEWS" else None
                        self.memory_store.add_memory(
                            category=cat,
                            content=content,
                            importance=imp,
                            expires_at=exp_date
                        )
        except Exception:
            pass
