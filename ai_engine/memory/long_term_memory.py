import os
import json
import uuid
import re
from datetime import datetime, date
from typing import List, Dict, Any, Optional

from .local_memory_vault import LocalMemoryVault

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
MEMORY_FILE = os.path.join(DATA_DIR, "long_term_memory.json")
SQLITE_VAULT_FILE = os.path.join(DATA_DIR, "aigis_local_vault.db")

SUPPORTED_CATEGORIES = {
    "USER_PREFERENCE",
    "PROJECT_CONTEXT",
    "GENERAL_KNOWLEDGE",
    "TEMPORARY_NEWS",
    "IMPROVEMENT",
    "TASK"
}

DEFAULT_PROJECT_CONTEXTS = [
    {
        "category": "PROJECT_CONTEXT",
        "importance": "HIGH",
        "content": "AIGIS uses Java Spring Boot 3 on port 8080 for REST controllers and H2 database conversation memory."
    },
    {
        "category": "PROJECT_CONTEXT",
        "importance": "HIGH",
        "content": "AIGIS Python AI Engine runs on port 8000 powering intent classification, RAG, Tavily web search, and memory orchestration."
    },
    {
        "category": "PROJECT_CONTEXT",
        "importance": "HIGH",
        "content": "LIVE_WEB uses official Tavily Search API as primary search provider with Google News RSS fallback."
    },
    {
        "category": "PROJECT_CONTEXT",
        "importance": "HIGH",
        "content": "Search providers are modularly organized inside ai_engine/providers/ (tavily_provider.py and rss_provider.py)."
    },
    {
        "category": "PROJECT_CONTEXT",
        "importance": "HIGH",
        "content": "AIGIS assistant persona is inspired by FRIDAY from Iron Man (witty, loyal, sharp, addressing user as sir)."
    }
]

SECRET_PATTERNS = [
    r'gsk_[a-zA-Z0-9_-]+',
    r'tvly-[a-zA-Z0-9_-]+',
    r'sk-[a-zA-Z0-9_-]+',
    r'bearer\s+[a-zA-Z0-9_\-\.]+',
    r'password\s*=\s*\S+',
    r'api[_-]?key\s*=\s*\S+'
]

IMPORTANCE_LEVELS = {
    "PERMANENT": {"stars": "★★★★★", "score": 5, "label": "Permanent"},
    "LONG_TERM": {"stars": "★★★★☆", "score": 4, "label": "Long-term"},
    "HIGH": {"stars": "★★★★☆", "score": 4, "label": "Long-term"},
    "PROJECT": {"stars": "★★★☆☆", "score": 3, "label": "Project"},
    "MEDIUM": {"stars": "★★★☆☆", "score": 3, "label": "Project"},
    "TEMPORARY": {"stars": "★★☆☆☆", "score": 2, "label": "Temporary"},
    "DISPOSABLE": {"stars": "★☆☆☆☆", "score": 1, "label": "Disposable"},
    "LOW": {"stars": "★☆☆☆☆", "score": 1, "label": "Disposable"}
}

def resolve_importance(imp_val: Any) -> Dict[str, Any]:
    """Resolves string or integer importance into display metadata."""
    if isinstance(imp_val, int):
        score_map = {
            5: {"stars": "★★★★★", "score": 5, "label": "Permanent"},
            4: {"stars": "★★★★☆", "score": 4, "label": "Long-term"},
            3: {"stars": "★★★☆☆", "score": 3, "label": "Project"},
            2: {"stars": "★★☆☆☆", "score": 2, "label": "Temporary"},
            1: {"stars": "★☆☆☆☆", "score": 1, "label": "Disposable"}
        }
        return score_map.get(imp_val, {"stars": "★★★☆☆", "score": 3, "label": "Project"})

    key = str(imp_val).upper().strip()
    return IMPORTANCE_LEVELS.get(key, {"stars": "★★★☆☆", "score": 3, "label": "Project"})


