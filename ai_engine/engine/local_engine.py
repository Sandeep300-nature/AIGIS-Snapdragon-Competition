import sys
import os
import re
import time
from datetime import datetime
from typing import Dict, Any, Optional
from .base_engine import BaseAIEngine, EngineResponse
from .slm_pipeline import LocalSLMPipeline
from .deterministic import (
    parse_time_date_query,
    build_time_date_response,
    parse_telemetry_query,
    build_telemetry_response
)
try:
    from .prompts import get_competition_system_prompt
except ImportError:
    from ai_engine.engine.prompts import get_competition_system_prompt

ai_engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)

try:
    from hardware.detector import HardwareDetector
except ImportError:
    from ai_engine.hardware.detector import HardwareDetector

try:
    from desktop_control import DesktopActionService
    from web_search import (
        check_open_website_shortcut,
        extract_url_from_text,
        classify_intent_llm,
        is_time_sensitive_query
    )
    from actions import ActionSafetyGuard, DefaultActionExecutor, ActionRequest, ActionType
except ImportError:
    from ai_engine.desktop_control import DesktopActionService
    from ai_engine.web_search import (
        check_open_website_shortcut,
        extract_url_from_text,
        classify_intent_llm,
        is_time_sensitive_query
    )
    from ai_engine.actions import ActionSafetyGuard, DefaultActionExecutor, ActionRequest, ActionType


