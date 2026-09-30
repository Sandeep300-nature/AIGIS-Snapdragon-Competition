import os
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional, Iterator
from pydantic import BaseModel, Field

from .base_engine import BaseAIEngine, EngineResponse
from .qualcomm_runner import (
    QualcommModelRunner,
    SnapdragonRuntimeState,
    SnapdragonCapabilityReport
)
from .deterministic import (
    parse_time_date_query,
    build_time_date_response,
    parse_telemetry_query,
    build_telemetry_response
)

try:
    from ..hardware.detector import HardwareDetector
except ImportError:
    try:
        from hardware.detector import HardwareDetector
    except ImportError:
        from ai_engine.hardware.detector import HardwareDetector

# Compatibility alias for BaseEngine
BaseEngine = BaseAIEngine


class HardwareNotSupportedError(RuntimeError):
    """Raised when Snapdragon NPU inference is requested on unsupported hardware (e.g., non-ARM64 host or missing QNN)."""
    pass


class SnapdragonConfig(BaseModel):
    """Configuration schema for Qualcomm AI Hub models targeting Snapdragon X Elite / X Plus."""
    model_id: str = Field(default="qwen3_4b_instruct_2507", description="Qualcomm AI Hub model identifier")
    checkpoint: str = Field(default="DEFAULT_W4A16", description="Qualcomm AI Hub model checkpoint")
    quantization: str = Field(default="w4a16", description="Quantization precision (4-bit weights, 16-bit activations)")
    runtime: str = Field(default="GenieX-QAIRT", description="Execution Provider runtime")
    execution_provider: str = Field(default="QnnHtp", description="Execution Provider")
    target_soc: str = Field(default="Snapdragon X Elite / X Plus", description="Target hardware system-on-chip")
    target_accelerator: str = Field(default="Qualcomm Hexagon NPU", description="Target neural processing unit")
    context_length: int = Field(default=4096, description="Context window token capacity")
    model_dir: Optional[str] = Field(default=None, description="Local model assets directory")


