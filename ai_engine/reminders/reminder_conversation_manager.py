from typing import Dict, Any, Tuple, Optional
from .priority_engine import PriorityClass, PriorityEngine

class ReminderConversationManager:
    """
    Reminder Conversation Manager:
    Single Responsibility: Decides HOW reminders are presented based on
    PriorityClass, Assistant Speaking State, and Conversation Flow.
    """

    @classmethod
    def determine_presentation_mode(
        cls,
        priority_class: PriorityClass,
        is_speaking: bool = False,
        seconds_remaining: float = 0.0
    ) -> str:
        """
        Returns delivery strategy: 'INTERRUPT_NOW' | 'WAIT_SENTENCE' | 'WAIT_RESPONSE_END' | 'VISUAL_ONLY'
        """
        if priority_class == PriorityClass.CRITICAL:
            return "INTERRUPT_NOW" if is_speaking else "INTERRUPT_NOW"
        elif priority_class == PriorityClass.IMPORTANT:
            return "WAIT_SENTENCE" if is_speaking else "INTERRUPT_NOW"
        elif priority_class == PriorityClass.URGENT:
            return "WAIT_RESPONSE_END" if is_speaking else "INTERRUPT_NOW"
        else: # ROUTINE
            return "VISUAL_ONLY"

    @classmethod
    def generate_polite_interruption_phrase(cls, title: str, milestone_seconds: int, priority_class: PriorityClass) -> str:
        t = title.strip()
        if milestone_seconds >= 600:
            return f"Sir, your {t} is scheduled in 10 minutes."
        elif milestone_seconds >= 300:
            return f"Excuse me, sir. Your {t} starts in 5 minutes."
        elif milestone_seconds >= 60:
            return f"Pardon the interruption, sir. Your {t} is in 1 minute."
        elif milestone_seconds == 30:
            return f"Excuse me, sir. Your {t} begins in 30 seconds."
        else:
            if priority_class == PriorityClass.CRITICAL:
                return f"Sir, urgent alert: Your {t} is starting now."
            return f"Sir, your {t} is scheduled for now."

    @classmethod
    def format_interrupted_continuation(cls, original_response: str, reminder_phrase: str) -> str:
        """
        Seamlessly weaves the polite interruption into the response and appends resumption:
        'Before I continue, <reminder_phrase> As I was saying, <original_response>'
        """
        clean_phrase = reminder_phrase.strip()
        clean_original = original_response.strip()

        if not clean_original:
            return clean_phrase

        return f"Pardon the interruption, sir. {clean_phrase}\n\nAs I was saying, {clean_original}"
