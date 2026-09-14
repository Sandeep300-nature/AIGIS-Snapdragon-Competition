import os
import sys
import shutil
import time
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field

ai_engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)

try:
    from hardware.detector import HardwareDetector
except ImportError:
    from ai_engine.hardware.detector import HardwareDetector


class SnapdragonRuntimeState(str, Enum):
    """
    Strict 6-state distinction for Qualcomm Snapdragon AI runtime readiness.
    These states MUST NOT collapse into a single boolean.
    """
    HARDWARE_UNAVAILABLE = "hardware_unavailable"              # 1. Non-ARM64 / non-Snapdragon CPU
    QNN_UNAVAILABLE = "qnn_unavailable"                        # 2. ARM64 host, but QNN Execution Provider not registered
    RUNTIME_INCOMPLETE = "runtime_incomplete"                  # 3. QNN EP available, but Qualcomm SDK runtime DLLs missing
    MODEL_ARTIFACT_UNAVAILABLE = "model_artifact_unavailable"  # 4. Hardware + Runtime present, but model weights missing locally
    FULLY_CONFIGURED = "fully_configured"                      # 5. Hardware + QNN + Runtime DLLs + Model Artifact verified
    INFERENCE_SUCCESSFUL = "inference_successful"              # 6. Actual physical Hexagon NPU execution succeeded


class SnapdragonCapabilityReport(BaseModel):
    """Structured telemetry report detailing Snapdragon NPU execution environment."""
    state: SnapdragonRuntimeState
    state_description: str
    is_available: bool = Field(..., description="True ONLY if state is fully_configured or inference_successful")
    architecture: str
    is_arm64: bool
    is_snapdragon_cpu: bool
    qnn_provider_available: bool
    qairt_runtime_available: bool
    genie_runtime_available: bool
    runtime_dlls_found: List[str] = Field(default_factory=list)
    missing_dlls: List[str] = Field(default_factory=list)
    model_artifact_found: bool
    model_dir: str
    model_id: str = "Llama-v3.2-1B-Instruct"
    checkpoint: str = "DEFAULT_W4A16"
    quantization: str = "w4a16"
    target_soc: str = "Snapdragon X Elite / X Plus"
    target_accelerator: str = "Qualcomm Hexagon NPU"
    runtime_engine: str = "ONNX Runtime GenAI"
    execution_provider: str = "QNNExecutionProvider"
    hardware_valid: bool = False
    simulated: bool = False


