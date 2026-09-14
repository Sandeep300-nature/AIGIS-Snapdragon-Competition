import os
from typing import List, Dict, Any, Optional

class ConversationManager:
    """
    Part 1 — Production Conversation Manager
    Maintains chronological conversation history per session with automatic trimming.
    Stores User and Assistant messages, preserving turn order and session state.
    """

    def __init__(self, max_messages: int = 16):
        self.max_messages = max_messages
        # In-memory session history store: session_id -> List[Dict[str, str]]
        self.sessions: Dict[str, List[Dict[str, str]]] = {}

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """Retrieves active conversation history for a given session."""
        return self.sessions.get(session_id, [])

    def add_message(self, session_id: str, role: str, content: str):
        """Appends a User or Assistant message to session history and trims old messages."""
        if not content or not content.strip():
            return

        if session_id not in self.sessions:
            self.sessions[session_id] = []

        clean_content = content.strip()
        # Clean grounded wrappers if present
        if clean_content.startswith("CRITICAL GROUNDING DIRECTIVES"):
            if "USER QUESTION:" in clean_content:
                parts = clean_content.split("USER QUESTION:")
                if len(parts) > 1:
                    clean_content = parts[1].split("\n\n")[0].strip()

        self.sessions[session_id].append({"role": role, "content": clean_content})

        # Trim old messages to fit context budget
        if len(self.sessions[session_id]) > self.max_messages:
            self.sessions[session_id] = self.sessions[session_id][-self.max_messages:]

    def prepare_rolling_history(self, history: List[Dict[str, str]], intent: str = "GENERAL_AI") -> List[Dict[str, str]]:
        """
        Formats recent conversation history for prompt construction.
        Keeps context budget balanced between live web facts and history.
        """
        if not history:
            return []

        cutoff = 6 if intent == "LIVE_WEB" else self.max_messages
        recent = history[-cutoff:] if len(history) > cutoff else history

        clean_history = []
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "").strip()
            if content:
                if content.startswith("CRITICAL GROUNDING DIRECTIVES"):
                    if "USER QUESTION:" in content:
                        parts = content.split("USER QUESTION:")
                        if len(parts) > 1:
                            content = parts[1].split("\n\n")[0].strip()
                clean_history.append({"role": role, "content": content})

        return clean_history

    def clear_session(self, session_id: str):
        """Clears memory for a specific session."""
        if session_id in self.sessions:
            self.sessions[session_id] = []
