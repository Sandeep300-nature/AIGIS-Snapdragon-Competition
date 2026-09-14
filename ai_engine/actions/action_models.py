from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ActionType(str, Enum):
    """
    Allowlisted, safe Action Types supported by AIGIS.
    Only covers actions that the existing AIGIS implementation can actually execute.
    """
    OPEN_APPLICATION = "OPEN_APPLICATION"
    OPEN_URL = "OPEN_URL"
    SEARCH_WEB = "SEARCH_WEB"
    OPEN_FOLDER = "OPEN_FOLDER"
    SYSTEM_CONTROL = "SYSTEM_CONTROL"


class ActionSafetyStatus(str, Enum):
    """Deterministic Safety Validation States."""
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"


@dataclass
class ActionValidationResult:
    """Outcome of ActionSafetyGuard validation before any execution occurs."""
    allowed: bool
    status: ActionSafetyStatus
    reason: str
    action_type: Optional[str] = None
    target: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionRequest:
    """Structured request to perform an action."""
    action_type: ActionType
    target: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    source_intent: str = "ACTION"
    session_id: str = "default-session"


@dataclass
class ActionResult:
    """Outcome of an action execution."""
    success: bool
    action_type: str
    message: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    url_to_open: Optional[str] = None
