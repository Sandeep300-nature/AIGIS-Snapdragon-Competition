import os
import sys

# Ensure ai_engine package directory is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from .engine.snapdragon_engine import (
        SnapdragonNPUEngine,
        SnapdragonConfig,
        HardwareNotSupportedError,
        BaseEngine
    )
except ImportError:
    from engine.snapdragon_engine import (
        SnapdragonNPUEngine,
        SnapdragonConfig,
        HardwareNotSupportedError,
        BaseEngine
    )

__all__ = [
    "SnapdragonNPUEngine",
    "SnapdragonConfig",
    "HardwareNotSupportedError",
    "BaseEngine"
]