class LocalEngine(BaseAIEngine):
    """
    On-Device AI Engine executing strictly local workloads.
    ZERO external network dependency: all inference and deterministic logic runs on the host PC.
    Priority hierarchy:
      1. Executable desktop & web navigation actions
      2. Deterministic system information (OS clock, hardware telemetry, privacy)
      3. Genuine on-device SLM neural inference for general AI
    """

    def __init__(
        self,
        hardware_detector: Optional[HardwareDetector] = None,
        slm_pipeline: Optional[LocalSLMPipeline] = None,
        desktop_action_service: Optional[DesktopActionService] = None,
        system_prompt: Optional[str] = None
    ):
        self.detector = hardware_detector or HardwareDetector
        self.slm_pipeline = slm_pipeline if slm_pipeline is not None else LocalSLMPipeline()
        self.desktop_action_service = desktop_action_service or DesktopActionService()
        self.action_guard = ActionSafetyGuard()
        self.action_executor = DefaultActionExecutor(self.action_guard, self.desktop_action_service)
        self.system_prompt = system_prompt or get_competition_system_prompt()
        self._cached_capabilities = None

    def _get_capabilities(self) -> Dict[str, Any]:
        if not self._cached_capabilities:
            self._cached_capabilities = self.detector.get_capabilities()
        return self._cached_capabilities

    def get_accelerator_label(self) -> str:
        caps = self._get_capabilities()
        if caps.get("accelerators", {}).get("snapdragonNpu", {}).get("npuAccelerated", False):
            return "Snapdragon Hexagon NPU (QNN)"
        elif caps.get("onnxruntime", {}).get("hasCpuProvider", False):
            return f"Local On-Device ({caps.get('architecture', 'x86_64')} CPU)"
        return "Local On-Device Host"

    def generate_response(
        self,
        prompt: str,
        session_id: str = "default-session",
        response_language: str = "en",
        **kwargs
    ) -> EngineResponse:
        start_time = time.perf_counter()
        now = datetime.now()

        # Extract actual user request, excluding any prepended memory/document context blocks
        raw_user_prompt = kwargs.get("raw_user_prompt") or kwargs.get("user_prompt")
        if not raw_user_prompt:
            if "\n\nUser Request: " in prompt:
                user_request = prompt.split("\n\nUser Request: ", 1)[1].strip()
            elif "\nUser Request: " in prompt:
                user_request = prompt.split("\nUser Request: ", 1)[1].strip()
            elif prompt.startswith("User Request: "):
                user_request = prompt[len("User Request: "):].strip()
            else:
                user_request = prompt.strip()
        else:
            user_request = str(raw_user_prompt).strip()

        request_lowered = user_request.lower()

        caps = self._get_capabilities()
        accelerator_label = self.get_accelerator_label()
        provider_name = f"AIGIS Local Engine -> {accelerator_label}"

        # =========================================================================
        # PRIORITY 1: Executable Desktop & Web Actions (Deterministic Safety Boundary)
        # Enforces M8.1 ActionSafetyGuard before any execution occurs.
        # =========================================================================

        # 1a. Prohibited command & destructive execution interceptor
        raw_val = self.action_guard.validate_raw_prompt(user_request)
        if raw_val and not raw_val.allowed:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(
                reply=f"Action blocked by safety boundary: {raw_val.reason}, sir.",
                provider="AIGIS Action Guard -> Safety Boundary",
                latency_ms=elapsed_ms,
                metadata={
                    "intent": "desktop_action",
                    "action": True,
                    "actionType": "PROHIBITED_COMMAND",
                    "actionStatus": "BLOCKED",
                    "reason": raw_val.reason,
                    "networkUsed": False
                }
            )

        # 1b. Structured action request validation & unified execution check (M8.2)
        action_req = self.action_guard.parse_from_prompt(user_request, session_id)
        if action_req:
            action_result = self.action_executor.execute(action_req)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            if not action_result.success:
                status = action_result.metadata.get("actionStatus", "FAILED")
                reason = action_result.error or action_result.message
                return self._build_local_response(
                    reply=action_result.message,
                    provider=action_result.metadata.get("provider", "AIGIS Action Guard -> Safety Boundary"),
                    latency_ms=elapsed_ms,
                    metadata={
                        "intent": action_result.metadata.get("intent", "desktop_action"),
                        "action": True,
                        "actionType": action_result.action_type,
                        "actionStatus": status,
                        "reason": reason,
                        "networkUsed": action_result.metadata.get("networkUsed", False)
                    }
                )
            else:
                return self._build_local_response(
                    reply=action_result.message,
                    provider=action_result.metadata.get("provider", "Desktop Control -> Action Execution"),
                    latency_ms=elapsed_ms,
                    metadata={
                        "intent": action_result.metadata.get("intent", "desktop_action"),
                        "handled": True,
                        "action": True,
                        "actionType": action_result.action_type,
                        "actionStatus": "SUCCESS",
                        "networkUsed": action_result.metadata.get("networkUsed", False),
                        **({"url": action_result.url_to_open} if action_result.url_to_open else {})
                    },
                    url_to_open=action_result.url_to_open
                )

        # 1c. Native Desktop Application & System Hardware Actions (Notepad, Calc, Volume, etc.)
        if self.desktop_action_service:
            handled_desktop, desktop_reply, desktop_provider = self.desktop_action_service.process_natural_command(
                session_id, user_request
            )
            if handled_desktop:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                action_type_label = "OPEN_APPLICATION" if "Opening " in desktop_reply else "SYSTEM_CONTROL"
                return self._build_local_response(
                    reply=desktop_reply,
                    provider=desktop_provider or "Desktop Control -> Action Execution",
                    latency_ms=elapsed_ms,
                    metadata={
                        "intent": "desktop_action",
                        "handled": True,
                        "action": True,
                        "actionType": action_type_label,
                        "actionStatus": "SUCCESS",
                        "networkUsed": False
                    }
                )

        # 1d. Web / Browser Navigation Actions (YouTube, GitHub, Google, explicit URLs)
        target_url = None
        explicit_url = extract_url_from_text(user_request)
        if explicit_url:
            target_url = explicit_url
        else:
            target_url = check_open_website_shortcut(user_request)

        if target_url:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            domain_match = re.search(r'https?://(?:www\.)?([^/]+)', target_url)
            site_name = domain_match.group(1).capitalize() if domain_match else "requested webpage"
            if "youtube.com" in target_url:
                site_name = "YouTube"
            elif "github.com" in target_url:
                site_name = "GitHub"
            elif "google.com" in target_url:
                site_name = "Google"

            reply_text = f"Opening {site_name} for you now, sir.\n\n[OPEN_URL: {target_url}]"
            return self._build_local_response(
                reply=reply_text,
                provider="AIGIS Desktop Action -> Web Navigation",
                latency_ms=elapsed_ms,
                metadata={
                    "intent": "web_action",
                    "url": target_url,
                    "action": True,
                    "actionType": "OPEN_URL",
                    "actionStatus": "SUCCESS",
                    "networkUsed": True
                },
                url_to_open=target_url
            )

        # =========================================================================
        # PRIORITY 2: Deterministic Local System Information (OS Clock, Hardware)
        # =========================================================================

        # 2a. System Time & Date Queries (OS-level truth)
        is_time, is_date, is_remote_location = parse_time_date_query(user_request)
        if is_remote_location:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            reply = "Current and live information for remote locations cannot be verified in Local-Only mode without network connectivity, sir."
            return self._build_local_response(reply, "AIGIS Local Engine -> Competition Guard", elapsed_ms, {
                "intent": "live_web",
                "localInference": False,
                "networkUsed": False,
                "verified": False,
                "remoteLocation": True
            })
        elif is_time and is_date:
            reply, intent_tag = build_time_date_response(True, True, now)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(reply, provider_name, elapsed_ms, {"intent": intent_tag, "localClock": True, "isOffline": True, "networkUsed": False})
        elif is_time:
            reply, intent_tag = build_time_date_response(True, False, now)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(reply, provider_name, elapsed_ms, {"intent": intent_tag, "localClock": True, "isOffline": True, "networkUsed": False})
        elif is_date:
            reply, intent_tag = build_time_date_response(False, True, now)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(reply, provider_name, elapsed_ms, {"intent": intent_tag, "localClock": True, "isOffline": True, "networkUsed": False})

        # 2b. Deterministic Hardware Telemetry & Accelerator Inquiries
        if parse_telemetry_query(user_request):
            telemetry_data = self.detector.get_system_telemetry(accelerator_label)
            reply, intent_tag = build_telemetry_response(caps, accelerator_label, user_request, telemetry_data)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(
                reply,
                provider_name,
                elapsed_ms,
                {
                    "intent": intent_tag,
                    "networkUsed": False,
                    "localTelemetry": True,
                    "telemetry": telemetry_data
                }
            )

        # 2c. Privacy & Processing Location Inquiries
        if any(kw in request_lowered for kw in ["where are you running", "is this local", "are you local", "is my data private", "privacy mode"]):
            reply = (
                f"I am executing locally on this physical workstation, sir. "
                f"Your query was processed entirely on-device via {accelerator_label} "
                f"without transmitting any tokens to external cloud servers."
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(reply, provider_name, elapsed_ms, {"intent": "privacy_verification"})

        # 2d. Identity & Assistant Capabilities
        is_identity = any(kw in request_lowered for kw in ["who are you", "what are you", "what is aigis", "introduce yourself"])
        is_capability = any(kw in request_lowered for kw in ["what can you do", "capabilities", "tell me about yourself"])

        if is_identity or is_capability:
            model_tag = self.slm_pipeline.model_name if (self.slm_pipeline and self.slm_pipeline.is_available()) else "On-Device Core"
            if is_capability and not (is_identity and "who are you" in request_lowered and "what can you do" not in request_lowered):
                reply = (
                    f"I am AIGIS — an advanced, privacy-first personal AI assistant engineered for local-first execution, sir.\n\n"
                    f"My currently verified capabilities include:\n"
                    f"• Local On-Device AI: Neural language inference powered by {model_tag} on {caps.get('architecture', 'x86_64')} CPU\n"
                    f"• Deterministic System Information: Local OS clock, date, and hardware telemetry\n"
                    f"• Desktop Actions: Launching local applications (such as Notepad and Calculator) and desktop controls\n"
                    f"• Web Navigation: Direct browser navigation to websites and services (such as YouTube and GitHub)\n"
                    f"• Live Web Search: Real-time internet information retrieval via Tavily and Google News RSS\n"
                    f"• Cloud AI Acceleration: Cloud language synthesis via Groq when configured\n"
                    f"• Local Privacy Guard: On-device processing with zero telemetry or data transmission"
                )
                intent_tag = "assistant_capabilities"
            else:
                reply = (
                    f"I am AIGIS — an advanced, privacy-first personal AI computer assistant "
                    f"engineered for local-first execution. I am currently running on this machine "
                    f"using {accelerator_label}, powered by {model_tag}, sir."
                )
                intent_tag = "assistant_identity"

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(reply, provider_name, elapsed_ms, {"intent": intent_tag})

        # =========================================================================
        # GUARD: Prevent SmolLM2 Hallucination on Live / Time-Sensitive Queries
        # =========================================================================
        # SmolLM2 is a static on-device model and MUST NEVER answer live web queries.
        intent_info = classify_intent_llm(user_request)
        if intent_info.get("intent") == "LIVE_WEB" or is_time_sensitive_query(user_request):
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(
                reply="Current and live information cannot be verified locally on this device, sir. Please enable online web services for real-time data.",
                provider="AIGIS Local Engine -> Anti-Hallucination Guard",
                latency_ms=elapsed_ms,
                metadata={
                    "intent": "live_web",
                    "localInference": False,
                    "verified": False,
                    "liveInfoBlocked": True
                }
            )

        # =========================================================================
        # PRIORITY 3: Genuine Local SLM Neural Generation (General AI)
        # =========================================================================
        if self.slm_pipeline and self.slm_pipeline.is_available():
            active_sys_prompt = kwargs.get("system_prompt") or self.system_prompt
            reply_text, token_count, latency_ms, tokens_per_sec, meta = self.slm_pipeline.generate(
                prompt,
                system_prompt=active_sys_prompt
            )
            slm_provider = f"AIGIS Local Engine -> {self.slm_pipeline.model_name} ({accelerator_label})"
            return self._build_local_response(
                reply=reply_text,
                provider=slm_provider,
                latency_ms=latency_ms,
                metadata={
                    "intent": "general_ai",
                    **meta
                }
            )
        else:
            err = self.slm_pipeline.load_error if self.slm_pipeline else "SLM pipeline not configured"
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            reply = f"Local SLM is unavailable ({err}); no local model inference was performed."
            return self._build_local_response(
                reply=reply,
                provider=provider_name,
                latency_ms=elapsed_ms,
                metadata={
                    "intent": "general_ai",
                    "localInference": False,
                    "error": err
                }
            )

    def _build_local_response(
        self,
        reply: str,
        provider: str,
        latency_ms: int,
        metadata: Dict[str, Any],
        url_to_open: Optional[str] = None
    ) -> EngineResponse:
        enriched_meta = dict(metadata)
        if "networkUsed" not in enriched_meta:
            enriched_meta["networkUsed"] = False
        return EngineResponse(
            reply=reply,
            provider=provider,
            engine="local",
            badge="⚡ AIGIS Local (Processed on this device)",
            latencyMs=max(1, latency_ms),
            urlToOpen=url_to_open,
            metadata=enriched_meta
        )

    def get_engine_info(self) -> Dict[str, Any]:
        caps = self._get_capabilities()
        info = {
            "engine": "local",
            "deviceType": caps.get("deviceType"),
            "architecture": caps.get("architecture"),
            "accelerator": self.get_accelerator_label(),
            "onnxProviders": caps.get("onnxruntime", {}).get("availableProviders", [])
        }
        if self.slm_pipeline:
            info["slmPipeline"] = self.slm_pipeline.get_pipeline_info()
        return info
