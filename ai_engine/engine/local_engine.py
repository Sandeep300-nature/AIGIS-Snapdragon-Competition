import sys
import os
import re
import time
from datetime import datetime
from typing import Dict, Any, Optional
from .base_engine import BaseAIEngine, EngineResponse
from .slm_pipeline import LocalSLMPipeline

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
except ImportError:
    from ai_engine.desktop_control import DesktopActionService
    from ai_engine.web_search import (
        check_open_website_shortcut,
        extract_url_from_text,
        classify_intent_llm,
        is_time_sensitive_query
    )


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
        desktop_action_service: Optional[DesktopActionService] = None
    ):
        self.detector = hardware_detector or HardwareDetector
        self.slm_pipeline = slm_pipeline if slm_pipeline is not None else LocalSLMPipeline()
        self.desktop_action_service = desktop_action_service or DesktopActionService()
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
        lowered = prompt.strip().lower()
        now = datetime.now()

        caps = self._get_capabilities()
        accelerator_label = self.get_accelerator_label()
        provider_name = f"AIGIS Local Engine -> {accelerator_label}"

        # =========================================================================
        # PRIORITY 1: Executable Desktop & Web Actions (Deterministic Execution)
        # =========================================================================

        # 1a. Native Desktop Application & System Hardware Actions (Notepad, Calc, Volume, etc.)
        if self.desktop_action_service:
            handled_desktop, desktop_reply, desktop_provider = self.desktop_action_service.process_natural_command(
                session_id, prompt
            )
            if handled_desktop:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                return self._build_local_response(
                    reply=desktop_reply,
                    provider=desktop_provider or "Desktop Control -> Action Execution",
                    latency_ms=elapsed_ms,
                    metadata={"intent": "desktop_action", "handled": True}
                )

        # 1b. Web / Browser Navigation Actions (YouTube, GitHub, Google, explicit URLs)
        target_url = None
        explicit_url = extract_url_from_text(prompt)
        if explicit_url:
            target_url = explicit_url
        else:
            target_url = check_open_website_shortcut(prompt)

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
                metadata={"intent": "web_action", "url": target_url},
                url_to_open=target_url
            )

        # =========================================================================
        # PRIORITY 2: Deterministic Local System Information (OS Clock, Hardware)
        # =========================================================================

        # 2a. System Time & Date Queries (OS-level truth)
        is_time = any(p in lowered for p in ["what time is it", "current time", "what's the time", "tell me the time"]) or lowered in ["time", "time now"]
        is_date = any(p in lowered for p in ["what's today's date", "what is today's date", "today's date", "what day is it", "what day is today"]) or lowered in ["date", "today date"]

        if is_time and is_date:
            reply = f"It is {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d, %Y')}, sir."
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(reply, provider_name, elapsed_ms, {"intent": "time_date"})
        elif is_time:
            reply = f"The current time is {now.strftime('%I:%M %p')}, sir."
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(reply, provider_name, elapsed_ms, {"intent": "time"})
        elif is_date:
            reply = f"Today is {now.strftime('%A, %B %d, %Y')}, sir."
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(reply, provider_name, elapsed_ms, {"intent": "date"})

        # 2b. Hardware / Accelerator Inquiries
        hw_keywords = ["hardware", "specs", "accelerator", "npu", "cpu", "gpu", "snapdragon", "system specs", "device info"]
        if any(kw in lowered for kw in hw_keywords) and any(w in lowered for w in ["what", "check", "show", "tell", "status", "info"]):
            arch = caps.get("architecture", "Unknown")
            cpu_brand = caps.get("cpu", {}).get("brand", "Unknown CPU")
            gpu_name = caps.get("gpu", {}).get("name", "Unknown GPU")
            npu_status = caps.get("accelerators", {}).get("snapdragonNpu", {}).get("status", "Not detected")
            device_type = caps.get("deviceType", "Host")

            reply = (
                f"Workstation Hardware Telemetry, sir:\n"
                f"• Device Environment: {device_type}\n"
                f"• Architecture: {arch}\n"
                f"• Processor: {cpu_brand} ({caps.get('cpu', {}).get('logicalCores', 0)} threads)\n"
                f"• Physical GPU: {gpu_name}\n"
                f"• Snapdragon NPU Status: {npu_status}\n"
                f"• Active AI Execution Runtime: {accelerator_label}"
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(reply, provider_name, elapsed_ms, {"intent": "hardware_telemetry"})

        # 2c. Privacy & Processing Location Inquiries
        if any(kw in lowered for kw in ["where are you running", "is this local", "are you local", "is my data private", "privacy mode"]):
            reply = (
                f"I am executing locally on this physical workstation, sir. "
                f"Your query was processed entirely on-device via {accelerator_label} "
                f"without transmitting any tokens to external cloud servers."
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_local_response(reply, provider_name, elapsed_ms, {"intent": "privacy_verification"})

        # 2d. Identity & Assistant Capabilities
        is_identity = any(kw in lowered for kw in ["who are you", "what are you", "what is aigis", "introduce yourself"])
        is_capability = any(kw in lowered for kw in ["what can you do", "capabilities", "tell me about yourself"])

        if is_identity or is_capability:
            model_tag = self.slm_pipeline.model_name if (self.slm_pipeline and self.slm_pipeline.is_available()) else "On-Device Core"
            if is_capability and not (is_identity and "who are you" in lowered and "what can you do" not in lowered):
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
        intent_info = classify_intent_llm(prompt)
        if intent_info.get("intent") == "LIVE_WEB" or is_time_sensitive_query(prompt):
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
            reply_text, token_count, latency_ms, tokens_per_sec, meta = self.slm_pipeline.generate(prompt)
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
