import os
import sys
import time
from typing import Optional, Dict, Any
from .base_engine import BaseAIEngine, EngineResponse
from .local_engine import LocalEngine
from .cloud_engine import CloudEngine

ai_engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)

try:
    from web_search import (
        classify_intent_llm,
        search_live_web,
        is_time_sensitive_query,
        check_open_website_shortcut,
        extract_url_from_text
    )
except ImportError:
    from ai_engine.web_search import (
        classify_intent_llm,
        search_live_web,
        is_time_sensitive_query,
        check_open_website_shortcut,
        extract_url_from_text
    )


class IntentTaskRouter:
    """
    Intelligent Intent & Task Router for AIGIS.
    Directs tasks following a strict 6-tier policy:
      1. Executable Actions (Desktop apps, media controls, web navigation) -> Local on-device
      2. Deterministic System Info (OS clock, hardware telemetry, privacy) -> Local on-device
      3. Live/Current Web Info (Sports, news, weather, live facts) -> Tavily + RSS Search (Never SmolLM2)
      4. General AI (Auto Mode) -> Groq when configured/reachable, SmolLM2 when offline/unconfigured
      5. Explicit Local Mode -> SmolLM2 only for general AI, local disclaimer for live web
      6. Explicit Cloud Mode -> CloudEngine only, never silent local fallback
    """

    def __init__(
        self,
        local_engine: Optional[LocalEngine] = None,
        cloud_engine: Optional[CloudEngine] = None
    ):
        self.local_engine = local_engine or LocalEngine()
        self.cloud_engine = cloud_engine or CloudEngine()

    def classify_intent(self, prompt: str) -> Dict[str, Any]:
        """Classifies prompt into ACTION, SYSTEM_INFO, LIVE_WEB, or GENERAL_AI."""
        lowered = prompt.strip().lower()

        # 1. Executable Actions (Desktop app launcher, system controls, URL navigation)
        is_desktop_action = any(kw in lowered for kw in [
            "open notepad", "open calc", "open code", "open terminal",
            "volume up", "volume down", "mute", "lock screen"
        ])
        if is_desktop_action or check_open_website_shortcut(prompt) or extract_url_from_text(prompt):
            return {
                "intent": "ACTION",
                "preferredEngine": "local",
                "reason": "Desktop and web navigation actions must execute on-device."
            }

        # 2. Deterministic System Information & Assistant Identity/Capabilities
        is_system_info = any(kw in lowered for kw in [
            "time", "date", "clock", "what time", "current time",
            "hardware", "specs", "specifications", "npu", "cpu", "gpu", "ram", "memory",
            "snapdragon", "telemetry", "system status",
            "where are you running", "is this local", "are you local",
            "who are you", "what are you", "what is aigis", "what can you do", "capabilities", "tell me about yourself"
        ])
        if is_system_info:
            return {
                "intent": "SYSTEM_INFO",
                "preferredEngine": "local",
                "reason": "Deterministic system clock, hardware telemetry, or assistant identity/capabilities handled locally."
            }

        # 3. Live / Current Web Information
        intent_data = classify_intent_llm(prompt, self.cloud_engine.api_key)
        detected_intent = intent_data.get("intent", "GENERAL_AI")
        search_q = intent_data.get("search_query", prompt) or prompt

        if detected_intent == "LIVE_WEB" or is_time_sensitive_query(prompt):
            return {
                "intent": "LIVE_WEB",
                "preferredEngine": "live_web",
                "searchQuery": search_q,
                "reason": "Current or real-time web inquiry requires live search."
            }

        # 4. General AI
        cloud_info = self.cloud_engine.get_engine_info()
        if cloud_info.get("configured", False):
            return {
                "intent": "GENERAL_AI",
                "preferredEngine": "cloud",
                "reason": "General knowledge inquiry routed to cloud AI for synthesis."
            }

        return {
            "intent": "GENERAL_AI",
            "preferredEngine": "local",
            "reason": "General inquiry processed locally on-device via SmolLM2."
        }

    def route_and_generate(
        self,
        prompt: str,
        session_id: str = "default-session",
        mode: str = "auto",
        response_language: str = "en",
        **kwargs
    ) -> EngineResponse:
        """
        Executes the 6-tier routing policy and returns an EngineResponse.
        """
        normalized_mode = (mode or "auto").strip().lower()
        classification = self.classify_intent(prompt)
        intent = classification.get("intent", "GENERAL_AI")

        # =========================================================================
        # 5. EXPLICIT LOCAL MODE
        # =========================================================================
        if normalized_mode == "local":
            if intent == "LIVE_WEB":
                # Never hallucinate live facts with SmolLM2 in local mode
                return EngineResponse(
                    reply="Current and live information cannot be verified in Local-Only mode without network connectivity, sir.",
                    provider="AIGIS Local Engine -> Privacy Guard",
                    engine="local",
                    badge="⚡ AIGIS Local (Privacy Guard)",
                    latencyMs=0,
                    metadata={
                        "intent": "live_web",
                        "routingMode": "enforced_local",
                        "localInference": False,
                        "networkUsed": False,
                        "verified": False,
                        "reason": "Explicit Local mode blocks external web and cloud access."
                    }
                )

            resp = self.local_engine.generate_response(
                prompt=prompt,
                session_id=session_id,
                response_language=response_language,
                **kwargs
            )
            resp.metadata["routingMode"] = "enforced_local"
            resp.metadata["routingReason"] = "User explicitly selected Local On-Device processing."
            return resp

        # =========================================================================
        # 6. EXPLICIT CLOUD MODE
        # =========================================================================
        elif normalized_mode == "cloud":
            if intent == "LIVE_WEB":
                search_q = classification.get("searchQuery", prompt)
                search_res = search_live_web(search_q)
                web_ctx = search_res.get("web_context", "")
                if search_res.get("success") and web_ctx:
                    resp = self.cloud_engine.generate_response(
                        prompt=prompt,
                        session_id=session_id,
                        response_language=response_language,
                        web_context=web_ctx,
                        **kwargs
                    )
                    resp.metadata["routingMode"] = "enforced_cloud"
                    resp.metadata["webSearchUsed"] = True
                    resp.metadata["networkUsed"] = True
                    return resp

            resp = self.cloud_engine.generate_response(
                prompt=prompt,
                session_id=session_id,
                response_language=response_language,
                **kwargs
            )
            resp.metadata["routingMode"] = "enforced_cloud"
            resp.metadata["routingReason"] = "User explicitly selected Cloud AI processing."
            return resp

        # =========================================================================
        # SMART AUTO ROUTING (Tiers 1, 2, 3, 4)
        # =========================================================================
        else:
            # Tier 1 (ACTION) & Tier 2 (SYSTEM_INFO) -> Local Engine deterministic
            if intent in ["ACTION", "SYSTEM_INFO"]:
                resp = self.local_engine.generate_response(
                    prompt=prompt,
                    session_id=session_id,
                    response_language=response_language,
                    **kwargs
                )
                resp.metadata["routingMode"] = "auto_local"
                resp.metadata["routingReason"] = classification["reason"]
                return resp

            # Tier 3: Current / Live Information -> Web Search (Tavily + RSS)
            elif intent == "LIVE_WEB":
                search_q = classification.get("searchQuery", prompt)
                start_t = time.perf_counter()
                search_res = search_live_web(search_q)
                elapsed_ms = int((time.perf_counter() - start_t) * 1000)

                web_context = search_res.get("web_context", "")
                success = search_res.get("success", False)
                audit_log = search_res.get("audit_log", {})

                if success and web_context:
                    # Case A: Groq is configured and reachable -> synthesize with cloud
                    if self.cloud_engine.get_engine_info().get("configured", False):
                        try:
                            cloud_resp = self.cloud_engine.generate_response(
                                prompt=prompt,
                                session_id=session_id,
                                response_language=response_language,
                                web_context=web_context,
                                **kwargs
                            )
                            if cloud_resp.metadata.get("statusCode") == 200:
                                cloud_resp.metadata["intent"] = "live_web"
                                cloud_resp.metadata["webSearchUsed"] = True
                                cloud_resp.metadata["networkUsed"] = True
                                cloud_resp.metadata["routingMode"] = "auto_live_web_cloud"
                                cloud_resp.provider = f"AIGIS Live Web -> Groq + Tavily"
                                return cloud_resp
                        except Exception:
                            pass

                    # Case B: Groq unconfigured/unavailable -> return verified facts directly
                    clean_reply = self._format_verified_web_facts(web_context)
                    return EngineResponse(
                        reply=clean_reply,
                        provider="AIGIS Live Search -> Tavily Web Facts",
                        engine="cloud",
                        badge="☁ Live Web (Verified Real-Time Facts)",
                        latencyMs=elapsed_ms,
                        metadata={
                            "intent": "live_web",
                            "routingMode": "auto_live_web",
                            "webSearchUsed": True,
                            "webUsed": True,
                            "networkUsed": True,
                            "verified": True,
                            "fallbackUsed": search_res.get("fallback_used", False),
                            "auditLog": audit_log
                        }
                    )
                else:
                    # Case C: Search failed or offline -> Truthful inability to verify
                    return EngineResponse(
                        reply="I cannot verify current or live information while offline or when live search services are unreachable, sir.",
                        provider="AIGIS Anti-Hallucination Guard -> Offline / Unreachable",
                        engine="local",
                        badge="⚡ AIGIS Guard (Unverified)",
                        latencyMs=elapsed_ms,
                        metadata={
                            "intent": "live_web",
                            "routingMode": "auto_live_web_blocked",
                            "webSearchUsed": False,
                            "networkUsed": False,
                            "verified": False,
                            "reason": "Search returned no verified facts or network was unreachable."
                        }
                    )

            # Tier 4: General AI
            else:
                preferred = classification["preferredEngine"]
                if preferred == "cloud":
                    resp = self.cloud_engine.generate_response(
                        prompt=prompt,
                        session_id=session_id,
                        response_language=response_language,
                        **kwargs
                    )
                    resp.metadata["routingMode"] = "auto_cloud"
                    resp.metadata["routingReason"] = classification["reason"]
                    return resp
                else:
                    resp = self.local_engine.generate_response(
                        prompt=prompt,
                        session_id=session_id,
                        response_language=response_language,
                        **kwargs
                    )
                    resp.metadata["routingMode"] = "auto_local"
                    resp.metadata["routingReason"] = classification["reason"]
                    return resp

    def _format_verified_web_facts(self, web_context: str) -> str:
        """Strips internal system prompts/directives and formats verified web facts cleanly."""
        lines = []
        for line in web_context.split("\n"):
            if "CRITICAL COMPLIANCE DIRECTIVES FOR ASSISTANT:" in line or "STRICT DIRECTIVES:" in line:
                break
            lines.append(line)
        cleaned = "\n".join(lines).strip()
        return cleaned or "Verified real-time information was retrieved from live web sources."

    def get_router_status(self) -> Dict[str, Any]:
        return {
            "localEngine": self.local_engine.get_engine_info(),
            "cloudEngine": self.cloud_engine.get_engine_info(),
            "supportedModes": ["auto", "local", "cloud"]
        }