class QualcommModelRunner:
    """
    Dedicated runtime adapter for Qualcomm AI Hub models targeting Snapdragon Hexagon NPU.
    Owns runtime-specific loading, artifact verification, and execution provider orchestration.
    
    Zero fabrication:
    - Never mocks NPU execution on x86_64.
    - Accurately reports which prerequisites are met and which are missing.
    """

    REQUIRED_RUNTIME_DLLS = ["QnnHtp.dll", "QnnSystem.dll"]
    OPTIONAL_RUNTIME_DLLS = ["QnnCpu.dll", "QnnHtpV73Stub.dll", "QnnHtpPrepare.dll"]
    EXPECTED_MODEL_FILES = ["genai_config.json", "model.onnx", "model.onnx.data"]

    DEFAULT_MODEL_DIR = os.path.join(
        ai_engine_dir,
        "models",
        "Llama-v3.2-1B-Instruct-w4a16"
    )

    def __init__(
        self,
        model_dir: Optional[str] = None,
        model_id: str = "Llama-v3.2-1B-Instruct",
        checkpoint: str = "DEFAULT_W4A16",
        hardware_detector: Optional[Any] = None
    ):
        self.model_dir = model_dir or os.getenv("AIGIS_SNAPDRAGON_MODEL_DIR", self.DEFAULT_MODEL_DIR)
        self.model_id = model_id
        self.checkpoint = checkpoint
        self.detector = hardware_detector or HardwareDetector
        self._session = None
        self._tokenizer = None
        self._is_loaded = False
        self._last_state = SnapdragonRuntimeState.HARDWARE_UNAVAILABLE

    def inspect_model_artifact(self) -> Tuple[bool, List[str]]:
        """
        Discovers whether the Qualcomm AI Hub model artifact exists locally.
        Returns: (artifact_present, missing_files)
        """
        if not os.path.isdir(self.model_dir):
            return False, ["directory_not_found"]

        existing_files = set(os.listdir(self.model_dir))
        # Valid if genai_config.json exists along with at least one model binary or onnx graph
        has_config = "genai_config.json" in existing_files or "config.json" in existing_files
        has_weights = any(
            f.endswith((".onnx", ".bin", ".data", ".raw")) for f in existing_files
        )
        if has_config and has_weights:
            return True, []

        missing = [f for f in self.EXPECTED_MODEL_FILES if f not in existing_files]
        return False, missing

    def inspect_capabilities(self) -> SnapdragonCapabilityReport:
        """
        Performs comprehensive capability inspection distinguishing the 6 runtime states.
        """
        caps = self.detector.get_capabilities() if hasattr(self.detector, "get_capabilities") else {}
        arch = str(caps.get("architecture", "")).lower()
        cpu_info = caps.get("cpu", {})
        is_snapdragon_cpu = bool(cpu_info.get("isSnapdragon", False))
        is_arm64 = (arch in ["arm64", "aarch64"]) or is_snapdragon_cpu

        accelerators = caps.get("accelerators", {})
        qnn_status = accelerators.get("qnn", {})
        ort_info = caps.get("onnxruntime", {})

        available_providers = ort_info.get("availableProviders", [])
        qnn_ep_available = "QNNExecutionProvider" in available_providers or qnn_status.get("providerAvailable", False)

        # Check for Qualcomm AI Engine Direct (QAIRT) runtime DLLs
        qnn_sdk_root = os.environ.get("QNN_SDK_ROOT") or os.environ.get("QUALCOMM_SDK_ROOT")
        found_dlls = []
        missing_dlls = []
        for dll in self.REQUIRED_RUNTIME_DLLS:
            if shutil.which(dll) is not None:
                found_dlls.append(dll)
            elif qnn_sdk_root and os.path.isfile(os.path.join(qnn_sdk_root, "lib", "arm64", dll)):
                found_dlls.append(dll)
            else:
                missing_dlls.append(dll)

        qairt_runtime_available = len(found_dlls) >= len(self.REQUIRED_RUNTIME_DLLS)
        genie_runtime_available = bool(shutil.which("genie.dll") or shutil.which("genie-runtime"))

        # Inspect local model artifact presence
        artifact_present, _ = self.inspect_model_artifact()

        # State Determination (Strict 6-state distinction)
        if not is_arm64:
            state = SnapdragonRuntimeState.HARDWARE_UNAVAILABLE
            state_desc = f"Host architecture '{arch}' is non-ARM64; Qualcomm Hexagon NPU is physically absent."
        elif not qnn_ep_available:
            state = SnapdragonRuntimeState.QNN_UNAVAILABLE
            state_desc = "ARM64 host detected, but ONNX Runtime QNN Execution Provider (QNNExecutionProvider) is not registered."
        elif not qairt_runtime_available:
            state = SnapdragonRuntimeState.RUNTIME_INCOMPLETE
            state_desc = f"QNN Execution Provider available, but required Qualcomm runtime libraries missing: {', '.join(missing_dlls)}."
        elif not artifact_present:
            state = SnapdragonRuntimeState.MODEL_ARTIFACT_UNAVAILABLE
            state_desc = f"Snapdragon NPU and QNN runtime ready, but Qualcomm model artifact not found at '{self.model_dir}'."
        else:
            state = SnapdragonRuntimeState.FULLY_CONFIGURED
            state_desc = "Qualcomm Snapdragon NPU, QNN Execution Provider, runtime DLLs, and model artifact are verified and ready."

        self._last_state = state
        is_avail = (state in [SnapdragonRuntimeState.FULLY_CONFIGURED, SnapdragonRuntimeState.INFERENCE_SUCCESSFUL])

        return SnapdragonCapabilityReport(
            state=state,
            state_description=state_desc,
            is_available=is_avail,
            architecture=arch,
            is_arm64=is_arm64,
            is_snapdragon_cpu=is_snapdragon_cpu,
            qnn_provider_available=qnn_ep_available,
            qairt_runtime_available=qairt_runtime_available,
            genie_runtime_available=genie_runtime_available,
            runtime_dlls_found=found_dlls,
            missing_dlls=missing_dlls,
            model_artifact_found=artifact_present,
            model_dir=self.model_dir,
            model_id=self.model_id,
            checkpoint=self.checkpoint,
            hardware_valid=is_avail,
            simulated=False
        )

    def is_available(self) -> bool:
        """Convenience method returning True ONLY when fully configured on physical hardware."""
        report = self.inspect_capabilities()
        return report.is_available

    def run_inference(
        self,
        prompt: str,
        max_new_tokens: int = 256,
        system_prompt: Optional[str] = None
    ) -> Tuple[Optional[str], int, int, Dict[str, Any]]:
        """
        Executes genuine on-device inference via ONNX Runtime GenAI + QNN Execution Provider.
        Returns: (reply_text, token_count, latency_ms, telemetry_metadata)
        
        Zero fabrication: If executed on an unsupported host, returns None with diagnostic telemetry.
        """
        report = self.inspect_capabilities()
        if not report.is_available:
            return None, 0, 0, {
                "error": report.state_description,
                "state": report.state.value,
                "hardware_valid": False,
                "simulated": False
            }

        # Physical execution path on ARM64 Snapdragon hardware
        t0 = time.perf_counter()
        try:
            # Isolated import of onnxruntime_genai
            import onnxruntime_genai as og
            if self._session is None:
                model_params = og.ModelParams(self.model_dir)
                self._session = og.Model(model_params)
                self._tokenizer = og.Tokenizer(self._session)

            sys_prompt = system_prompt or "You are AIGIS, a personal AI computer assistant powered by Qualcomm Snapdragon."
            formatted = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{sys_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"

            tokens = self._tokenizer.encode(formatted)
            params = og.GeneratorParams(self._session)
            params.set_search_options(max_length=len(tokens) + max_new_tokens)
            params.set_input_sequences(tokens)

            generator = og.Generator(self._session, params)
            new_tokens = []
            while not generator.is_done():
                generator.compute_logits()
                generator.generate_next_token()
                tok = generator.get_next_tokens()[0]
                new_tokens.append(tok)

            reply_text = self._tokenizer.decode(new_tokens).strip()
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            self._last_state = SnapdragonRuntimeState.INFERENCE_SUCCESSFUL

            return reply_text, len(new_tokens), elapsed_ms, {
                "state": SnapdragonRuntimeState.INFERENCE_SUCCESSFUL.value,
                "hardware_valid": True,
                "simulated": False,
                "target": "Qualcomm Hexagon NPU",
                "executionProvider": "QNNExecutionProvider"
            }
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return None, 0, elapsed_ms, {
                "error": f"Physical Snapdragon inference error: {str(e)}",
                "state": report.state.value,
                "hardware_valid": False,
                "simulated": False
            }
