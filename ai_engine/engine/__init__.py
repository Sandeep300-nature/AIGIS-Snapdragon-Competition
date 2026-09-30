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

from .prompts import (
    AIGIS_COMPETITION_SYSTEM_PROMPT,
    get_competition_system_prompt
)
from .speech_sanitizer import (
    sanitize_speech_text,
    normalize_stt_transcript
)
from .deterministic import (
    parse_time_date_query,
    build_time_date_response,
    parse_telemetry_query,
    build_telemetry_response
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
    "LocalSTTService",
    "AIGIS_COMPETITION_SYSTEM_PROMPT",
    "get_competition_system_prompt",
    "sanitize_speech_text",
    "normalize_stt_transcript",
    "parse_time_date_query",
    "build_time_date_response"
]

