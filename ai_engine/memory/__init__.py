"""
AIGIS Intelligent Memory & Conversation State Engine Package
Modular memory architecture containing:
- ConversationManager: Rolling context window & history persistence per session
- ConversationStateManager: Active state tracking, follow-up detection & meta-question resolution
- PromptBuilder: Priority-ranked prompt construction (System -> State -> History -> LongTerm -> RAG -> LIVE_WEB -> User)
- LongTermMemoryStore: Structured JSON store for project context, user preferences, news & facts
- MemoryExtractor: Automatic post-turn memory extraction & secret filtering
- MemoryRetriever: Semantic & keyword relevance filtering
- AIJournal: Internal AI system learning & performance journal
"""

from .conversation_manager import ConversationManager
from .conversation_state import ConversationStateManager
from .task_engine import TaskEngine, Task, TaskStatus
from .conversation_presence import (
    ConversationPresenceLayer,
    PresenceRecommendation,
    SpeechMode,
    ObservablePresenceState,
    TurnCompletionDetector
)
from .conversation_sync import ConversationSynchronizer
from .prompt_builder import PromptBuilder
from .local_memory_vault import LocalMemoryVault
from .long_term_memory import LongTermMemoryStore
from .memory_extractor import MemoryExtractor
from .memory_retriever import MemoryRetriever
from .ai_journal import AIJournal

__all__ = [
    "LocalMemoryVault",
    "ConversationManager",
    "ConversationStateManager",
    "TaskEngine",
    "Task",
    "TaskStatus",
    "ConversationPresenceLayer",
    "PresenceRecommendation",
    "SpeechMode",
    "ObservablePresenceState",
    "TurnCompletionDetector",
    "ConversationSynchronizer",
    "PromptBuilder",
    "LongTermMemoryStore",
    "MemoryExtractor",
    "MemoryRetriever",
    "AIJournal"
]

