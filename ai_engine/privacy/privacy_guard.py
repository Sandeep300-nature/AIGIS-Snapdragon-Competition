import re
from enum import Enum
from typing import Dict, Any, Tuple, Optional, Union, NamedTuple, List
from dataclasses import dataclass


class PrivacyMode(str, Enum):
    LOCAL_ONLY = "LOCAL_ONLY"
    AUTO = "AUTO"
    CLOUD_PERMITTED = "CLOUD_PERMITTED"


class ContentSensitivity(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    SECRET = "SECRET"


class PrivateIntent(str, Enum):
    MEMORY_QUERY = "MEMORY_QUERY"
    DOCUMENT_QUERY = "DOCUMENT_QUERY"
    PRIVATE_PROJECT_QUERY = "PRIVATE_PROJECT_QUERY"
    PUBLIC = "PUBLIC"


class ContextFilterResult(NamedTuple):
    proj_context: str = ""
    long_memory: str = ""
    rag_context: str = ""

    @property
    def safe_proj_ctx(self) -> str:
        return self.proj_context

    @property
    def safe_long_mem(self) -> str:
        return self.long_memory

    @property
    def safe_rag(self) -> str:
        return self.rag_context


@dataclass
class ContextBundle:
    proj_context: str = ""
    long_memory: str = ""
    rag_context: str = ""
    private_context_used: bool = False
    allowed: bool = True
    combined_context: str = ""


class ContentClassifier:
    """
    Deterministic, zero-cloud content and intent classifier for privacy enforcement.
    """

    # Common secret patterns (API keys, tokens, passwords, private keys)
    SECRET_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9_\-]{16,}", re.IGNORECASE),
        re.compile(r"gsk_[a-zA-Z0-9_\-]{16,}", re.IGNORECASE),
        re.compile(r"gh[pousr]_[a-zA-Z0-9]{16,}", re.IGNORECASE),
        re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
        re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{16,}", re.IGNORECASE),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"\b(?:api[_-]?key|apikey|secret|token|password|passwd)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.]{8,}['\"]?", re.IGNORECASE),
    ]

    # Private context markers (memories, project context, document index chunks)
    PRIVATE_MARKERS = [
        "retrieved memory",
        "[memory]",
        "user memory",
        "long-term memory",
        "relevant memories",
        "relevant long-term memories",
        "user profile",
        "memory:",
        "project context",
        "[project]",
        "project architecture",
        "project status",
        "current project",
        "active project",
        "retrieved document index",
        "retrieved document chunks",
        "[document chunk",
        "document chunk",
        "[rag chunk",
        "rag index",
        "retrieved rag",
        "(score:",
    ]

    MEMORY_QUERY_PATTERNS = [
        "what do you remember",
        "what do you know about me",
        "know about me",
        "my memories",
        "search my memories",
        "remember about me",
        "recall about me",
        "do you remember",
        "what do you recall",
        "what memories",
        "my memory",
        "stored memories",
        "what have you remembered",
        # Natural query variants (asking about previously stored facts/instructions)
        "ask you to remember",
        "asked you to remember",
        "ask you to recall",
        "asked you to recall",
        "tell you to remember",
        "told you to remember",
        "what did i ask you to remember",
        "what did i tell you to remember",
        "what did i ask you to recall",
        "what did i tell you to recall",
        "what i asked you to remember",
        "what i told you to remember",
        "what you remember",
        "what you recall",
        "things to remember",
        "things you remember",
    ]

    DOCUMENT_QUERY_PATTERNS = [
        "search my files",
        "find in my documents",
        "look in my files",
        "search my documents",
        "find in my files",
        "look through my files",
        "look in documents",
        "find in documents",
        "search in my documents",
        "search files",
        "find in files",
    ]

    PROJECT_QUERY_PATTERNS = [
        "my project",
        "our architecture",
        "the project uses",
        "our project",
        "project status",
        "about my project",
        "in my project",
        "project architecture",
    ]

    @classmethod
    def classify(cls, text: str) -> ContentSensitivity:
        """Classifies a block of text into PUBLIC, PRIVATE, or SECRET."""
        if not text or not text.strip():
            return ContentSensitivity.PUBLIC

        # Check for secrets first (highest sensitivity)
        for pattern in cls.SECRET_PATTERNS:
            if pattern.search(text):
                return ContentSensitivity.SECRET

        # Check for private markers (memories, project context, document chunks)
        lowered = text.lower()
        for marker in cls.PRIVATE_MARKERS:
            if marker in lowered:
                return ContentSensitivity.PRIVATE

        return ContentSensitivity.PUBLIC

    @classmethod
    def strip_secrets(cls, text: str) -> str:
        """Strips secrets (API keys, passwords, credentials) by replacing them with a redacted marker."""
        if not text:
            return ""
        sanitized = text
        for pattern in cls.SECRET_PATTERNS:
            sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
        return sanitized

    @classmethod
    def classify_intent(cls, prompt: str) -> PrivateIntent:
        """Classifies prompt intent into MEMORY_QUERY, DOCUMENT_QUERY, PRIVATE_PROJECT_QUERY, or PUBLIC."""
        if not prompt:
            return PrivateIntent.PUBLIC

        lowered = prompt.strip().lower()

        # Priority 1: Private Memory Queries
        for pattern in cls.MEMORY_QUERY_PATTERNS:
            if pattern in lowered:
                return PrivateIntent.MEMORY_QUERY

        # Priority 2: Private Document Queries
        for pattern in cls.DOCUMENT_QUERY_PATTERNS:
            if pattern in lowered:
                return PrivateIntent.DOCUMENT_QUERY

        # Priority 3: Private Project Queries
        for pattern in cls.PROJECT_QUERY_PATTERNS:
            if pattern in lowered:
                return PrivateIntent.PRIVATE_PROJECT_QUERY

        return PrivateIntent.PUBLIC


