import re
import urllib.parse
from typing import Any, Dict, Optional, Set

from .action_models import (
    ActionRequest,
    ActionSafetyStatus,
    ActionType,
    ActionValidationResult,
)


class ActionSafetyGuard:
    """
    Deterministic Action Safety Boundary for AIGIS.
    
    Responsibilities:
      - Validates ActionRequest BEFORE execution.
      - Enforces strict allowlists for action types, applications, and URLs.
      - Blocks arbitrary command execution, shell injection, and destructive commands.
      - Deterministic: Zero LLM dependency, zero network access, zero side-effects.
      - Does NOT execute any actions; purely validates.
    """

    ALLOWED_APPLICATIONS: Set[str] = {
        "notepad", "calculator", "calc", "explorer", "file manager",
        "vs code", "vscode", "code", "spotify", "chrome",
        "browser", "edge", "cmd", "terminal", "wt"
    }

    ALLOWED_APP_BINARIES: Set[str] = {
        "notepad.exe", "calc.exe", "explorer.exe", "spotify.exe",
        "chrome.exe", "msedge.exe", "cmd.exe", "wt.exe", "code"
    }

    ALLOWED_FOLDERS: Set[str] = {
        "downloads", "documents", "desktop", "c drive", "c:\\", "c:/"
    }

    ALLOWED_SYSTEM_COMMANDS: Set[str] = {
        "mute", "volume_up", "volume_down", "volume up", "volume down",
        "play_pause", "play media", "pause media",
        "next_track", "next song", "previous_track", "previous song",
        "lock", "lock workstation", "lock screen",
        "sleep", "sleep pc", "sleep workstation"
    }

    # Dangerous command injection patterns & destructive verbs
    PROHIBITED_COMMAND_PATTERNS = [
        r'\brmdir\b', r'\bdel\s+/[fFqQsS]\b', r'\bdel\s+[a-zA-Z]:', r'\bdel\s+\*',
        r'\brm\s+-[rfRF]+\b', r'\bformat\s+[a-zA-Z]:', r'\bformat\s+disk\b', r'\bformat\s+drive\b',
        r'\bpowershell\b', r'\bcmd\.exe\s+/[cC]\b', r'\bcmd\s+/[cC]\b',
        r'\bsh\s+-[cC]\b', r'\bbash\s+-[cC]\b',
        r'\btaskkill\s+/[fF]\b', r'\bnet\s+user\b', r'\breg\s+(?:add|delete)\b',
        r'\bchmod\s+[-+]?[0-9rwx]+\b', r'\bcurl\b.*\|\s*(?:sh|bash|powershell)',
        r'[;&|`]', r'\$\(', r'\bdrop\s+table\b', r'\bdrop\s+database\b', r'\bwipe\s+(?:disk|drive)\b'
    ]

    UNSAFE_SYSTEM_PATHS = [
        "system32", "syswow64", "windows\\system", "\\windows\\",
        "/etc/", "/usr/", "/bin/", "/var/"
    ]

    def validate_raw_prompt(self, prompt: str) -> Optional[ActionValidationResult]:
        """
        Scans a raw natural language prompt for prohibited command execution or destructive commands.
        Returns ActionValidationResult if prohibited, or None if safe.
        """
        lowered = (prompt or "").strip().lower()
        if not lowered:
            return None

        # Check for explicit shell command execution attempts
        for pattern in self.PROHIBITED_COMMAND_PATTERNS:
            if re.search(pattern, lowered, re.IGNORECASE):
                return ActionValidationResult(
                    allowed=False,
                    status=ActionSafetyStatus.BLOCKED,
                    reason="Arbitrary command execution, shell injection, and destructive commands are strictly prohibited.",
                    action_type="PROHIBITED_COMMAND",
                    target=prompt.strip(),
                    metadata={"violation": "COMMAND_INJECTION_OR_DESTRUCTIVE"}
                )

        return None

    def validate(self, request: ActionRequest) -> ActionValidationResult:
        """
        Validates an ActionRequest against the deterministic safety boundary.
        Returns ActionValidationResult indicating whether execution is allowed.
        """
        # 1. Validate request structure & ActionType
        if not isinstance(request, ActionRequest):
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.INVALID,
                reason="Invalid request object: must be an instance of ActionRequest."
            )

        if not isinstance(request.action_type, ActionType):
            try:
                # Attempt conversion if passed as string
                req_type = ActionType(request.action_type)
            except ValueError:
                return ActionValidationResult(
                    allowed=False,
                    status=ActionSafetyStatus.BLOCKED,
                    reason=f"Action type '{request.action_type}' is unknown or not allowlisted.",
                    action_type=str(request.action_type)
                )
        else:
            req_type = request.action_type

        # 2. Validate target presence
        target = (request.target or "").strip()
        if not target:
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.INVALID,
                reason="Target cannot be empty or whitespace.",
                action_type=req_type.value
            )

        # 3. Check for null bytes and control characters
        if "\0" in target or any(ord(c) < 32 and c not in "\t\n\r" for c in target):
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.BLOCKED,
                reason="Target contains dangerous control characters or null bytes.",
                action_type=req_type.value,
                target=target
            )

        # 4. Check for arbitrary command injection & destructive actions
        lowered_target = target.lower()
        for pattern in self.PROHIBITED_COMMAND_PATTERNS:
            if re.search(pattern, lowered_target, re.IGNORECASE):
                return ActionValidationResult(
                    allowed=False,
                    status=ActionSafetyStatus.BLOCKED,
                    reason="Arbitrary command execution, shell injection, and destructive commands are strictly prohibited.",
                    action_type=req_type.value,
                    target=target,
                    metadata={"violation": "COMMAND_INJECTION_OR_DESTRUCTIVE"}
                )

        # 5. Action-specific validation
        if req_type == ActionType.OPEN_APPLICATION:
            return self._validate_open_application(target)

        elif req_type == ActionType.OPEN_URL:
            return self._validate_open_url(target)

        elif req_type == ActionType.OPEN_FOLDER:
            return self._validate_open_folder(target)

        elif req_type == ActionType.SYSTEM_CONTROL:
            return self._validate_system_control(target)

        elif req_type == ActionType.SEARCH_WEB:
            return self._validate_search_web(target)

        return ActionValidationResult(
            allowed=False,
            status=ActionSafetyStatus.BLOCKED,
            reason=f"Action type '{req_type.value}' is not supported by safety guard.",
            action_type=req_type.value,
            target=target
        )

    def _validate_open_application(self, target: str) -> ActionValidationResult:
        """Validates that requested application is in the deterministic allowlist."""
        normalized = target.lower().strip()
        # Remove common wrapping extensions
        clean_name = normalized.removesuffix(".exe")

        is_allowed = (
            clean_name in self.ALLOWED_APPLICATIONS or
            normalized in self.ALLOWED_APP_BINARIES or
            any(allowed in normalized for allowed in self.ALLOWED_APPLICATIONS)
        )

        if not is_allowed:
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.BLOCKED,
                reason=f"Application '{target}' is not in the allowlist of safe applications.",
                action_type=ActionType.OPEN_APPLICATION.value,
                target=target
            )

        return ActionValidationResult(
            allowed=True,
            status=ActionSafetyStatus.ALLOWED,
            reason=f"Application '{target}' is verified and allowlisted.",
            action_type=ActionType.OPEN_APPLICATION.value,
            target=target
        )

    def _validate_open_url(self, target: str) -> ActionValidationResult:
        """Validates that URL has a safe http/https scheme and a valid domain."""
        url = target.strip()

        # Check if an explicit scheme is present (e.g. javascript:, file:, http:, https:)
        scheme_match = re.match(r'^([a-zA-Z][a-zA-Z0-9+.-]*):', url)
        if scheme_match:
            scheme = scheme_match.group(1).lower()
            if scheme not in ("http", "https"):
                return ActionValidationResult(
                    allowed=False,
                    status=ActionSafetyStatus.BLOCKED,
                    reason=f"Unsafe URL scheme '{scheme}'. Only http and https are permitted.",
                    action_type=ActionType.OPEN_URL.value,
                    target=target
                )
        else:
            # Prepend https:// if raw domain was supplied
            url = f"https://{url}"

        try:
            parsed = urllib.parse.urlparse(url)
        except Exception:
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.INVALID,
                reason=f"Malformed URL: '{target}'.",
                action_type=ActionType.OPEN_URL.value,
                target=target
            )

        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.BLOCKED,
                reason=f"Unsafe URL scheme '{scheme}'. Only http and https are permitted.",
                action_type=ActionType.OPEN_URL.value,
                target=target
            )

        netloc = parsed.netloc.strip()
        if not netloc or "." not in netloc:
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.INVALID,
                reason=f"Invalid or missing domain in URL: '{target}'.",
                action_type=ActionType.OPEN_URL.value,
                target=target
            )

        # Check for invalid hostname characters
        if re.search(r'[^a-zA-Z0-9.\-:]', netloc):
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.INVALID,
                reason=f"URL contains invalid characters in hostname: '{netloc}'.",
                action_type=ActionType.OPEN_URL.value,
                target=target
            )

        return ActionValidationResult(
            allowed=True,
            status=ActionSafetyStatus.ALLOWED,
            reason=f"URL '{url}' is valid and allowlisted for navigation.",
            action_type=ActionType.OPEN_URL.value,
            target=url
        )

    def _validate_open_folder(self, target: str) -> ActionValidationResult:
        """Validates that requested folder is an authorized, safe user directory."""
        normalized = target.lower().strip()

        # Reject path traversal
        if ".." in normalized:
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.BLOCKED,
                reason="Path traversal (..) is strictly prohibited.",
                action_type=ActionType.OPEN_FOLDER.value,
                target=target
            )

        # Reject system paths
        if any(sys_path in normalized for sys_path in self.UNSAFE_SYSTEM_PATHS):
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.BLOCKED,
                reason="Access to operating system system directories is restricted.",
                action_type=ActionType.OPEN_FOLDER.value,
                target=target
            )

        is_allowed = (
            any(f in normalized for f in self.ALLOWED_FOLDERS) or
            normalized in self.ALLOWED_FOLDERS
        )

        if not is_allowed:
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.BLOCKED,
                reason=f"Directory '{target}' is not in the allowlist of safe user folders.",
                action_type=ActionType.OPEN_FOLDER.value,
                target=target
            )

        return ActionValidationResult(
            allowed=True,
            status=ActionSafetyStatus.ALLOWED,
            reason=f"Folder target '{target}' is allowlisted.",
            action_type=ActionType.OPEN_FOLDER.value,
            target=target
        )

    def _validate_system_control(self, target: str) -> ActionValidationResult:
        """Validates that system control command is authorized and non-destructive."""
        normalized = target.lower().strip()
        if normalized not in self.ALLOWED_SYSTEM_COMMANDS:
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.BLOCKED,
                reason=f"System control command '{target}' is not allowlisted.",
                action_type=ActionType.SYSTEM_CONTROL.value,
                target=target
            )

        return ActionValidationResult(
            allowed=True,
            status=ActionSafetyStatus.ALLOWED,
            reason=f"System control command '{target}' is verified and allowlisted.",
            action_type=ActionType.SYSTEM_CONTROL.value,
            target=target
        )

    def _validate_search_web(self, target: str) -> ActionValidationResult:
        """Validates that search query is non-empty and contains no command injection."""
        clean_q = target.strip()
        if not clean_q:
            return ActionValidationResult(
                allowed=False,
                status=ActionSafetyStatus.INVALID,
                reason="Search query cannot be empty.",
                action_type=ActionType.SEARCH_WEB.value,
                target=target
            )

        return ActionValidationResult(
            allowed=True,
            status=ActionSafetyStatus.ALLOWED,
            reason="Web search query is valid.",
            action_type=ActionType.SEARCH_WEB.value,
            target=clean_q
        )

    def parse_from_prompt(self, prompt: str, session_id: str = "default-session") -> Optional[ActionRequest]:
        """
        Deterministically parses natural language prompts into structured ActionRequests.
        Returns None if prompt is not an actionable command.
        """
        raw = (prompt or "").strip()
        if not raw:
            return None

        p = raw.lower()

        # Clean conversational prefixes & wake words (e.g. "Can you open YouTube, AIGIS?")
        clean_p = re.sub(
            r'^(hey\s+)?(aigis|a\.i\.g\.i\.s\.|friday|assistant)?\s*(can\s+you|could\s+you|would\s+you|please|kindly|i\s+want\s+you\s+to|go\s+ahead\s+and)?\s*',
            '',
            p,
            flags=re.IGNORECASE
        ).strip()
        clean_p = re.sub(r'[,\s]+(aigis|friday|sir|please)[?.!]*$', '', clean_p, flags=re.IGNORECASE).strip()

        # 1. Direct explicit HTTP/HTTPS URL in prompt
        url_match = re.search(r'https?://[^\s]+', raw)
        if url_match:
            return ActionRequest(
                action_type=ActionType.OPEN_URL,
                target=url_match.group(0),
                session_id=session_id
            )

        # 2. Desktop App Launching (e.g. "open notepad", "launch calculator", "start chrome")
        app_match = re.match(r'^(open|launch|start)\s+(the\s+)?([a-zA-Z0-9\s._-]+)$', clean_p)
        if app_match:
            candidate = app_match.group(3).strip()
            # Check if candidate matches folder
            if any(f in candidate for f in ["folder", "directory", "downloads", "documents", "desktop", "c drive"]):
                return ActionRequest(
                    action_type=ActionType.OPEN_FOLDER,
                    target=candidate,
                    session_id=session_id
                )

            # Check if candidate is an allowed or candidate application
            for app_key in self.ALLOWED_APPLICATIONS:
                if app_key in candidate:
                    return ActionRequest(
                        action_type=ActionType.OPEN_APPLICATION,
                        target=app_key,
                        session_id=session_id
                    )

            # Check if candidate is a website shortcut (e.g. "open youtube")
            website_url = self._detect_website_url(candidate)
            if website_url:
                return ActionRequest(
                    action_type=ActionType.OPEN_URL,
                    target=website_url,
                    session_id=session_id
                )

            # If user explicitly said "open X", return ActionRequest so ActionSafetyGuard can validate/block
            return ActionRequest(
                action_type=ActionType.OPEN_APPLICATION,
                target=candidate,
                session_id=session_id
            )

        # 3. Web navigation shortcuts (e.g. "open youtube", "go to github")
        website_url = self._detect_website_url(clean_p)
        if website_url:
            return ActionRequest(
                action_type=ActionType.OPEN_URL,
                target=website_url,
                session_id=session_id
            )

        # 4. Web Search Action (e.g. "search the web for quantum computing")
        search_match = re.match(r'^(search\s+(the\s+)?(web|internet)\s+(for\s+)?|look\s+up\s+on\s+(the\s+)?web\s+)(.+)$', clean_p)
        if search_match:
            query = search_match.group(6).strip()
            if query:
                return ActionRequest(
                    action_type=ActionType.SEARCH_WEB,
                    target=query,
                    session_id=session_id
                )

        # 5. System Hardware Controls
        if "mute" in clean_p:
            return ActionRequest(
                action_type=ActionType.SYSTEM_CONTROL,
                target="mute",
                session_id=session_id
            )
        elif "volume up" in clean_p or "increase volume" in clean_p or "louder" in clean_p:
            return ActionRequest(
                action_type=ActionType.SYSTEM_CONTROL,
                target="volume_up",
                session_id=session_id
            )
        elif "volume down" in clean_p or "decrease volume" in clean_p or "lower volume" in clean_p:
            return ActionRequest(
                action_type=ActionType.SYSTEM_CONTROL,
                target="volume_down",
                session_id=session_id
            )
        elif any(kw in clean_p for kw in ["play media", "pause media", "play music", "pause music", "toggle media"]):
            return ActionRequest(
                action_type=ActionType.SYSTEM_CONTROL,
                target="play_pause",
                session_id=session_id
            )
        elif any(kw in clean_p for kw in ["next track", "next song", "skip song"]):
            return ActionRequest(
                action_type=ActionType.SYSTEM_CONTROL,
                target="next_track",
                session_id=session_id
            )
        elif any(kw in clean_p for kw in ["previous track", "prev song", "previous song"]):
            return ActionRequest(
                action_type=ActionType.SYSTEM_CONTROL,
                target="previous_track",
                session_id=session_id
            )
        elif any(kw in clean_p for kw in ["lock workstation", "lock computer", "lock pc", "lock screen"]):
            return ActionRequest(
                action_type=ActionType.SYSTEM_CONTROL,
                target="lock",
                session_id=session_id
            )
        elif any(kw in clean_p for kw in ["sleep pc", "sleep computer", "put pc to sleep"]):
            return ActionRequest(
                action_type=ActionType.SYSTEM_CONTROL,
                target="sleep",
                session_id=session_id
            )

        return None

    def _detect_website_url(self, text: str) -> Optional[str]:
        """Detects common website navigation targets."""
        shortcuts = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "github": "https://www.github.com",
            "reddit": "https://www.reddit.com",
            "twitter": "https://www.twitter.com",
            "x.com": "https://www.x.com",
            "wikipedia": "https://www.wikipedia.org",
            "amazon": "https://www.amazon.com",
            "netflix": "https://www.netflix.com"
        }
        for name, url in shortcuts.items():
            if re.search(r'\b' + re.escape(name) + r'\b', text):
                return url
        return None
