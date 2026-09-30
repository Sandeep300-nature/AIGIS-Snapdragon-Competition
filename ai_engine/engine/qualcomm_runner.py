import os
import sys
import shutil
import time
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

from .genie_provider import (
    SnapdragonRuntimeState,
    SnapdragonCapabilityReport,
    GenieRuntimeAdapter,
    GenieQwenProvider
)


class QualcommModelRunner:
    """
    Dedicated runtime adapter for Qualcomm AI Hub models targeting Snapdragon Hexagon NPU.
    Delegates to GenieQwenProvider for Qwen3-4B-Instruct-2507 W4A16 GenieX-QAIRT.
    
    Truthful capability enforcement:
    - Zero fabrication: never mocks NPU execution on x86_64.
    - Inspects physical architecture (requires ARM64), Genie runtime, and verified Qwen3 bundle.
    """

    REQUIRED_RUNTIME_DLLS = ["QnnHtp.dll", "QnnSystem.dll"]
    OPTIONAL_RUNTIME_DLLS = ["QnnCpu.dll", "QnnHtpV73Stub.dll", "QnnHtpPrepare.dll"]
    EXPECTED_MODEL_FILES = [
        "genie_config.json",
        "part1_of_4.bin",
        "part2_of_4.bin",
        "part3_of_4.bin",
        "part4_of_4.bin"
    ]

    cached_geniex_bundle = os.path.expanduser(r"~/.cache/geniex/models/qualcomm/Qwen3-4B-Instruct-2507")
    DEFAULT_MODEL_DIR = (
        os.getenv("AIGIS_GENIE_MODEL_DIR")
        or os.getenv("AIGIS_SNAPDRAGON_MODEL_DIR")
        or (cached_geniex_bundle if os.path.isdir(cached_geniex_bundle) else r"D:\AIGIS-Snapdragon-Models\qwen3_4b_instruct_2507-geniex_qairt-w4a16-qualcomm_snapdragon_x_elite")
    )

    def __init__(
        self,
        model_dir: Optional[str] = None,
        model_id: str = "qwen3_4b_instruct_2507",
        checkpoint: str = "DEFAULT_W4A16",
        hardware_detector: Optional[Any] = None,
        runtime_adapter: Optional[GenieRuntimeAdapter] = None,
        system_prompt: Optional[str] = None
    ):
        cached_geniex_bundle = os.path.normpath(os.path.expanduser(r"~/.cache/geniex/models/qualcomm/Qwen3-4B-Instruct-2507"))
        default_dir = cached_geniex_bundle if os.path.isdir(cached_geniex_bundle) else self.DEFAULT_MODEL_DIR
        self.model_dir = (
            model_dir
            or os.getenv("AIGIS_GENIE_MODEL_DIR")
            or os.getenv("AIGIS_SNAPDRAGON_MODEL_DIR")
            or default_dir
        )
        self.model_id = model_id
        self.checkpoint = checkpoint
        self.detector = hardware_detector or HardwareDetector
        self.runtime_adapter = runtime_adapter or GenieRuntimeAdapter()
        self.system_prompt = system_prompt
        self.provider = GenieQwenProvider(
            model_dir=self.model_dir,
            hardware_detector=self.detector,
            runtime_adapter=self.runtime_adapter,
            system_prompt=self.system_prompt
        )
        self.provider.model_id = self.model_id
        self.provider.checkpoint = self.checkpoint

    def inspect_model_artifact(self) -> Tuple[bool, List[str]]:
        """
        Discovers whether the verified Qwen3 GenieX bundle files exist locally.
        Returns: (artifact_present, missing_files)
        """
        return self.provider.inspect_model_bundle()

    def inspect_capabilities(self) -> SnapdragonCapabilityReport:
        """
        Performs comprehensive capability inspection distinguishing the 6 runtime states.
        """
        report = self.provider.inspect_capabilities()
        # Synchronize model_id and checkpoint if overridden on runner
        report.model_id = self.model_id
        report.checkpoint = self.checkpoint
        return report

    def is_available(self) -> bool:
        """Convenience method returning True ONLY when fully configured on physical hardware."""
        return self.provider.is_available()

    def run_inference(
        self,
        prompt: Union[str, List[Dict[str, str]]],
        max_new_tokens: int = 256,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Tuple[Optional[str], int, int, Dict[str, Any]]:
        """
        Executes genuine on-device inference via Qualcomm Genie dialog runtime.
        Returns: (reply_text, token_count, latency_ms, telemetry_metadata)
        
        Zero fabrication: If executed on an unsupported host, returns None with diagnostic telemetry.
        """
        return self.provider.generate(
            messages_or_prompt=prompt,
            max_tokens=max_new_tokens,
            system_prompt=system_prompt,
            **kwargs
        )


__all__ = [
    "SnapdragonRuntimeState",
    "SnapdragonCapabilityReport",
    "GenieRuntimeAdapter",
    "GenieQwenProvider",
    "QualcommModelRunner"
]