class PrivacyGuard:
    """
    Code-enforced deterministic privacy guard that prevents private data
    (memories, project context, document chunks, secrets) from reaching cloud APIs.
    """

    def __init__(self, mode: Union[PrivacyMode, str] = PrivacyMode.AUTO):
        if isinstance(mode, str):
            try:
                self.mode = PrivacyMode(mode.upper())
            except ValueError:
                self.mode = PrivacyMode.AUTO
        else:
            self.mode = mode

    def is_private_intent(self, prompt: str) -> bool:
        """Returns True if the prompt targets personal memory, private documents, or project architecture."""
        intent = ContentClassifier.classify_intent(prompt)
        return intent in (
            PrivateIntent.MEMORY_QUERY,
            PrivateIntent.DOCUMENT_QUERY,
            PrivateIntent.PRIVATE_PROJECT_QUERY
        )

    def filter_context_for_cloud(
        self,
        proj_ctx: str = "",
        long_mem: str = "",
        rag_ctx: str = ""
    ) -> ContextFilterResult:
        """
        Returns stripped (empty) strings for cloud calls in AUTO/LOCAL_ONLY mode.
        In CLOUD_PERMITTED mode, allows non-secret context while strictly stripping secrets.
        """
        p_ctx = proj_ctx or ""
        l_mem = long_mem or ""
        r_ctx = rag_ctx or ""

        if self.mode in (PrivacyMode.AUTO, PrivacyMode.LOCAL_ONLY):
            # Strict blocking: zero private context sent to cloud
            return ContextFilterResult(proj_context="", long_memory="", rag_context="")

        if self.mode == PrivacyMode.CLOUD_PERMITTED:
            # Cloud permitted for general context, but secrets (API keys etc.) are always stripped
            safe_proj = ContentClassifier.strip_secrets(p_ctx)
            safe_mem = ContentClassifier.strip_secrets(l_mem)
            safe_rag = ContentClassifier.strip_secrets(r_ctx)
            return ContextFilterResult(
                proj_context=safe_proj,
                long_memory=safe_mem,
                rag_context=safe_rag
            )

        return ContextFilterResult(proj_context="", long_memory="", rag_context="")

    def filter_context(
        self,
        proj_ctx: str = "",
        long_mem: str = "",
        rag_ctx: str = "",
        engine_type: str = "local"
    ) -> ContextFilterResult:
        """
        Generic filter for any engine type.
        Local execution passes all context, cloud execution applies cloud filtering.
        """
        if engine_type == "local":
            return ContextFilterResult(
                proj_context=proj_ctx or "",
                long_memory=long_mem or "",
                rag_context=rag_ctx or ""
            )
        return self.filter_context_for_cloud(proj_ctx, long_mem, rag_ctx)

    def build_context_for_request(
        self,
        prompt: str,
        engine_type: str = "local",
        proj_ctx: str = "",
        long_mem: str = "",
        rag_ctx: str = ""
    ) -> ContextBundle:
        """
        Single choke-point for context injection.
        Guarantees local requests receive all context, while cloud requests obey privacy mode rules.
        """
        p_ctx = proj_ctx or ""
        l_mem = long_mem or ""
        r_ctx = rag_ctx or ""

        if engine_type == "local":
            parts = [p for p in (p_ctx, l_mem, r_ctx) if p.strip()]
            combined = "\n\n".join(parts)
            has_private = bool(parts)
            return ContextBundle(
                proj_context=p_ctx,
                long_memory=l_mem,
                rag_context=r_ctx,
                private_context_used=has_private,
                allowed=True,
                combined_context=combined
            )

        # Cloud engine request
        if self.mode == PrivacyMode.LOCAL_ONLY:
            # Cloud is forbidden in LOCAL_ONLY mode
            return ContextBundle(
                proj_context="",
                long_memory="",
                rag_context="",
                private_context_used=False,
                allowed=False,
                combined_context=""
            )

        safe = self.filter_context_for_cloud(p_ctx, l_mem, r_ctx)
        safe_parts = [p for p in (safe.proj_context, safe.long_memory, safe.rag_context) if p.strip()]
        combined = "\n\n".join(safe_parts)
        has_private = bool(safe_parts)

        return ContextBundle(
            proj_context=safe.proj_context,
            long_memory=safe.long_memory,
            rag_context=safe.rag_context,
            private_context_used=has_private,
            allowed=True,
            combined_context=combined
        )

    def create_provenance_metadata(
        self,
        engine_type: str,
        private_context_used: bool,
        privacy_mode: Union[PrivacyMode, str] = PrivacyMode.AUTO,
        network_used: bool = False,
        privacy_intent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates standard provenance metadata attached to router/engine responses."""
        if isinstance(privacy_mode, PrivacyMode):
            mode_val = privacy_mode.value
        else:
            mode_val = str(privacy_mode).upper()

        meta = {
            "privacyMode": mode_val,
            "networkUsed": bool(network_used),
            "privateContextUsed": bool(private_context_used),
            "engineType": engine_type,
        }
        if privacy_intent is not None:
            meta["privacyIntent"] = privacy_intent
        return meta
