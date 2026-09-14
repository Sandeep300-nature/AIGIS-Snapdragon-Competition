import os
import json
import uuid
import re
from datetime import datetime, date
from typing import List, Dict, Any, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
MEMORY_FILE = os.path.join(DATA_DIR, "long_term_memory.json")

SUPPORTED_CATEGORIES = {
    "USER_PREFERENCE",
    "PROJECT_CONTEXT",
    "GENERAL_KNOWLEDGE",
    "TEMPORARY_NEWS",
    "IMPROVEMENT",
    "TASK"
}

# Pre-seeded core project context memories (Part 6)
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

def resolve_importance(imp_str: str) -> Dict[str, Any]:
    key = str(imp_str).upper().strip()
    return IMPORTANCE_LEVELS.get(key, {"stars": "★★★☆☆", "score": 3, "label": "Project"})

class LongTermMemoryStore:
    """
    Structured Long-Term Memory Store with 5-Star Memory Importance Rating:
    - ★★★★★ Permanent (5 stars)
    - ★★★★☆ Long-term (4 stars)
    - ★★★☆☆ Project (3 stars)
    - ★★☆☆☆ Temporary (2 stars)
    - ★☆☆☆☆ Disposable (1 star)
    """

    def __init__(self, memory_filepath: str = MEMORY_FILE):
        self.filepath = memory_filepath
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        self.memories: List[Dict[str, Any]] = []
        self._load_memory()

    def _load_memory(self):
        """Loads memory from JSON file. Pre-seeds default project context if empty."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.memories = json.load(f)
            except Exception as e:
                print(f"[MEMORY WARNING] Could not read {self.filepath}: {e}")
                self.memories = []

        if not self.memories:
            for item in DEFAULT_PROJECT_CONTEXTS:
                self.add_memory(
                    category=item["category"],
                    content=item["content"],
                    importance=item.get("importance", "PERMANENT")
                )
            self._save_memory()

    def _save_memory(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.memories, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[MEMORY ERROR] Could not save {self.filepath}: {e}")

    def contains_secrets(self, text: str) -> bool:
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def is_trivial(self, text: str) -> bool:
        clean = text.lower().strip()
        if len(clean) < 8:
            return True
        trivial_phrases = ["hello", "hi", "hey", "how are you", "good morning", "thanks", "thank you", "bye"]
        return any(clean == phrase for phrase in trivial_phrases)

    def add_memory(self, category: str, content: str, importance: str = "PERMANENT", expires_at: Optional[str] = None) -> Optional[Dict[str, Any]]:
        category = category.upper().strip()
        if category not in SUPPORTED_CATEGORIES:
            category = "GENERAL_KNOWLEDGE"

        content = content.strip()
        if not content or self.contains_secrets(content) or self.is_trivial(content):
            return None

        imp_info = resolve_importance(importance)

        for existing in self.memories:
            if existing.get("category") == category:
                existing_content = existing.get("content", "").lower()
                new_content = content.lower()
                if existing_content == new_content or (len(new_content) > 15 and new_content in existing_content):
                    existing["updated_at"] = datetime.now().isoformat()
                    existing["importance"] = importance.upper()
                    existing["stars"] = imp_info["stars"]
                    existing["importance_score"] = imp_info["score"]
                    existing["importance_label"] = imp_info["label"]
                    if expires_at:
                        existing["expires_at"] = expires_at
                    self._save_memory()
                    return existing

        now_str = datetime.now().isoformat()
        memory_entry = {
            "id": str(uuid.uuid4()),
            "category": category,
            "importance": importance.upper(),
            "stars": imp_info["stars"],
            "importance_score": imp_info["score"],
            "importance_label": imp_info["label"],
            "created_at": now_str,
            "updated_at": now_str,
            "expires_at": expires_at,
            "content": content,
            "embedding": None
        }

        self.memories.append(memory_entry)
        self._save_memory()
        return memory_entry


    def get_active_memories(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns active memories. Filters out expired TEMPORARY_NEWS (Part 4).
        """
        today_str = date.today().isoformat()
        active = []

        for m in self.memories:
            expires_at = m.get("expires_at")
            if expires_at and expires_at < today_str:
                continue  # Skip expired news/memories

            if category and m.get("category") != category.upper():
                continue

            active.append(m)

        return active

    def get_project_contexts(self) -> List[Dict[str, Any]]:
        """Retrieves all active PROJECT_CONTEXT memories."""
        return self.get_active_memories(category="PROJECT_CONTEXT")

    def update_memory(self, memory_id: str, content: str, category: Optional[str] = None, importance: Optional[str] = None, is_pinned: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        """Updates an existing memory by ID."""
        for m in self.memories:
            if m.get("id") == memory_id:
                if content:
                    m["content"] = content.strip()
                if category and category.upper() in SUPPORTED_CATEGORIES:
                    m["category"] = category.upper()
                if importance:
                    m["importance"] = importance.upper()
                if is_pinned is not None:
                    m["is_pinned"] = is_pinned
                m["updated_at"] = datetime.now().isoformat()
                self._save_memory()
                return m
        return None

    def delete_memory(self, memory_id: str) -> bool:
        """Deletes a memory item by ID."""
        initial_len = len(self.memories)
        self.memories = [m for m in self.memories if m.get("id") != memory_id]
        if len(self.memories) < initial_len:
            self._save_memory()
            return True
        return False

    def pin_memory(self, memory_id: str, is_pinned: bool) -> Optional[Dict[str, Any]]:
        """Pins or unpins a memory item."""
        return self.update_memory(memory_id, content="", is_pinned=is_pinned)

    def export_memories(self) -> List[Dict[str, Any]]:
        """Exports all memories for JSON backup."""
        return self.memories

    def import_memories(self, new_memories: List[Dict[str, Any]]) -> int:
        """Imports a list of memory objects."""
        count = 0
        for item in new_memories:
            if isinstance(item, dict) and "content" in item:
                res = self.add_memory(
                    category=item.get("category", "GENERAL_KNOWLEDGE"),
                    content=item.get("content", ""),
                    importance=item.get("importance", "MEDIUM")
                )
                if res:
                    if item.get("is_pinned"):
                        res["is_pinned"] = True
                    count += 1
        self._save_memory()
        return count

    def get_dashboard_categorized(self, query: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Categorizes memories for the Memory Dashboard View:
        - Facts (User facts & knowledge)
        - Preferences (User preferences & settings)
        - Long-Term Memories (Project context & core knowledge)
        - Recent Memories (Created or updated recently)
        """
        active = self.get_active_memories()

        if query:
            q = query.lower().strip()
            active = [m for m in active if q in m.get("content", "").lower() or q in m.get("category", "").lower()]

        facts = []
        preferences = []
        long_term = []
        recent = []

        # Sort pinned items to the top
        active.sort(key=lambda x: (not x.get("is_pinned", False), x.get("updated_at", "")), reverse=True)

        for m in active:
            if not m.get("stars") or not m.get("importance_label"):
                imp_info = resolve_importance(m.get("importance", "PERMANENT"))
                m["stars"] = imp_info["stars"]
                m["importance_score"] = imp_info["score"]
                m["importance_label"] = imp_info["label"]

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

