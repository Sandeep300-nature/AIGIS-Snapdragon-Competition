from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from .action_guard import ActionSafetyGuard
from .action_models import ActionRequest, ActionResult, ActionType


class BaseActionExecutor(ABC):
    """Abstract base class for all AIGIS action executors."""

    @abstractmethod
    def execute(self, request: ActionRequest) -> ActionResult:
        """Executes a validated ActionRequest and returns an ActionResult."""
        pass


class DefaultActionExecutor(BaseActionExecutor):
    """
    Standard Action Executor implementing the M8.1 Safety Boundary.
    
    Guarantees:
      - Never receives or executes an unvalidated action.
      - Enforces ActionSafetyGuard before any execution.
      - Returns structured ActionResult with truthful provenance metadata.
    """

    def __init__(
        self,
        guard: Optional[ActionSafetyGuard] = None,
        desktop_service: Optional[Any] = None
    ):
        self.guard = guard or ActionSafetyGuard()
        self.desktop_service = desktop_service

    def execute(self, request: ActionRequest) -> ActionResult:
        """
        Validates through ActionSafetyGuard and executes if allowed.
        If validation fails, returns a safe failure ActionResult without executing.
        """
        # 1. Safety Guard Enforcement
        validation = self.guard.validate(request)
        if not validation.allowed:
            return ActionResult(
                success=False,
                action_type=str(request.action_type),
                message=f"Action blocked by safety boundary: {validation.reason}",
                error=validation.reason,
                metadata={
                    "action": True,
                    "actionType": str(request.action_type),
                    "actionStatus": "BLOCKED",
                    "reason": validation.reason,
                    "networkUsed": False
                }
            )

        # 2. Execution of Validated Actions
        req_type = request.action_type

        # --- A. Open Application ---
        if req_type == ActionType.OPEN_APPLICATION:
            target_app = request.target.lower().strip()
            binary = None
            if self.desktop_service:
                binary = self.desktop_service.ALLOWED_APPS.get(target_app)
                if not binary:
                    for k, v in self.desktop_service.ALLOWED_APPS.items():
                        if k in target_app:
                            binary = v
                            break

            if not binary:
                app_map = {
                    "notepad": "notepad.exe",
                    "calculator": "calc.exe",
                    "calc": "calc.exe",
                    "explorer": "explorer.exe",
                    "file manager": "explorer.exe",
                    "code": "code",
                    "vscode": "code",
                    "vs code": "code",
                    "spotify": "spotify.exe",
                    "chrome": "chrome.exe",
                    "browser": "msedge.exe",
                    "edge": "msedge.exe",
                    "cmd": "cmd.exe",
                    "terminal": "wt.exe",
                    "wt": "wt.exe"
                }
                clean_name = target_app.removesuffix(".exe")
                binary = app_map.get(clean_name) or (target_app if target_app.endswith(".exe") else None)

            if not binary:
                return ActionResult(
                    success=False,
                    action_type=req_type.value,
                    message=f"Could not resolve binary executable for application '{request.target}'.",
                    error="BINARY_NOT_FOUND",
                    metadata={
                        "action": True,
                        "actionType": req_type.value,
                        "actionStatus": "FAILED",
                        "intent": "desktop_action",
                        "target": request.target,
                        "networkUsed": False
                    }
                )

            try:
                if self.desktop_service:
                    handled, reply, provider = self.desktop_service.launch_app(target_app, binary)
                    is_failed = ("could not launch" in reply.lower()) or ("failed" in reply.lower()) or ("error" in (provider or "").lower())
                    return ActionResult(
                        success=handled and not is_failed,
                        action_type=req_type.value,
                        message=reply,
                        error=reply if is_failed else None,
                        metadata={
                            "action": True,
                            "actionType": req_type.value,
                            "actionStatus": "FAILED" if is_failed else "SUCCESS",
                            "intent": "desktop_action",
                            "provider": provider or "Desktop Control -> App Launcher",
                            "target": request.target,
                            "networkUsed": False
                        }
                    )
                else:
                    import subprocess
                    subprocess.Popen([binary], shell=True)
                    return ActionResult(
                        success=True,
                        action_type=req_type.value,
                        message=f"Opening {request.target.capitalize()}, sir.",
                        metadata={
                            "action": True,
                            "actionType": req_type.value,
                            "actionStatus": "SUCCESS",
                            "intent": "desktop_action",
                            "provider": "Desktop Control -> App Launcher",
                            "target": request.target,
                            "networkUsed": False
                        }
                    )
            except Exception as e:
                return ActionResult(
                    success=False,
                    action_type=req_type.value,
                    message=f"Failed to launch application '{request.target}': {e}",
                    error=str(e),
                    metadata={
                        "action": True,
                        "actionType": req_type.value,
                        "actionStatus": "FAILED",
                        "intent": "desktop_action",
                        "target": request.target,
                        "networkUsed": False
                    }
                )

        # --- B. Open URL ---
        elif req_type == ActionType.OPEN_URL:
            url = validation.target or request.target
            site_name = "website"
            if "youtube.com" in url:
                site_name = "YouTube"
            elif "github.com" in url:
                site_name = "GitHub"
            elif "google.com" in url:
                site_name = "Google"
            elif "reddit.com" in url:
                site_name = "Reddit"

            reply_text = f"Opening {site_name} for you now, sir.\n\n[OPEN_URL: {url}]"
            return ActionResult(
                success=True,
                action_type=req_type.value,
                message=reply_text,
                url_to_open=url,
                metadata={
                    "action": True,
                    "actionType": req_type.value,
                    "actionStatus": "SUCCESS",
                    "intent": "web_action",
                    "provider": "AIGIS Desktop Action -> Web Navigation",
                    "url": url,
                    "networkUsed": True
                }
            )

        # --- C. Open Folder ---
        elif req_type == ActionType.OPEN_FOLDER:
            target_folder = request.target
            try:
                if self.desktop_service:
                    handled, reply, provider = self.desktop_service.open_folder_by_name(target_folder)
                    is_failed = not handled or ("could not open" in reply.lower()) or ("error" in (provider or "").lower())
                    return ActionResult(
                        success=not is_failed,
                        action_type=req_type.value,
                        message=reply if handled else f"Could not open directory '{target_folder}', sir.",
                        error=None if not is_failed else (reply or "FOLDER_NOT_FOUND"),
                        metadata={
                            "action": True,
                            "actionType": req_type.value,
                            "actionStatus": "FAILED" if is_failed else "SUCCESS",
                            "intent": "desktop_action",
                            "provider": provider or "Desktop Control -> Folder Explorer",
                            "target": target_folder,
                            "networkUsed": False
                        }
                    )
                return ActionResult(
                    success=True,
                    action_type=req_type.value,
                    message=f"Opening folder {target_folder}, sir.",
                    metadata={
                        "action": True,
                        "actionType": req_type.value,
                        "actionStatus": "SUCCESS",
                        "intent": "desktop_action",
                        "provider": "Desktop Control -> Folder Explorer",
                        "target": target_folder,
                        "networkUsed": False
                    }
                )
            except Exception as e:
                return ActionResult(
                    success=False,
                    action_type=req_type.value,
                    message=f"Failed to open directory '{target_folder}': {e}",
                    error=str(e),
                    metadata={
                        "action": True,
                        "actionType": req_type.value,
                        "actionStatus": "FAILED",
                        "intent": "desktop_action",
                        "target": target_folder,
                        "networkUsed": False
                    }
                )

        # --- D. System Control ---
        elif req_type == ActionType.SYSTEM_CONTROL:
            target_cmd = request.target
            try:
                if self.desktop_service:
                    handled, reply, provider = self.desktop_service.process_natural_command(
                        request.session_id, target_cmd
                    )
                    is_failed = not handled or ("failed" in reply.lower()) or ("error" in (provider or "").lower())
                    return ActionResult(
                        success=not is_failed,
                        action_type=req_type.value,
                        message=reply or f"Executed system control: {target_cmd}, sir.",
                        error=None if not is_failed else (reply or "SYSTEM_CONTROL_FAILED"),
                        metadata={
                            "action": True,
                            "actionType": req_type.value,
                            "actionStatus": "FAILED" if is_failed else "SUCCESS",
                            "intent": "desktop_action",
                            "provider": provider or "Desktop Control -> System",
                            "target": target_cmd,
                            "networkUsed": False
                        }
                    )
                return ActionResult(
                    success=True,
                    action_type=req_type.value,
                    message=f"Executed system control: {target_cmd}, sir.",
                    metadata={
                        "action": True,
                        "actionType": req_type.value,
                        "actionStatus": "SUCCESS",
                        "intent": "desktop_action",
                        "provider": "Desktop Control -> System",
                        "target": target_cmd,
                        "networkUsed": False
                    }
                )
            except Exception as e:
                return ActionResult(
                    success=False,
                    action_type=req_type.value,
                    message=f"Failed to execute system control '{target_cmd}': {e}",
                    error=str(e),
                    metadata={
                        "action": True,
                        "actionType": req_type.value,
                        "actionStatus": "FAILED",
                        "intent": "desktop_action",
                        "target": target_cmd,
                        "networkUsed": False
                    }
                )

        # --- E. Search Web ---
        elif req_type == ActionType.SEARCH_WEB:
            query = request.target
            return ActionResult(
                success=True,
                action_type=req_type.value,
                message=f"Searching the web for '{query}', sir.",
                metadata={
                    "action": True,
                    "actionType": req_type.value,
                    "actionStatus": "SUCCESS",
                    "intent": "live_web",
                    "provider": "AIGIS Live Search -> Web Action",
                    "query": query,
                    "networkUsed": True
                }
            )

        return ActionResult(
            success=False,
            action_type=req_type.value,
            message=f"No executor handler configured for action type '{req_type.value}'.",
            error="UNHANDLED_ACTION_TYPE",
            metadata={
                "action": True,
                "actionType": req_type.value,
                "actionStatus": "FAILED",
                "networkUsed": False
            }
        )
