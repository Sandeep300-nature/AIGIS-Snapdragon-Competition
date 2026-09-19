import os
import sys
import time
from typing import Optional, Dict, Any
from .base_engine import BaseAIEngine, EngineResponse
from .local_engine import LocalEngine
from .cloud_engine import CloudEngine
from .snapdragon_engine import SnapdragonNPUEngine, HardwareNotSupportedError

# Compatibility aliases
SmolLM2Engine = LocalEngine
GroqEngine = CloudEngine

ai_engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)

try:
    from hardware.detector import HardwareDetector
except ImportError:
    from ai_engine.hardware.detector import HardwareDetector

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

try:
    from privacy import PrivacyGuard, PrivacyMode, PrivateIntent, ContentClassifier
except ImportError:
    try:
        from ai_engine.privacy import PrivacyGuard, PrivacyMode, PrivateIntent, ContentClassifier
    except ImportError:
        pass

try:
    from actions import ActionSafetyGuard
except ImportError:
    try:
        from ai_engine.actions import ActionSafetyGuard
    except ImportError:
        pass


# Intent match patterns for private queries
MEMORY_QUERY_PATTERNS = [
    "what do you remember",
    "what do you know about me",
    "know about me",
    "my memories",
    "search my memories",
    "remember about me",
    "recall about me",
    "do you remember",
    "what do you recall",
    "what memories",
    "my memory",
    "stored memories",
    "what have you remembered",
    # Natural query variants (asking about previously stored facts/instructions)
    "ask you to remember",
    "asked you to remember",
    "ask you to recall",
    "asked you to recall",
    "tell you to remember",
    "told you to remember",
    "what did i ask you to remember",
    "what did i tell you to remember",
    "what did i ask you to recall",
    "what did i tell you to recall",
    "what i asked you to remember",
    "what i told you to remember",
    "what you remember",
    "what you recall",
    "things to remember",
    "things you remember",
]

DOCUMENT_QUERY_PATTERNS = [
    "search my files",
    "find in my documents",
    "look in my files",
    "search my documents",
    "find in my files",
    "look through my files",
    "look in documents",
    "find in documents",
    "search in my documents",
    "search files",
    "find in files",
]

PROJECT_QUERY_PATTERNS = [
    "my project",
    "our architecture",
    "the project uses",
    "our project",
    "project status",
    "about my project",
    "in my project",
    "project architecture",
]


