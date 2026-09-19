import os
import sys
import time
import shutil
import subprocess
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple, Union
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
    RUNTIME_INCOMPLETE = "runtime_incomplete"                  # 3. QNN available, but Qualcomm Genie SDK / runtime DLLs missing
    MODEL_ARTIFACT_UNAVAILABLE = "model_artifact_unavailable"  # 4. Hardware + Runtime present, but model weights missing locally
    FULLY_CONFIGURED = "fully_configured"                      # 5. Hardware + QNN + Genie Runtime + Model Artifact verified
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
    model_id: str = "qwen3_4b_instruct_2507"
    checkpoint: str = "DEFAULT_W4A16"
    quantization: str = "w4a16"
    target_soc: str = "Snapdragon X Elite / X Plus"
    target_accelerator: str = "Qualcomm Hexagon NPU"
    runtime_engine: str = "GenieX-QAIRT"
    execution_provider: str = "QnnHtp"
    hardware_valid: bool = False
    simulated: bool = False


class GenieRuntimeAdapter:
    """
    Modular execution boundary for the Qualcomm Genie Dialog runtime.
    
    Zero fabrication:
    - Does NOT fabricate or simulate Genie runtime responses.
    - Does NOT assume or import an unverified Python 'genie' package.
    - Discovers verified CLI or native runtime entry points (e.g. genie-t2t-run.exe).
    - Only executes if a verified binary is present on the physical target.
    """

    SUPPORTED_EXECUTABLES = [
        "genie-t2t-run.exe",
        "genie-t2t-run",
        "geniex-bench.exe",
        "geniex-bench"
    ]

    SUPPORTED_LIBRARIES = [
        "genie.dll",
        "QnnHtp.dll",
        "QnnSystem.dll"
    ]

    def __init__(self, custom_runtime_dir: Optional[str] = None):
        self.custom_runtime_dir = custom_runtime_dir or os.getenv("GENIE_ROOT") or os.getenv("GENIEX_PATH")
        self._executable_path: Optional[str] = None
        self._library_paths: Dict[str, str] = {}
        self.refresh()

    def refresh(self) -> None:
        """Discovers runtime executables and libraries on the system."""
        self._executable_path = None
        self._library_paths.clear()

        # Check explicit runtime directory first
        search_dirs = []
        if self.custom_runtime_dir and os.path.isdir(self.custom_runtime_dir):
            search_dirs.append(self.custom_runtime_dir)
            search_dirs.append(os.path.join(self.custom_runtime_dir, "bin"))
            search_dirs.append(os.path.join(self.custom_runtime_dir, "lib"))

        # Find executable
        for exe in self.SUPPORTED_EXECUTABLES:
            for s_dir in search_dirs:
                candidate = os.path.join(s_dir, exe)
                if os.path.isfile(candidate):
                    self._executable_path = candidate
                    break
            if self._executable_path:
                break
            found = shutil.which(exe)
            if found:
                self._executable_path = found
                break

        # Find libraries
        for lib in self.SUPPORTED_LIBRARIES:
            for s_dir in search_dirs:
                candidate = os.path.join(s_dir, lib)
                if os.path.isfile(candidate):
                    self._library_paths[lib] = candidate
                    break
            if lib not in self._library_paths:
                found = shutil.which(lib)
                if found:
                    self._library_paths[lib] = found

    @property
    def is_runtime_present(self) -> bool:
        """Returns True ONLY if a real Genie runtime binary is found."""
        return self._executable_path is not None or "genie.dll" in self._library_paths

    @property
    def executable_path(self) -> Optional[str]:
        return self._executable_path

    @property
    def libraries_found(self) -> List[str]:
        return list(self._library_paths.keys())

    def execute_dialog(
        self,
        config_path: str,
        formatted_prompt: str,
        max_tokens: int = 512,
        timeout_s: float = 60.0
    ) -> Tuple[Optional[str], int, int, Dict[str, Any]]:
        """
        Executes genuine Genie text generation via verified on-device CLI/binary.
        Returns: (reply_text, token_count, latency_ms, telemetry_metadata)
        
        Zero fabrication: If runtime is not present, returns None. Never produces fake output.
        """
        if not self.is_runtime_present or not self._executable_path:
            return None, 0, 0, {
                "error": "Qualcomm Genie runtime executable is not installed on this host.",
                "hardware_valid": False,
                "simulated": False
            }

        t0 = time.perf_counter()
        try:
            cmd = [
                self._executable_path,
                "--config", config_path,
                "--prompt", formatted_prompt,
                "--max-output-tokens", str(max_tokens)
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False
            )
            elapsed_ms = int((time.perf_counter() - t0) * 1000)

            if proc.returncode != 0:
                return None, 0, elapsed_ms, {
                    "error": f"Genie process exited with return code {proc.returncode}: {proc.stderr.strip()}",
                    "hardware_valid": True,
                    "simulated": False
                }

            stdout_text = proc.stdout.strip()
            # Approximation of token count based on output length if exact metric is absent
            token_count = max(1, len(stdout_text.split()))

            return stdout_text, token_count, elapsed_ms, {
                "hardware_valid": True,
                "simulated": False,
                "target": "Qualcomm Hexagon NPU",
                "runtime": "GenieX-QAIRT",
                "backend": "QnnHtp"
            }
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return None, 0, elapsed_ms, {
                "error": f"Genie execution failure: {str(e)}",
                "hardware_valid": False,
                "simulated": False
            }