class LongTermMemoryStore:
    """
    Long-Term Memory Store for AIGIS backed by LocalMemoryVault (SQLite).
    Maintains 100% backward compatibility with existing REST endpoints and React UI
    while delegating persistence to SQLite aigis_local_vault.db.
    """

    def __init__(
        self,
        memory_filepath: str = MEMORY_FILE,
        db_path: Optional[str] = None
    ):
        self.filepath = memory_filepath
        self.db_path = db_path or SQLITE_VAULT_FILE

        # Initialize SQLite Vault (which auto-migrates from legacy JSON if present)
        self.vault = LocalMemoryVault(
            db_path=self.db_path,
            json_migration_path=self.filepath,
            auto_migrate=True
        )

        # Pre-seed default project contexts if empty
        if self.vault.count_memories() == 0:
            for item in DEFAULT_PROJECT_CONTEXTS:
                self.add_memory(
                    category=item["category"],
                    content=item["content"],
                    importance=item.get("importance", "PERMANENT")
                )

    @property
    def memories(self) -> List[Dict[str, Any]]:
        """Backward-compatible access to memory list."""
        all_records = self.vault.list_memories(include_expired=True)
        return [self._format_memory(r) for r in all_records]

    def _format_memory(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures 5-star rating presentation fields are present."""
        m = dict(record)
        imp_info = resolve_importance(m.get("importance", 3))
        m["stars"] = imp_info["stars"]
        m["importance_score"] = imp_info["score"]
        m["importance_label"] = imp_info["label"]
        return m

    def contains_secrets(self, text: str) -> bool:
        """Checks for API keys, passwords, or tokens."""
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def is_trivial(self, text: str) -> bool:
        """Filters out non-substantive conversational small talk."""
        clean = text.lower().strip()
        if len(clean) < 8:
            return True
        trivial_phrases = [
            "hello", "hi", "hey", "how are you", "good morning",
            "thanks", "thank you", "bye", "ok", "okay", "sure", "cool"
        ]
        return any(clean == phrase for phrase in trivial_phrases)

    def add_memory(
        self,
        category: str,
        content: str,
        importance: str = "PERMANENT",
        expires_at: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Adds or updates a memory record in the local SQLite vault.
        Applies secret scrubbing and triviality filtering.
        """
        category = category.upper().strip()
        if category not in SUPPORTED_CATEGORIES:
            category = "GENERAL_KNOWLEDGE"

        content = content.strip()
        if not content or self.contains_secrets(content) or self.is_trivial(content):
            return None

        imp_info = resolve_importance(importance)
        res = self.vault.add_memory(
            content=content,
            category=category,
            importance=imp_info["score"],
            is_pinned=False,
            source_turn="user_explicit",
            expires_at=expires_at
        )
        return self._format_memory(res) if res else None

    def get_active_memories(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves active unexpired memories from the SQLite vault."""
        records = self.vault.list_memories(category=category, include_expired=False)
        return [self._format_memory(r) for r in records]

    def get_project_contexts(self) -> List[Dict[str, Any]]:
        """Retrieves active PROJECT_CONTEXT memories."""
        return self.get_active_memories(category="PROJECT_CONTEXT")

    def update_memory(
        self,
        memory_id: str,
        content: str,
        category: Optional[str] = None,
        importance: Optional[str] = None,
        is_pinned: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        """Updates an existing memory in the SQLite vault."""
        imp_score = resolve_importance(importance)["score"] if importance else None
        res = self.vault.update_memory(
            memory_id=memory_id,
            content=content if content else None,
            category=category,
            importance=imp_score,
            is_pinned=is_pinned
        )
        return self._format_memory(res) if res else None

    def delete_memory(self, memory_id: str) -> bool:
        """Deletes a memory record from the SQLite vault."""
        return self.vault.delete_memory(memory_id)

    def pin_memory(self, memory_id: str, is_pinned: bool) -> Optional[Dict[str, Any]]:
        """Pins or unpins a memory record."""
        res = self.vault.pin_memory(memory_id, is_pinned=is_pinned)
        return self._format_memory(res) if res else None

    def export_memories(self) -> List[Dict[str, Any]]:
        """Exports all memories in a JSON-serializable list."""
        all_records = self.vault.export_memories()
        return [self._format_memory(r) for r in all_records]

    def import_memories(self, new_memories: List[Dict[str, Any]]) -> int:
        """Imports memory items into the SQLite vault."""
        return self.vault.import_memories(new_memories)

    def get_dashboard_categorized(self, query: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Categorizes memories for the Memory Dashboard View:
        - Facts (User facts & knowledge)
        - Preferences (User preferences & settings)
        - Long-Term Memories (Project context & core knowledge)
        - Recent Memories (Created or updated recently)
        """
        if query:
            active = [self._format_memory(r) for r in self.vault.search_memories(query=query, limit=100, include_expired=False)]
        else:
            active = self.get_active_memories()

        facts = []
        preferences = []
        long_term = []
        recent = []

        # Pinned items at top
        active.sort(key=lambda x: (not x.get("is_pinned", False), x.get("updated_at", "")), reverse=True)

        for m in active:
            cat = m.get("category", "GENERAL_KNOWLEDGE")
            if cat == "USER_PREFERENCE":
                preferences.append(m)
            elif cat in ["PROJECT_CONTEXT", "IMPROVEMENT"]:
                long_term.append(m)
            elif cat in ["GENERAL_KNOWLEDGE", "TASK"]:
                facts.append(m)
            else:
                recent.append(m)

        return {
            "facts": facts,
            "preferences": preferences,
            "longTerm": long_term,
            "recent": recent,
            "totalCount": len(active)
        }