class IntentTaskRouter:
    """
    Intelligent Intent & Task Router for AIGIS.
    Directs tasks following a strict hierarchy:
      - Actions & System Info -> Deterministic local execution on-device
      - Private Queries (Memory, Documents, Project) -> Strictly On-Device Local Engine
      - Live/Current Web Info -> Tavily + RSS Search (Anti-hallucination guard)
      - On-Device Intelligence:
          * Tier 1 (NPU Target): Qualcomm AI Hub model via QNN (Snapdragon ARM64)
          * Tier 2 (Local Fallback): SmolLM2-135M via CPU (portable, private)
      - General AI / Cloud:
          * Tier 3 (Cloud / Live Web): Groq Llama-3.3-70b / Tavily facts (Privacy Guard Protected)
    """

    def __init__(
        self,
        local_engine: Optional[LocalEngine] = None,
        cloud_engine: Optional[CloudEngine] = None,
        snapdragon_engine: Optional[SnapdragonNPUEngine] = None,
        hardware_detector: Optional[Any] = None
    ):
        self.local_engine = local_engine or LocalEngine()
        self.cloud_engine = cloud_engine or CloudEngine()
        self.detector = hardware_detector or HardwareDetector
        self.action_guard = ActionSafetyGuard()

        # Registered engine aliases
        self.smollm2_engine = self.local_engine
        self.groq_engine = self.cloud_engine

        if snapdragon_engine is not None:
            self.snapdragon_engine = snapdragon_engine
        else:
            self.snapdragon_engine = SnapdragonNPUEngine(
                hardware_detector=self.detector,
                fallback_engine=self.local_engine,
                auto_fallback=True
            )

    def get_active_local_engine(self) -> BaseAIEngine:
        """
        Hardware-Aware Polymorphic Engine Selector:
        Tier 1: SnapdragonNPUEngine (ARM64 + QNN Hexagon NPU)
        Tier 2: SmolLM2Engine / LocalEngine (portable x86_64 CPU fallback)
        """
        if self.snapdragon_engine and self.snapdragon_engine.is_available():
            return self.snapdragon_engine
        return self.local_engine

    def classify_intent(self, prompt: str) -> Dict[str, Any]:
        """Classifies prompt into ACTION, SYSTEM_INFO, MEMORY_QUERY, DOCUMENT_QUERY, PRIVATE_PROJECT_QUERY, LIVE_WEB, or GENERAL_AI."""
        lowered = prompt.strip().lower()

        # 1. Executable Actions (Desktop app launcher, system controls, URL navigation, safety boundary checks)
        is_desktop_action = any(kw in lowered for kw in [
            "open notepad", "open calc", "open code", "open terminal",
            "volume up", "volume down", "mute", "lock screen"
        ])
        is_action = (
            is_desktop_action or
            check_open_website_shortcut(prompt) or
            extract_url_from_text(prompt) or
            bool(self.action_guard.validate_raw_prompt(prompt)) or
            bool(self.action_guard.parse_from_prompt(prompt))
        )
        if is_action:
            return {
                "intent": "ACTION",
                "privacyIntent": "PUBLIC",
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
                "privacyIntent": "PUBLIC",
                "preferredEngine": "local",
                "reason": "Deterministic system clock, hardware telemetry, or assistant identity/capabilities handled locally."
            }

        # 2b. Private Memory Queries -> Strictly On-Device Local
        if any(kw in lowered for kw in MEMORY_QUERY_PATTERNS):
            return {
                "intent": "MEMORY_QUERY",
                "privacyIntent": "MEMORY_QUERY",
                "preferredEngine": "local",
                "reason": "Memory inquiries access private local store and must execute on-device."
            }

        # 2c. Private Document / File Queries -> Strictly On-Device Local
        if any(kw in lowered for kw in DOCUMENT_QUERY_PATTERNS):
            return {
                "intent": "DOCUMENT_QUERY",
                "privacyIntent": "DOCUMENT_QUERY",
                "preferredEngine": "local",
                "reason": "Document search inquiries access private local files and must execute on-device."
            }

        # 2d. Private Project Queries -> Strictly On-Device Local
        if any(kw in lowered for kw in PROJECT_QUERY_PATTERNS):
            return {
                "intent": "PRIVATE_PROJECT_QUERY",
                "privacyIntent": "PRIVATE_PROJECT_QUERY",
                "preferredEngine": "local",
                "reason": "Project architecture inquiries access private local context and must execute on-device."
            }

        # 3. Live / Current Web Information
        intent_data = classify_intent_llm(prompt, self.cloud_engine.api_key)
        detected_intent = intent_data.get("intent", "GENERAL_AI")
        search_q = intent_data.get("search_query", prompt) or prompt

        if detected_intent == "LIVE_WEB" or is_time_sensitive_query(prompt):
            return {
                "intent": "LIVE_WEB",
                "privacyIntent": "PUBLIC",
                "preferredEngine": "live_web",
                "searchQuery": search_q,
                "reason": "Current or real-time web inquiry requires live search."
            }

        # 4. General AI
        cloud_info = self.cloud_engine.get_engine_info()
        if cloud_info.get("configured", False):
            return {
                "intent": "GENERAL_AI",
                "privacyIntent": "PUBLIC",
                "preferredEngine": "cloud",
                "reason": "General knowledge inquiry routed to cloud AI for synthesis."
            }

        return {
            "intent": "GENERAL_AI",
            "privacyIntent": "PUBLIC",
            "preferredEngine": "local",
            "reason": "General inquiry processed locally on-device via SmolLM2."
        }

    def route_and_generate(
        self,
        prompt: str,
        session_id: str = "default-session",
        mode: str = "auto",
        response_language: str = "en",
        memory_context: str = "",
        doc_context: str = "",
        privacy_mode: str = "AUTO",
        **kwargs
    ) -> EngineResponse:
        """
        Executes the privacy-gated multi-tier routing policy and returns an EngineResponse.
        """
        normalized_mode = (mode or "auto").strip().lower()
        classification = self.classify_intent(prompt)
        intent = classification.get("intent", "GENERAL_AI")
        privacy_intent = classification.get("privacyIntent", "PUBLIC")

        # =========================================================================
        # 0. PRIVATE INTENTS (MEMORY_QUERY, DOCUMENT_QUERY, PRIVATE_PROJECT_QUERY)
        # Strictly routed to on-device local engine; zero network or cloud usage.
        # =========================================================================
        if intent in ["MEMORY_QUERY", "DOCUMENT_QUERY", "PRIVATE_PROJECT_QUERY"]:
            active_engine = self.get_active_local_engine()
            context_blocks = []
            if memory_context and memory_context.strip():
                context_blocks.append(memory_context.strip())
            if doc_context and doc_context.strip():
                context_blocks.append(doc_context.strip())

            augmented_prompt = f"{'\n\n'.join(context_blocks)}\n\nUser Request: {prompt}" if context_blocks else prompt
            resp = active_engine.generate_response(
                prompt=augmented_prompt,
                session_id=session_id,
                response_language=response_language,
                raw_user_prompt=prompt,
                **kwargs
            )
            resp.metadata["routingMode"] = "enforced_private_local"
            resp.metadata["routingReason"] = classification.get("reason", "Private query handled locally on-device.")
            resp.metadata["privacyMode"] = privacy_mode
            resp.metadata["networkUsed"] = False
            resp.metadata["privateContextUsed"] = bool(context_blocks)
            resp.metadata["privacyIntent"] = intent
            return resp

        # =========================================================================
        # 1. EXPLICIT LOCAL MODE
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
                        "reason": "Explicit Local mode blocks external web and cloud access.",
                        "privacyMode": privacy_mode,
                        "privateContextUsed": bool(memory_context or doc_context),
                        "privacyIntent": privacy_intent
                    }
                )

            active_engine = self.get_active_local_engine()
            context_blocks = []
            if memory_context and memory_context.strip():
                context_blocks.append(memory_context.strip())
            if doc_context and doc_context.strip():
                context_blocks.append(doc_context.strip())
            augmented_prompt = f"{'\n\n'.join(context_blocks)}\n\nUser Request: {prompt}" if context_blocks else prompt

            resp = active_engine.generate_response(
                prompt=augmented_prompt,
                session_id=session_id,
                response_language=response_language,
                raw_user_prompt=prompt,
                **kwargs
            )
            resp.metadata["routingMode"] = "enforced_local"
            resp.metadata["routingReason"] = "User explicitly selected Local On-Device processing."
            resp.metadata["privacyMode"] = privacy_mode
            resp.metadata["networkUsed"] = False
            resp.metadata["privateContextUsed"] = bool(context_blocks)
            resp.metadata["privacyIntent"] = privacy_intent
            return resp

        # =========================================================================
        # 2. EXPLICIT CLOUD MODE
        # =========================================================================
        elif normalized_mode == "cloud":
            guard = PrivacyGuard(mode=privacy_mode)
            safe_ctx = guard.filter_context_for_cloud(long_mem=memory_context, rag_ctx=doc_context)
            safe_mem = safe_ctx.long_memory
            safe_doc = safe_ctx.rag_context
            cloud_prompt = prompt
            if safe_mem or safe_doc:
                prefix_parts = [p for p in (safe_mem, safe_doc) if p]
                cloud_prompt = f"{'\n\n'.join(prefix_parts)}\n\nUser Request: {prompt}"

            if intent == "LIVE_WEB":
                search_q = classification.get("searchQuery", prompt)
                search_res = search_live_web(search_q)
                web_ctx = search_res.get("web_context", "")
                if search_res.get("success") and web_ctx:
                    resp = self.cloud_engine.generate_response(
                        prompt=cloud_prompt,
                        session_id=session_id,
                        response_language=response_language,
                        web_context=web_ctx,
                        **kwargs
                    )
                    resp.metadata["routingMode"] = "enforced_cloud"
                    resp.metadata["webSearchUsed"] = True
                    resp.metadata["networkUsed"] = True
                    resp.metadata["privacyMode"] = privacy_mode
                    resp.metadata["privateContextUsed"] = bool(safe_mem or safe_doc)
                    resp.metadata["privacyIntent"] = privacy_intent
                    return resp

            resp = self.cloud_engine.generate_response(
                prompt=cloud_prompt,
                session_id=session_id,
                response_language=response_language,
                **kwargs
            )
            resp.metadata["routingMode"] = "enforced_cloud"
            resp.metadata["routingReason"] = "User explicitly selected Cloud AI processing."
            resp.metadata["privacyMode"] = privacy_mode
            resp.metadata["networkUsed"] = True
            resp.metadata["privateContextUsed"] = bool(safe_mem or safe_doc)
            resp.metadata["privacyIntent"] = privacy_intent
            return resp

        # =========================================================================
        # 3. SMART AUTO ROUTING (Tiers 1, 2, 3, 4)
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
                resp.metadata["privacyMode"] = privacy_mode
                resp.metadata["networkUsed"] = False
                resp.metadata["privateContextUsed"] = False
                resp.metadata["privacyIntent"] = privacy_intent
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
                                cloud_resp.metadata["privacyMode"] = privacy_mode
                                cloud_resp.metadata["privateContextUsed"] = False
                                cloud_resp.metadata["privacyIntent"] = privacy_intent
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
                            "auditLog": audit_log,
                            "privacyMode": privacy_mode,
                            "privateContextUsed": False,
                            "privacyIntent": privacy_intent
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
                            "reason": "Search returned no verified facts or network was unreachable.",
                            "privacyMode": privacy_mode,
                            "privateContextUsed": False,
                            "privacyIntent": privacy_intent
                        }
                    )

            # Tier 4: General AI
            else:
                preferred = classification["preferredEngine"]
                if preferred == "cloud":
                    guard = PrivacyGuard(mode=privacy_mode)
                    safe_ctx = guard.filter_context_for_cloud(
                        long_mem=memory_context,
                        rag_ctx=doc_context
                    )
                    safe_mem = safe_ctx.long_memory
                    safe_doc = safe_ctx.rag_context
                    cloud_prompt = prompt
                    if safe_mem or safe_doc:
                        prefix_parts = [p for p in (safe_mem, safe_doc) if p]
                        cloud_prompt = f"{'\n\n'.join(prefix_parts)}\n\nUser Request: {prompt}"

                    resp = self.cloud_engine.generate_response(
                        prompt=cloud_prompt,
                        session_id=session_id,
                        response_language=response_language,
                        **kwargs
                    )
                    resp.metadata["routingMode"] = "auto_cloud"
                    resp.metadata["routingReason"] = classification["reason"]
                    resp.metadata["privacyMode"] = privacy_mode
                    resp.metadata["networkUsed"] = True
                    resp.metadata["privateContextUsed"] = bool(safe_mem or safe_doc)
                    resp.metadata["privacyIntent"] = privacy_intent
                    return resp
                else:
                    active_engine = self.get_active_local_engine()
                    context_blocks = []
                    if memory_context and memory_context.strip():
                        context_blocks.append(memory_context.strip())
                    if doc_context and doc_context.strip():
                        context_blocks.append(doc_context.strip())
                    local_prompt = f"{'\n\n'.join(context_blocks)}\n\nUser Request: {prompt}" if context_blocks else prompt

                    resp = active_engine.generate_response(
                        prompt=local_prompt,
                        session_id=session_id,
                        response_language=response_language,
                        **kwargs
                    )
                    resp.metadata["routingMode"] = "auto_local"
                    resp.metadata["routingReason"] = classification["reason"]
                    resp.metadata["privacyMode"] = privacy_mode
                    resp.metadata["networkUsed"] = False
                    resp.metadata["privateContextUsed"] = bool(context_blocks)
                    resp.metadata["privacyIntent"] = privacy_intent
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
        active_backend = "snapdragon_npu" if (self.snapdragon_engine and self.snapdragon_engine.is_available()) else "smollm2_cpu"
        return {
            "localEngine": self.local_engine.get_engine_info(),
            "cloudEngine": self.cloud_engine.get_engine_info(),
            "snapdragonEngine": self.snapdragon_engine.get_engine_info() if self.snapdragon_engine else None,
            "activeLocalBackend": active_backend,
            "supportedModes": ["auto", "local", "cloud"],
            "privacyModes": ["LOCAL_ONLY", "AUTO", "CLOUD_PERMITTED"]
        }
