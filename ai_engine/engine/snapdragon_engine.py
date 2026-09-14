import os
import sys
import time
from typing import Dict, Any, Optional, Iterator
from pydantic import BaseModel, Field

from .base_engine import BaseAIEngine, EngineResponse
from .qualcomm_runner import (
    QualcommModelRunner,
    SnapdragonRuntimeState,
    SnapdragonCapabilityReport
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
    model_id: str = Field(default="Llama-3.2-1B-Instruct", description="Qualcomm AI Hub model identifier")
    checkpoint: str = Field(default="DEFAULT_W4A16", description="Qualcomm AI Hub model checkpoint")
    quantization: str = Field(default="w4a16", description="Quantization precision (4-bit weights, 16-bit activations)")
    runtime: str = Field(default="QNNExecutionProvider", description="Execution Provider runtime")
    execution_provider: str = Field(default="QNNExecutionProvider", description="Execution Provider")
    target_soc: str = Field(default="Snapdragon X Elite / X Plus", description="Target hardware system-on-chip")
    target_accelerator: str = Field(default="Qualcomm Hexagon NPU", description="Target neural processing unit")
    context_length: int = Field(default=4096, description="Context window token capacity")
    model_dir: Optional[str] = Field(default=None, description="Local model assets directory")


class SnapdragonNPUEngine(BaseAIEngine):
    """
    On-Device AI Engine targeting Qualcomm Snapdragon X Elite / X Plus Hexagon NPU.
    Delegates runtime-specific orchestration to QualcommModelRunner.
    
    Truthful capability enforcement:
    - Never fabricates NPU execution.
    - Inspects physical architecture (requires ARM64), loadable QNN runtime, and model assets.
    - Gracefully delegates to portable fallback engine (SmolLM2-135M on CPU) on x86_64 development machines.
    """

    def __init__(
        self,
        config: Optional[SnapdragonConfig] = None,
        hardware_detector: Optional[Any] = None,
        fallback_engine: Optional[BaseAIEngine] = None,
        auto_fallback: bool = True,
        runner: Optional[QualcommModelRunner] = None
    ):
        self.config = config or SnapdragonConfig()
        self.detector = hardware_detector or HardwareDetector
        self.fallback_engine = fallback_engine
        self.auto_fallback = auto_fallback
        self.runner = runner or QualcommModelRunner(
            model_dir=self.config.model_dir,
            model_id=self.config.model_id,
            checkpoint=self.config.checkpoint,
            hardware_detector=self.detector
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
            "provider": "Qualcomm QNN / Hexagon NPU",
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
                    "fallback_engine": resp.metadata.get("runtime", "SmolLM2-135M-Instruct (CPU)")
                })
                return resp
            else:
                raise HardwareNotSupportedError(
                    f"Snapdragon NPU inference requested, but host is not supported: {report.state_description}"
                )

        # On verified ARM64 + QNN host with model artifact:
        reply, tok_count, lat_ms, meta = self.runner.run_inference(prompt, **kwargs)
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

        return EngineResponse(
            reply=reply,
            provider="Qualcomm QNN / Hexagon NPU",
            engine="local",
            badge="⚡ AIGIS Snapdragon NPU (Hexagon Accelerated)",
            latencyMs=max(1, elapsed_ms),
            metadata={
                "engine": "snapdragon_npu",
                "provider": "Qualcomm QNN / Hexagon NPU",
                "target": self.config.target_accelerator,
                "targetAccelerator": self.config.target_accelerator,
                "model": self.config.model_id,
                "checkpoint": self.config.checkpoint,
                "quantization": self.config.quantization,
                "runtime": "ONNX Runtime GenAI",
                "executionProvider": "QNNExecutionProvider",
                "simulated": False,
                "hardware_valid": True,
                "hardwareValid": True,
                "localInference": True,
                "networkUsed": False,
                "tokensGenerated": tok_count
            }
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
