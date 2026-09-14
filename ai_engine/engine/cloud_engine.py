import os
import time
import requests
from typing import Dict, Any, Optional
from .base_engine import BaseAIEngine, EngineResponse


class CloudEngine(BaseAIEngine):
    """
    Remote Cloud AI Engine connecting to hosted LLM APIs (default: Groq).
    Explicitly tags all outputs as cloud-processed and reports real API latency.
    """

    DEFAULT_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    DEFAULT_MODEL = "llama-3.3-70b-versatile"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_url: Optional[str] = None
    ):
        self.api_key = api_key if api_key is not None else os.getenv("GROQ_API_KEY", "").strip()
        self.model = model or os.getenv("GROQ_MODEL", self.DEFAULT_MODEL)
        self.api_url = api_url or os.getenv("GROQ_URL", self.DEFAULT_GROQ_URL)

    def generate_response(
        self,
        prompt: str,
        session_id: str = "default-session",
        response_language: str = "en",
        **kwargs
    ) -> EngineResponse:
        start_time = time.perf_counter()

        if not self.api_key:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return EngineResponse(
                reply="Cloud AI processing was requested, but GROQ_API_KEY is not configured in the environment. Please configure your API key or switch to Local On-Device processing, sir.",
                provider="Cloud Engine -> Groq (Unconfigured)",
                engine="cloud",
                badge="☁ Cloud (No API Key)",
                latencyMs=elapsed_ms,
                metadata={
                    "configured": False,
                    "model": self.model,
                    "error": "GROQ_API_KEY missing"
                }
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        system_instruction = kwargs.get("system_instruction") or (
            "You are AIGIS, a personal AI computer assistant. "
            "Respond composed, concise, helpful, and sharp. Address the user as 'sir'."
        )
        if kwargs.get("web_context"):
            system_instruction += (
                "\n\nLIVE DATA CONTEXT (FETCHED FROM INTERNET):\n"
                + kwargs["web_context"]
                + "\n\nCRITICAL: Answer based strictly on the verified facts above. Never hallucinate outdated information."
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.6,
            "max_tokens": 1024
        }

        try:
            res = requests.post(self.api_url, json=payload, headers=headers, timeout=12.0)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            if res.status_code == 200:
                data = res.json()
                reply_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return EngineResponse(
                    reply=reply_text.strip(),
                    provider=f"Cloud AI -> Groq ({self.model})",
                    engine="cloud",
                    badge="☁ Cloud (Processed using cloud AI)",
                    latencyMs=elapsed_ms,
                    metadata={
                        "model": self.model,
                        "usage": data.get("usage", {}),
                        "statusCode": 200
                    }
                )
            else:
                return EngineResponse(
                    reply=f"Cloud AI service returned status {res.status_code}: {res.text[:150]}",
                    provider=f"Cloud AI -> Groq (HTTP {res.status_code})",
                    engine="cloud",
                    badge="☁ Cloud (Error)",
                    latencyMs=elapsed_ms,
                    metadata={"statusCode": res.status_code, "error": res.text[:200]}
                )

        except requests.exceptions.Timeout:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return EngineResponse(
                reply="Cloud AI request timed out. The remote endpoint did not respond in time, sir.",
                provider="Cloud AI -> Timeout",
                engine="cloud",
                badge="☁ Cloud (Timeout)",
                latencyMs=elapsed_ms,
                metadata={"error": "Request timed out"}
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return EngineResponse(
                reply=f"Cloud AI service encounter an error: {str(e)}",
                provider="Cloud AI -> Connection Error",
                engine="cloud",
                badge="☁ Cloud (Connection Failed)",
                latencyMs=elapsed_ms,
                metadata={"error": str(e)}
            )

    def get_engine_info(self) -> Dict[str, Any]:
        return {
            "engine": "cloud",
            "provider": "Groq",
            "model": self.model,
            "configured": bool(self.api_key),
            "endpoint": self.api_url
        }
