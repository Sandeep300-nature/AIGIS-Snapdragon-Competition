from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class EngineResponse(BaseModel):
    """Standardized response schema returned by all AIEngine implementations."""
    reply: str
    provider: str
    engine: str = Field(..., description="'local' or 'cloud'")
    badge: str = Field(..., description="User-facing UI provenance badge")
    latencyMs: int = Field(default=0, description="Real measured round-trip time in milliseconds")
    urlToOpen: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostics & telemetry metadata")


class BaseAIEngine(ABC):
    """
    Abstract Base Class for AIGIS modular AI engines.
    Both LocalEngine (on-device) and CloudEngine (remote API) conform to this interface.
    """

    @abstractmethod
    def generate_response(
        self,
        prompt: str,
        session_id: str = "default-session",
        response_language: str = "en",
        **kwargs
    ) -> EngineResponse:
        """Generates a text response for the given prompt."""
        pass

    @abstractmethod
    def get_engine_info(self) -> Dict[str, Any]:
        """Returns metadata regarding active engine type, runtime, and capabilities."""
        pass