class SnapdragonNPUEngine(BaseAIEngine):
    """
    On-Device AI Engine targeting Qualcomm Snapdragon X Elite / X Plus Hexagon NPU.
    Delegates runtime-specific orchestration to QualcommModelRunner and GenieQwenProvider.
    
    Truthful capability enforcement:
    - Never fabricates NPU execution.
    - Inspects physical architecture (requires ARM64), loadable Genie/QAIRT runtime, and model assets.
    - Gracefully delegates to portable fallback engine (SmolLM2-135M on CPU) on x86_64 development machines.
    """

    def __init__(
        self,
        config: Optional[SnapdragonConfig] = None,
        hardware_detector: Optional[Any] = None,
        fallback_engine: Optional[BaseAIEngine] = None,
        auto_fallback: bool = True,
        runner: Optional[QualcommModelRunner] = None,
        system_prompt: Optional[str] = None
    ):
        self.config = config or SnapdragonConfig()
        self.detector = hardware_detector or HardwareDetector
        self.fallback_engine = fallback_engine
        self.auto_fallback = auto_fallback
        self.system_prompt = system_prompt
        resolved_model_dir = (
            self.config.model_dir
            or os.getenv("AIGIS_GENIE_MODEL_DIR")
            or os.getenv("AIGIS_SNAPDRAGON_MODEL_DIR")
            or QualcommModelRunner.DEFAULT_MODEL_DIR
        )
        self.runner = runner or QualcommModelRunner(
            model_dir=resolved_model_dir,
            model_id=self.config.model_id,
            checkpoint=self.config.checkpoint,
            hardware_detector=self.detector,
            system_prompt=self.system_prompt
        )
        self._cached_report: Optional[SnapdragonCapabilityReport] = None

    def get_capability_report(self) -> SnapdragonCapabilityReport:
        """Returns the full, multi-state capability diagnosis without collapsing into a boolean."""
        self._cached_report = self.runner.inspect_capabilities()
        return self._cached_report

    def is_available(self) -> bool:
        """
        Dynamically inspects the system detector and runtime.
        Returns True ONLY if state is FULLY_CONFIGURED or INFERENCE_SUCCESSFUL on physical hardware.
        Returns False on the current x86_64 machine with clear reason.
        """
        report = self.get_capability_report()
        return report.is_available

    def get_availability_reason(self) -> str:
        """Returns the explanatory string for the current availability state."""
        report = self.get_capability_report()
        return report.state_description

    def get_engine_info(self) -> Dict[str, Any]:
        """Returns metadata regarding active engine type, runtime, and capabilities."""
        report = self.get_capability_report()
        return {
            "engine": "snapdragon_npu",
            "provider": "Qualcomm Genie / Hexagon NPU",
            "model": f"{self.config.model_id}-{self.config.quantization}",
            "model_id": self.config.model_id,
            "checkpoint": self.config.checkpoint,
            "quantization": self.config.quantization,
            "runtime": self.config.runtime,
            "executionProvider": self.config.execution_provider,
            "target_soc": self.config.target_soc,
            "target": self.config.target_accelerator,
            "targetAccelerator": self.config.target_accelerator,
            "state": report.state.value,
            "available": report.is_available,
            "reason": report.state_description,
            "simulated": False,
            "hardware_valid": report.hardware_valid,
            "fallback_configured": self.fallback_engine is not None,
            "model_artifact_found": report.model_artifact_found
        }

    def generate(
        self,
        prompt: str,
        session_id: str = "default-session",
        response_language: str = "en",
        fallback: Optional[bool] = None,
        **kwargs
    ) -> EngineResponse:
        """Alias conforming to generate() contract."""
        return self.generate_response(
            prompt=prompt,
            session_id=session_id,
            response_language=response_language,
            fallback=fallback,
            **kwargs
        )

    def generate_response(
        self,
        prompt: str,
        session_id: str = "default-session",
        response_language: str = "en",
        fallback: Optional[bool] = None,
        **kwargs
    ) -> EngineResponse:
        """
        Executes inference or cleanly delegates to fallback engine with structured provenance.
        """
        start_time = time.perf_counter()
        allow_fallback = fallback if fallback is not None else self.auto_fallback
        report = self.get_capability_report()

        if not report.is_available:
            if allow_fallback and self.fallback_engine is not None:
                # Delegate cleanly to designated fallback (SmolLM2 on CPU)
                resp = self.fallback_engine.generate_response(
                    prompt=prompt,
                    session_id=session_id,
                    response_language=response_language,
                    **kwargs
                )
                # Attach truthful Snapdragon NPU fallback metadata
                resp.metadata.update({
                    "snapdragon_requested": True,
                    "engine": "snapdragon_npu",
                    "target": self.config.target_accelerator,
                    "targetAccelerator": self.config.target_accelerator,
                    "model": f"{self.config.model_id}-{self.config.quantization}",
                    "checkpoint": self.config.checkpoint,
                    "runtime": self.config.runtime,
                    "executionProvider": self.config.execution_provider,
                    "simulated": False,
                    "hardware_valid": False,
                    "hardwareValid": False,
                    "fallback_triggered": True,
                    "fallback_reason": report.state_description,
                    "fallback_state": report.state.value,
                    "fallback_engine": resp.metadata.get("model") or resp.provider or "SmolLM2-135M-Instruct (CPU)"
                })
                return resp
            else:
                raise HardwareNotSupportedError(
                    f"Snapdragon NPU inference requested, but host is not supported: {report.state_description}"
                )

        # On verified ARM64 + Genie host:
        # OS-level clock truth: bypass NPU LLM runner completely for deterministic time/date queries
        is_time, is_date, is_remote_location = parse_time_date_query(prompt)
        if is_remote_location:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return EngineResponse(
                reply="Current and live information for remote locations cannot be verified in Competition Local-Only mode without network connectivity, sir.",
                provider="AIGIS Snapdragon Engine -> Competition Guard",
                engine="local",
                badge="⚡ AIGIS Local (Competition Guard)",
                latencyMs=elapsed_ms,
                metadata={
                    "intent": "live_web",
                    "engine": "snapdragon_npu",
                    "localInference": False,
                    "networkUsed": False,
                    "verified": False,
                    "remoteLocation": True,
                    "hardware_valid": report.is_available
                }
            )
        elif is_time or is_date:
            reply, intent_tag = build_time_date_response(is_time, is_date, datetime.now())
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return EngineResponse(
                reply=reply,
                provider="AIGIS Snapdragon Engine -> Local OS Clock",
                engine="local",
                badge="⚡ AIGIS Local (Deterministic Clock)",
                latencyMs=elapsed_ms,
                metadata={
                    "intent": intent_tag,
                    "engine": "local_clock",
                    "localInference": True,
                    "networkUsed": False,
                    "localClock": True,
                    "hardware_valid": report.is_available,
                    "hardwareValid": report.is_available
                }
            )

        # OS-level hardware telemetry truth: bypass NPU LLM runner completely for deterministic telemetry queries
        if parse_telemetry_query(prompt):
            caps = self.detector.get_capabilities() if hasattr(self.detector, "get_capabilities") else {}
            accelerator_label = "Qualcomm GenieX-QAIRT (Hexagon NPU)"
            telemetry_data = self.detector.get_system_telemetry(accelerator_label)
            reply, intent_tag = build_telemetry_response(caps, accelerator_label, prompt, telemetry_data)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return EngineResponse(
                reply=reply,
                provider="AIGIS Snapdragon Engine -> Local Hardware Telemetry",
                engine="local",
                badge="⚡ AIGIS Snapdragon NPU (Hardware Telemetry)",
                latencyMs=elapsed_ms,
                metadata={
                    "intent": intent_tag,
                    "engine": "snapdragon_telemetry",
                    "localInference": True,
                    "networkUsed": False,
                    "localTelemetry": True,
                    "hardware_valid": report.is_available,
                    "hardwareValid": report.is_available,
                    "telemetry": telemetry_data
                }
            )

        # On verified ARM64 + Genie host with model artifact:
        system_prompt = kwargs.pop("system_prompt", None) or self.system_prompt
        reply, tok_count, lat_ms, meta = self.runner.run_inference(
            prompt,
            system_prompt=system_prompt,
            **kwargs
        )
        elapsed_ms = lat_ms or int((time.perf_counter() - start_time) * 1000)

        if reply is None:
            # Inference failed on hardware; handle fallback or error
            err_msg = meta.get("error", "Unknown Snapdragon execution failure")
            if allow_fallback and self.fallback_engine is not None:
                resp = self.fallback_engine.generate_response(prompt=prompt, session_id=session_id, **kwargs)
                resp.metadata["fallback_triggered"] = True
                resp.metadata["fallback_reason"] = err_msg
                return resp
            raise HardwareNotSupportedError(f"Snapdragon inference failed: {err_msg}")

        resp_metadata = {
            "engine": "snapdragon_npu",
            "provider": "Qualcomm Genie / Hexagon NPU",
            "target": self.config.target_accelerator,
            "targetAccelerator": self.config.target_accelerator,
            "model": self.config.model_id,
            "checkpoint": self.config.checkpoint,
            "quantization": self.config.quantization,
            "runtime": self.config.runtime,
            "executionProvider": self.config.execution_provider,
            "simulated": False,
            "hardware_valid": True,
            "hardwareValid": True,
            "localInference": True,
            "networkUsed": False,
            "tokensGenerated": tok_count
        }
        resp_metadata.update(meta)

        return EngineResponse(
            reply=reply,
            provider="Qualcomm Genie / Hexagon NPU",
            engine="local",
            badge="⚡ AIGIS Snapdragon NPU (Hexagon NPU Accelerated via GenieX)",
            latencyMs=max(1, elapsed_ms),
            metadata=resp_metadata
        )

    def generate_stream(
        self,
        prompt: str,
        session_id: str = "default-session",
        fallback: Optional[bool] = None,
        **kwargs
    ) -> Iterator[str]:
        """
        Streaming token generation interface.
        Yields tokens if supported, or raises HardwareNotSupportedError when on an unsupported host without fallback.
        """
        allow_fallback = fallback if fallback is not None else self.auto_fallback
        report = self.get_capability_report()

        if not report.is_available:
            if allow_fallback and self.fallback_engine is not None:
                resp = self.fallback_engine.generate_response(prompt=prompt, session_id=session_id, **kwargs)
                yield resp.reply
                return
            else:
                raise HardwareNotSupportedError(
                    f"Snapdragon NPU stream requested, but host is not supported: {report.state_description}"
                )

        # On physical hardware:
        reply, _, _, _ = self.runner.run_inference(prompt, **kwargs)
        if reply:
            yield reply
