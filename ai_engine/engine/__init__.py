"""
AIGIS Modular AIEngine Package.
Provides decoupled LocalEngine, CloudEngine, and IntentTaskRouter.
"""

from .base_engine import BaseAIEngine, EngineResponse
from .local_engine import LocalEngine
from .cloud_engine import CloudEngine
from .router import IntentTaskRouter
from .slm_pipeline import LocalSLMPipeline
from .local_stt import LocalSTTService
from .snapdragon_engine import (
    SnapdragonNPUEngine,
    SnapdragonConfig,
    HardwareNotSupportedError,
    BaseEngine
)
from .qualcomm_runner import (
    QualcommModelRunner,
    SnapdragonRuntimeState,
    SnapdragonCapabilityReport
)

# Compatibility aliases
SmolLM2Engine = LocalEngine
GroqEngine = CloudEngine

__all__ = [
    "BaseAIEngine",
    "BaseEngine",
    "EngineResponse",
    "LocalEngine",
    "CloudEngine",
    "SmolLM2Engine",
    "GroqEngine",
    "SnapdragonNPUEngine",
    "SnapdragonConfig",
    "HardwareNotSupportedError",
    "QualcommModelRunner",
    "SnapdragonRuntimeState",
    "SnapdragonCapabilityReport",
    "IntentTaskRouter",
    "LocalSLMPipeline",
    "LocalSTTService"
]

