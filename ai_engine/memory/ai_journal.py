import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
JOURNAL_FILE = os.path.join(DATA_DIR, "ai_journal.json")

class AIJournal:
    """
    Part 7 — Internal AI Improvement Journal
    Stores system reflections, operational lessons learned, latency metrics, and performance notes.
    This journal is used for internal AI self-improvement and system telemetry only.
    """

    def __init__(self, journal_filepath: str = JOURNAL_FILE):
        self.filepath = journal_filepath
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        self.entries: List[Dict[str, Any]] = []
        self._load_journal()

    def _load_journal(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.entries = json.load(f)
            except Exception as e:
                print(f"[JOURNAL WARNING] Could not read {self.filepath}: {e}")
                self.entries = []

        if not self.entries:
            # Seed initial operational insights
            self.log_lesson("GROUNDING_STABILITY", "Strict prompt grounding directives successfully enforce verified Tavily facts for sports queries.")
            self.log_lesson("ARCHITECTURE_PORT", "Python AI Engine binds on port 8000; Java Spring Boot routes backend requests to port 8000.")

    def _save_journal(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[JOURNAL ERROR] Could not save {self.filepath}: {e}")

    def log_lesson(self, topic: str, lesson_text: str):
        """Logs an internal lesson learned or operational insight."""
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "topic": topic.upper().strip(),
            "lesson": lesson_text.strip()
        }
        self.entries.append(entry)
        self._save_memory = self._save_journal()

    def get_recent_lessons(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Returns recent internal system insights."""
        return self.entries[-limit:]
