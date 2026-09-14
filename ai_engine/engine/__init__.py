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

__all__ = [
    "BaseAIEngine",
    "EngineResponse",
    "LocalEngine",
    "CloudEngine",
    "IntentTaskRouter",
    "LocalSLMPipeline",
    "LocalSTTService"
]
