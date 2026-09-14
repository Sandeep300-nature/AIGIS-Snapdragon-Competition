import os
import time
import socket
import requests
from typing import List, Dict, Any, Tuple, Optional

class ProviderRouter:
    """
    Multi-Provider AI Router for AIGIS.
    Abstracts LLM execution across Groq, OpenAI, Claude (Anthropic), Gemini, and Ollama (Local).
    Implements automatic failover routing: Preferred Provider -> Secondary Providers -> Ollama (Local).
    """

    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.claude_api_key = os.getenv("CLAUDE_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

    def is_internet_available(self) -> bool:
        """Quick 1.0s socket test to check internet connectivity."""
        try:
            socket.setdefaulttimeout(1.0)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("8.8.8.8", 53))
            s.close()
            return True
        except Exception:
            return False

    def route_and_execute(
        self,
        messages: List[Dict[str, str]],
        grounded_content: str,
        preferred_provider: str = "groq"
    ) -> Tuple[str, str, bool]:
        """
        Executes prompt via preferred provider with automatic failover chain.
        Returns: (reply_text, provider_display_name, is_offline)
        """
        is_online = self.is_internet_available()

        # If internet is completely offline, fall back directly to Ollama
        if not is_online:
            reply, provider_name = self.call_ollama(grounded_content)
            return reply, "Ollama (Offline Mode)", True

        # Build fallback execution order starting with requested/preferred provider
        provider_chain = self._build_provider_chain(preferred_provider.lower())

        for provider in provider_chain:
            try:
                if provider == "groq":
                    reply, p_name = self.call_groq(messages)
                    if reply:
                        return reply, p_name, False
                elif provider == "openai":
                    reply, p_name = self.call_openai(messages)
                    if reply:
                        return reply, p_name, False
                elif provider == "claude":
                    reply, p_name = self.call_claude(messages)
                    if reply:
                        return reply, p_name, False
                elif provider == "gemini":
                    reply, p_name = self.call_gemini(grounded_content)
                    if reply:
                        return reply, p_name, False
                elif provider == "ollama":
                    reply, p_name = self.call_ollama(grounded_content)
                    if reply:
                        return reply, p_name, False
            except Exception as e:
                # Log exception and continue to next provider in fallback chain
                print(f"[PROVIDER ROUTER] Provider '{provider}' failed: {e}. Switching to next provider...")

        # Final safety fallback to Ollama
        reply, p_name = self.call_ollama(grounded_content)
        return reply, p_name, True

    def _build_provider_chain(self, preferred: str) -> List[str]:
        all_providers = ["groq", "gemini", "openai", "claude", "ollama"]
        chain = []
        if preferred in all_providers:
            chain.append(preferred)
        for p in all_providers:
            if p not in chain:
                chain.append(p)
        return chain

    def call_groq(self, messages: List[Dict[str, str]]) -> Tuple[Optional[str], str]:
        if not self.groq_api_key:
            return None, "Groq (No API Key)"

        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json"
        }
        url = "https://api.groq.com/openai/v1/chat/completions"

        # Attempt 1: primary model llama-3.3-70b-versatile
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 700
        }
        res = requests.post(url, headers=headers, json=payload, timeout=12.0)
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"], "Groq (llama-3.3-70b)"

        # Attempt 2: fast model llama-3.1-8b-instant on rate limit / 429
        if res.status_code in (429, 503):
            time.sleep(1.0)
            payload["model"] = "llama-3.1-8b-instant"
            res2 = requests.post(url, headers=headers, json=payload, timeout=10.0)
            if res2.status_code == 200:
                return res2.json()["choices"][0]["message"]["content"], "Groq (llama-3.1-8b-instant)"

        return None, "Groq (Failed)"

    def call_openai(self, messages: List[Dict[str, str]]) -> Tuple[Optional[str], str]:
        if not self.openai_api_key:
            return None, "OpenAI (No API Key)"

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 700
        }
        res = requests.post(url, headers=headers, json=payload, timeout=12.0)
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"], "OpenAI (gpt-4o-mini)"
        return None, "OpenAI (Failed)"

    def call_claude(self, messages: List[Dict[str, str]]) -> Tuple[Optional[str], str]:
        if not self.claude_api_key:
            return None, "Claude (No API Key)"

        headers = {
            "x-api-key": self.claude_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        url = "https://api.anthropic.com/v1/messages"
        
        system_content = ""
        user_messages = []
        for m in messages:
            if m.get("role") == "system":
                system_content += m.get("content", "") + "\n"
            else:
                user_messages.append({"role": m.get("role"), "content": m.get("content")})

        payload = {
            "model": "claude-3-haiku-20240307",
            "system": system_content.strip(),
            "messages": user_messages,
            "max_tokens": 700
        }
        res = requests.post(url, headers=headers, json=payload, timeout=12.0)
        if res.status_code == 200:
            return res.json()["content"][0]["text"], "Claude (claude-3-haiku)"
        return None, "Claude (Failed)"

    def call_gemini(self, grounded_content: str) -> Tuple[Optional[str], str]:
        if not self.gemini_api_key:
            return None, "Gemini (No API Key)"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": grounded_content}]}]
        }
        res = requests.post(url, headers=headers, json=payload, timeout=12.0)
        if res.status_code == 200:
            candidates = res.json().get("candidates", [])
            if candidates:
                text = candidates[0]["content"]["parts"][0]["text"]
                return text, "Gemini (gemini-1.5-flash)"
        return None, "Gemini (Failed)"

    def call_ollama(self, grounded_content: str) -> Tuple[str, str]:
        try:
            payload = {"model": "llama3", "prompt": grounded_content, "stream": False}
            res = requests.post(self.ollama_url, json=payload, timeout=5.0)
            if res.status_code == 200:
                reply = res.json().get("response", "")
                if reply:
                    return reply, "Ollama (Local LLM)"
        except Exception:
            pass
        return "I am currently unable to reach remote AI services or local Ollama core, sir.", "Ollama (Offline)"
