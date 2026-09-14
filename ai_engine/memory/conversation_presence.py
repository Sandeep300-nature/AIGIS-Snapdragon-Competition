from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

class SpeechMode(str, Enum):
    SPEAK_BRIEF = "SPEAK_BRIEF"
    ELABORATE = "ELABORATE"
    WAIT = "WAIT"
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"

class ObservablePresenceState(str, Enum):
    LISTENING = "LISTENING"
    AGREEING = "AGREEING"
    CLARIFYING = "CLARIFYING"
    CORRECTING = "CORRECTING"

@dataclass
class PresenceRecommendation:
    speech_mode: SpeechMode
    presence_state: ObservablePresenceState
    is_greeting: bool
    turn_complete: bool  # Hook for TurnCompletionDetector
    recommendation_directive: str

class TurnCompletionDetector:
    """
    Architectural hook for evaluating whether a user turn is complete or pausing mid-utterance.
    Evaluates trailing punctuation, filler word signals, and utterance structure.
    """
    @staticmethod
    def is_turn_complete(user_prompt: str, has_filler_trail: bool = False) -> bool:
        if has_filler_trail:
            return False
        trimmed = user_prompt.strip()
        if not trimmed:
            return False
        # If user ends with trailing ellipsis or hesitation words, turn may be incomplete
        if trimmed.endswith("...") or trimmed.endswith("—") or trimmed.endswith("-"):
            return False
        return True

class ConversationPresenceLayer:
    """
    Conversation Presence Layer — Pure Decision Maker
    Recommends response pacing, observable presence state (LISTENING, AGREEING, CLARIFYING, CORRECTING),
    and speech mode (SPEAK_BRIEF, ELABORATE, WAIT, ACKNOWLEDGEMENT) based on intent and conversational context.
    Does NOT control language generation; feeds recommendations to the LLM personality layer.
    """

    def __init__(self):
        self.turn_completion_detector = TurnCompletionDetector()

    def evaluate_presence(
        self,
        session_id: str,
        user_prompt: str,
        conversation_moment: str,
        active_task_intent: Optional[str] = None
    ) -> PresenceRecommendation:
        lowered = user_prompt.lower().strip()
        words = lowered.split()

        # Check turn completion
        has_filler_trail = words[-1] in ("um", "uh", "hmm", "like") if words else False
        turn_complete = self.turn_completion_detector.is_turn_complete(user_prompt, has_filler_trail)

        # Minimal greeting check based on context
        is_greeting = lowered in ("hello", "hi", "hey", "good morning", "good evening", "greetings")

        # Determine Speech Mode & Presence State by context and intent
        if conversation_moment in ("WAITING", "PAUSE_REQUEST"):
            speech_mode = SpeechMode.WAIT
            presence_state = ObservablePresenceState.LISTENING
            rec_directive = "RECOMMENDATION: User requested pause. Maintain listening presence and confirm pause briefly in persona."
        elif conversation_moment == "CORRECTION":
            speech_mode = SpeechMode.SPEAK_BRIEF
            presence_state = ObservablePresenceState.CORRECTING
            rec_directive = "RECOMMENDATION: User provided correction. Maintain correcting presence, acknowledge update naturally."
        elif conversation_moment in ("CONTINUATION", "TASK_RESUMPTION"):
            speech_mode = SpeechMode.SPEAK_BRIEF
            presence_state = ObservablePresenceState.AGREEING
            rec_directive = "RECOMMENDATION: Resuming active task. Maintain agreeing/partner presence and pick up task."
        elif is_greeting:
            speech_mode = SpeechMode.SPEAK_BRIEF
            presence_state = ObservablePresenceState.LISTENING
            rec_directive = "RECOMMENDATION: Minimal greeting. Respond with a warm, 1-sentence greeting without system status or time dumps unless asked."
        elif any(kw in lowered for kw in ("explain", "elaborate", "details", "why", "how does", "tell me more", "describe")):
            speech_mode = SpeechMode.ELABORATE
            presence_state = ObservablePresenceState.CLARIFYING
            rec_directive = "RECOMMENDATION: User requested detail. Provide an informative, well-structured explanation."
        else:
            # Default conversational restraint: brief, natural human partner response
            speech_mode = SpeechMode.SPEAK_BRIEF
            presence_state = ObservablePresenceState.LISTENING
            rec_directive = "RECOMMENDATION: Default restraint. Keep response brief, natural, and punchy (1-2 sentences) like a human partner."

        return PresenceRecommendation(
            speech_mode=speech_mode,
            presence_state=presence_state,
            is_greeting=is_greeting,
            turn_complete=turn_complete,
            recommendation_directive=rec_directive
        )
