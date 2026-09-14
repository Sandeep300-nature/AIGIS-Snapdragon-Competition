from typing import Dict, Any, Optional
from .conversation_state import ConversationStateManager, ConversationMoment
from .conversation_manager import ConversationManager

class ConversationSynchronizer:
    """
    Conversation Synchronization Engine
    Handles realtime turn synchronization across 5 explicit lifecycle events:
    1. speech_started — Physical speech activity detected (audio muted, no instant task pause)
    2. user_turn_committed — Meaningful user turn available to conversation layer
    3. assistant_response_started — Model begins speech/text response
    4. assistant_response_interrupted — User barged in mid-response (truncates history, no false completes)
    5. assistant_response_completed — Complete response turn delivered

    Guarantees interrupted assistant responses are truncated to exact spoken audio duration,
    and TaskEngine state transitions occur strictly when ConversationStateManager classifies a genuine task interruption.
    """

    def __init__(self, state_manager: ConversationStateManager, conv_manager: ConversationManager):
        self.state_manager = state_manager
        self.conv_manager = conv_manager
        self.active_assistant_turns: Dict[str, Dict[str, Any]] = {}

    def handle_speech_started(self, session_id: str) -> Dict[str, Any]:
        """
        Physical speech activity detected.
        Signals local playback mute; does NOT transition TaskEngine state to PAUSED.
        """
        return {
            "session_id": session_id,
            "event": "speech_started",
            "action": "mute_local_playback",
            "task_state_changed": False
        }

    def handle_assistant_response_started(self, session_id: str, response_id: str, item_id: str):
        """Records start of assistant response item."""
        self.active_assistant_turns[session_id] = {
            "response_id": response_id,
            "item_id": item_id,
            "partial_content": "",
            "interrupted": False
        }

    def handle_assistant_response_interrupted(self, session_id: str, audio_end_ms: int, truncated_text: str) -> Dict[str, Any]:
        """
        Handles user barge-in mid-assistant turn.
        Truncates history to exact spoken text; ensures incomplete speech is NOT stored as a completed turn.
        """
        turn_data = self.active_assistant_turns.get(session_id, {})
        turn_data["interrupted"] = True
        turn_data["truncated_text"] = truncated_text
        turn_data["audio_end_ms"] = audio_end_ms

        return {
            "session_id": session_id,
            "event": "assistant_response_interrupted",
            "audio_end_ms": audio_end_ms,
            "truncated_text": truncated_text,
            "stored_as_completed": False
        }

    def handle_user_turn_committed(self, session_id: str, user_prompt: str) -> Dict[str, Any]:
        """
        Meaningful user turn available to conversation layer.
        Passes prompt to ConversationStateManager to evaluate semantic moment & task engine state transitions.
        """
        # Resolve context and classify moment (CORRECTION, WAITING, CONTINUATION, SIDE_QUESTION, etc.)
        resolved_prompt, meta_reply = self.state_manager.resolve_context(session_id, user_prompt)
        moment = self.state_manager.classify_moment(session_id, user_prompt)

        active_task = self.state_manager.task_engine.get_active_task(session_id)
        task_status = active_task.status.value if active_task else "NONE"

        return {
            "session_id": session_id,
            "event": "user_turn_committed",
            "moment": moment.value,
            "task_status": task_status,
            "meta_reply": meta_reply
        }

    def handle_assistant_response_completed(self, session_id: str, user_prompt: str, final_reply: str):
        """Records full turn in state manager and conversation manager upon completion."""
        turn_data = self.active_assistant_turns.get(session_id)
        if turn_data and turn_data.get("interrupted"):
            # Use truncated text instead of full reply
            final_reply = turn_data.get("truncated_text", final_reply)

        self.state_manager.update_state(session_id, user_prompt, final_reply)
        self.conv_manager.add_message(session_id, "user", user_prompt)
        self.conv_manager.add_message(session_id, "assistant", final_reply)
        self.active_assistant_turns.pop(session_id, None)