class GenieQwenProvider:
    """
    Dedicated AI provider for Qwen3-4B-Instruct-2507 W4A16 running on
    Qualcomm Snapdragon X Elite NPU via GenieX QAIRT.
    
    Responsibilities:
    - Discovers and validates the verified 4-shard QAIRT context binary bundle.
    - Discovers Genie runtime availability via GenieRuntimeAdapter.
    - Detects ARM64 / Snapdragon capability with zero fabrication on x86_64.
    - Formats multi-turn and single-turn messages into proper Qwen3 ChatML syntax.
    - Exposes a clean generate() interface conforming to AIGIS expectations.
    - Never fabricates NPU inference on unsupported development hosts.
    """

    DEFAULT_MODEL_DIR = r"D:\AIGIS-Snapdragon-Models\qwen3_4b_instruct_2507-geniex_qairt-w4a16-qualcomm_snapdragon_x_elite"
    DEFAULT_SYSTEM_PROMPT = "You are AIGIS, an autonomous on-device personal AI assistant powered by Qualcomm Snapdragon."

    EXPECTED_BUNDLE_FILES = [
        "genie_config.json",
        "part1_of_4.bin",
        "part2_of_4.bin",
        "part3_of_4.bin",
        "part4_of_4.bin"
    ]

    REQUIRED_RUNTIME_DLLS = [
        "QnnHtp.dll",
        "QnnSystem.dll"
    ]

    def __init__(
        self,
        model_dir: Optional[str] = None,
        hardware_detector: Optional[Any] = None,
        runtime_adapter: Optional[GenieRuntimeAdapter] = None
    ):
        # Configurable model directory via environment variables with fallback
        self.model_dir = (
            model_dir
            or os.getenv("AIGIS_GENIE_MODEL_DIR")
            or os.getenv("AIGIS_SNAPDRAGON_MODEL_DIR")
            or self.DEFAULT_MODEL_DIR
        )
        self.model_id = "qwen3_4b_instruct_2507"
        self.checkpoint = "DEFAULT_W4A16"
        self.detector = hardware_detector or HardwareDetector
        self.runtime_adapter = runtime_adapter or GenieRuntimeAdapter()
        self._last_state = SnapdragonRuntimeState.HARDWARE_UNAVAILABLE

    def inspect_model_bundle(self) -> Tuple[bool, List[str]]:
        """
        Verifies presence of the verified Qwen3-4B GenieX bundle files.
        Returns: (bundle_present, missing_files)
        """
        if not os.path.isdir(self.model_dir):
            return False, ["directory_not_found"]

        existing_files = set(os.listdir(self.model_dir))
        missing = [f for f in self.EXPECTED_BUNDLE_FILES if f not in existing_files]
        bundle_present = (len(missing) == 0)
        return bundle_present, missing

    def inspect_capabilities(self) -> SnapdragonCapabilityReport:
        """
        Performs comprehensive capability inspection distinguishing the 6 runtime states.
        Strict zero fabrication: x86_64 host will ALWAYS report HARDWARE_UNAVAILABLE.
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

        # Inspect Qualcomm runtime DLLs
        qnn_sdk_root = os.environ.get("QNN_SDK_ROOT") or os.environ.get("QUALCOMM_SDK_ROOT") or os.environ.get("QAIRT_SDK_ROOT")
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
        genie_runtime_available = self.runtime_adapter.is_runtime_present

        # Inspect local model bundle
        bundle_present, missing_bundle_files = self.inspect_model_bundle()

        # State Determination (Strict 6-state distinction)
        if not is_arm64:
            state = SnapdragonRuntimeState.HARDWARE_UNAVAILABLE
            state_desc = f"Host architecture '{arch}' is non-ARM64; Qualcomm Hexagon NPU is physically absent."
        elif not qnn_ep_available and not qairt_runtime_available:
            state = SnapdragonRuntimeState.QNN_UNAVAILABLE
            state_desc = "ARM64 host detected, but Qualcomm QNN / QAIRT runtime is not available."
        elif not genie_runtime_available:
            state = SnapdragonRuntimeState.RUNTIME_INCOMPLETE
            state_desc = f"Snapdragon hardware detected, but Qualcomm Genie runtime is missing: {', '.join(missing_dlls) if missing_dlls else 'genie-t2t-run not in PATH'}."
        elif not bundle_present:
            state = SnapdragonRuntimeState.MODEL_ARTIFACT_UNAVAILABLE
            state_desc = f"Snapdragon NPU and Genie runtime ready, but Qwen3 bundle missing files at '{self.model_dir}': {', '.join(missing_bundle_files)}."
        else:
            state = SnapdragonRuntimeState.FULLY_CONFIGURED
            state_desc = "Qualcomm Snapdragon NPU, Genie runtime, QAIRT context binaries, and model bundle are verified and ready."

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
            model_artifact_found=bundle_present,
            model_dir=self.model_dir,
            model_id=self.model_id,
            checkpoint=self.checkpoint,
            quantization="w4a16",
            target_soc="Snapdragon X Elite / X Plus",
            target_accelerator="Qualcomm Hexagon NPU",
            runtime_engine="GenieX-QAIRT",
            execution_provider="QnnHtp",
            hardware_valid=is_avail,
            simulated=False
        )

    def is_available(self) -> bool:
        """Returns True ONLY when physical ARM64 hardware, Genie runtime, and bundle are all verified."""
        report = self.inspect_capabilities()
        return report.is_available

    def format_chatml_prompt(
        self,
        messages_or_prompt: Union[str, List[Dict[str, str]]],
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Formats user input into Qwen3 ChatML tokenization format:
        <|im_start|>system
        {system_prompt}<|im_end|>
        <|im_start|>user
        {user_message}<|im_end|>
        <|im_start|>assistant
        """
        sys_p = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        formatted = f"<|im_start|>system\n{sys_p}<|im_end|>\n"

        if isinstance(messages_or_prompt, str):
            formatted += f"<|im_start|>user\n{messages_or_prompt.strip()}<|im_end|>\n<|im_start|>assistant\n"
        elif isinstance(messages_or_prompt, list):
            for msg in messages_or_prompt:
                role = msg.get("role", "user")
                content = msg.get("content", "").strip()
                if role == "system":
                    # Override system prompt if explicitly provided in messages
                    formatted = f"<|im_start|>system\n{content}<|im_end|>\n"
                elif role in ["user", "assistant"]:
                    formatted += f"<|im_start|>{role}\n{content}<|im_end|>\n"
            formatted += "<|im_start|>assistant\n"

        return formatted

    def generate(
        self,
        messages_or_prompt: Union[str, List[Dict[str, str]]],
        max_tokens: int = 512,
        system_prompt: Optional[str] = None,
        **options: Any
    ) -> Tuple[Optional[str], int, int, Dict[str, Any]]:
        """
        Submits prompt for execution.
        On physical Snapdragon X Elite hardware: runs Genie Dialog Engine.
        On unsupported development hardware (x86_64): truthfully returns None with telemetry.
        """
        report = self.inspect_capabilities()
        if not report.is_available:
            return None, 0, 0, {
                "error": report.state_description,
                "state": report.state.value,
                "hardware_valid": False,
                "simulated": False
            }

        config_path = os.path.join(self.model_dir, "genie_config.json")
        formatted_prompt = self.format_chatml_prompt(messages_or_prompt, system_prompt=system_prompt)

        reply, tokens, latency, meta = self.runtime_adapter.execute_dialog(
            config_path=config_path,
            formatted_prompt=formatted_prompt,
            max_tokens=max_tokens
        )
        if reply is not None:
            self._last_state = SnapdragonRuntimeState.INFERENCE_SUCCESSFUL
            meta["state"] = SnapdragonRuntimeState.INFERENCE_SUCCESSFUL.value
        return reply, tokens, latency, meta

    def shutdown(self) -> None:
        """Cleans up any runtime resources."""
        pass
