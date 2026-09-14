from ast import Tuple
import re
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from .task_engine import TaskEngine, Task, TaskStatus
from .conversation_presence import ConversationPresenceLayer, PresenceRecommendation, SpeechMode, ObservablePresenceState

class ConversationMoment(str, Enum):
    INTERRUPTION = "INTERRUPTION"
    CORRECTION = "CORRECTION"
    CONTINUATION = "CONTINUATION"
    WAITING = "WAITING"
    COMPLETION = "COMPLETION"
    CANCELLATION = "CANCELLATION"
    FILLER_ONLY = "FILLER_ONLY"
    META = "META"
    GENERAL_TURN = "GENERAL_TURN"

FILLER_WORDS = {
    "um", "uh", "er", "err", "hmm", "hm", "like", "well", "you know", "ah", "ahh", "so", "basically"
}

META_QUESTION_PATTERNS = {
    "what_did_i_ask": [r'what did i ask', r'what was my question', r'what did i just ask'],
    "previous_answer": [r'what was your previous answer', r'what did you just say', r'repeat your last answer', r'summarize your last answer'],
    "current_topic": [r'who were we talking about', r'what are we talking about', r'what is the current topic']
}

class ConversationStateManager:
    """
    Conversation Intelligence Layer & State Manager
    Implements layered intent detection & conversation moment classification.
    Drives TaskEngine state transitions and injects conversational directives
    so the LLM personality layer generates 100% voice-consistent natural responses.
    """

    def __init__(self):
        self.states: Dict[str, Dict[str, Any]] = {}
        self.task_engine: TaskEngine = TaskEngine()
        self.presence_layer: ConversationPresenceLayer = ConversationPresenceLayer()

    def get_state(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.states:
            self.states[session_id] = {
                "session_id": session_id,
                "current_topic": "General Conversation",
                "last_user_question": "",
                "last_assistant_answer": "",
                "conversation_turns": 0,
                "active_entities": [],
                "active_task": None,
                "current_intent": "GENERAL_AI"
            }
        return self.states[session_id]

    def filter_filler_words(self, user_prompt: str) -> Tuple[str, bool]:
        """
        Strips pure filler words ('um', 'uh', 'like', 'hmm') from prompt.
        Returns tuple: (cleaned_prompt, is_pure_filler).
        """
        words = user_prompt.strip().split()
        cleaned_words = [w for w in words if w.lower().strip(".,!?") not in FILLER_WORDS]

        if not cleaned_words and words:
            return user_prompt, True
        
        cleaned_text = " ".join(cleaned_words)
        return (cleaned_text if cleaned_text else user_prompt), False

    def classify_moment(self, session_id: str, user_prompt: str) -> ConversationMoment:
        """
        Layered Intent & Conversation Moment Classifier.
        Identifies: FILLER_ONLY, META, INTERRUPTION, CORRECTION, CONTINUATION, WAITING, COMPLETION, CANCELLATION, GENERAL_TURN.
        """
        cleaned_prompt, is_filler = self.filter_filler_words(user_prompt)
        if is_filler:
            return ConversationMoment.FILLER_ONLY

        lowered = cleaned_prompt.lower().strip()

        # Meta question check
        for meta_type, patterns in META_QUESTION_PATTERNS.items():
            for p in patterns:
                if re.search(p, lowered):
                    return ConversationMoment.META

        # Cancellation Moment
        cancel_keywords = ["cancel", "cancel task", "nevermind", "forget it", "forget about it", "abort task"]
        if any(kw == lowered or lowered.startswith(kw) for kw in cancel_keywords):
            return ConversationMoment.CANCELLATION

        # Completion Moment
        completion_keywords = ["done", "finished", "that's all", "task complete", "we are done", "all set"]
        if any(kw == lowered or lowered.startswith(kw) for kw in completion_keywords):
            return ConversationMoment.COMPLETION

        # Waiting Moment (explicit pause / wait request)
        waiting_keywords = ["wait", "wait a minute", "hold on", "hang on", "stop for a second", "give me a sec", "pause"]
        if any(kw == lowered or lowered.startswith(kw) for kw in waiting_keywords):
            return ConversationMoment.WAITING

        # Continuation / Resumption Moment
        continuation_keywords = ["continue", "resume", "go ahead", "go back", "pick up where we left off", "keep going", "as we were saying"]
        if any(kw == lowered or lowered.startswith(kw) for kw in continuation_keywords):
            return ConversationMoment.CONTINUATION

        # Correction Moment
        correction_patterns = [r'^\s*no\b', r'^\s*actually\b', r'^\s*correction:', r'^\s*change that to\b', r'^\s*i meant\b', r'^\s*instead of\b']
        if any(re.search(pat, lowered) for pat in correction_patterns):
            return ConversationMoment.CORRECTION

        # Interruption / Side Question Moment (if there is an active task and user prompt introduces a tangent)
        active_t = self.task_engine.get_active_task(session_id)
        if active_t:
            side_keywords = ["by the way", "side question", "quick question", "before that", "unrelated"]
            if any(kw in lowered for kw in side_keywords):
                return ConversationMoment.INTERRUPTION

        return ConversationMoment.GENERAL_TURN

    def resolve_context(self, session_id: str, user_prompt: str) -> Tuple[str, Optional[str]]:
        """
        Task & Conversation Moment Context Resolution.
        Executes TaskEngine state transitions based on classified conversation moment,
        and injects conversational directives so the LLM personality layer generates natural responses.
        """
        state = self.get_state(session_id)
        cleaned_prompt, is_filler = self.filter_filler_words(user_prompt)
        moment = self.classify_moment(session_id, user_prompt)

        # 1. Meta Questions
        if moment == ConversationMoment.META:
            meta_type = self._detect_meta_type(lowered_prompt=cleaned_prompt.lower())
            if meta_type == "what_did_i_ask":
                last_q = state.get("last_user_question", "")
                return user_prompt, (f"You previously asked me: '{last_q}', sir." if last_q else "We haven't recorded any previous questions in this session yet, sir.")
            if meta_type == "previous_answer":
                last_ans = state.get("last_assistant_answer", "")
                return user_prompt, (f"My previous response was:\n\n{last_ans}" if last_ans else "I haven't provided a previous response in this session yet, sir.")
            if meta_type == "current_topic":
                active_t = self.task_engine.get_active_task(session_id)
                topic = active_t.name if active_t else state.get("current_topic", "General Conversation")
                entities = ", ".join(state.get("active_entities", []))
                return user_prompt, f"We are currently working on task: '{topic}' (Key entities: {entities}), sir."

        # 2. Filler-only turn
        if moment == ConversationMoment.FILLER_ONLY:
            directive_query = (
                f"{user_prompt}\n\n"
                f"[CONVERSATIONAL MOMENT: FILLER_PHRASE]\n"
                f"Directive: The user uttered a filler word without detailed intent. Respond naturally, politely, and concisely as FRIDAY asking how you can assist."
            )
            return directive_query, None

        # 3. Waiting / Pause Moment
        if moment == ConversationMoment.WAITING:
            paused_task = self.task_engine.set_active_task_waiting(session_id, reason="User requested pause")
            if not paused_task:
                paused_task = self.task_engine.pause_active_task(session_id, reason="User requested pause")
            
            task_name = paused_task.name if paused_task else state.get("current_topic", "current topic")
            directive_query = (
                f"{user_prompt}\n\n"
                f"[CONVERSATIONAL MOMENT: PAUSE_REQUEST]\n"
                f"Task State Changed: Task '{task_name}' is now PAUSED / WAITING_FOR_USER.\n"
                f"Directive: Respond naturally and loyalty-focused in FRIDAY's persona confirming that you are holding on/waiting for the user to proceed."
            )
            return directive_query, None

        # 4. Continuation / Resumption Moment
        if moment == ConversationMoment.CONTINUATION:
            resumed_task = self.task_engine.resume_task(session_id)
            if resumed_task:
                state["current_topic"] = resumed_task.name
                directive_query = (
                    f"{user_prompt}\n\n"
                    f"[CONVERSATIONAL MOMENT: TASK_RESUMPTION]\n"
                    f"Task State Changed: Resumed task '{resumed_task.name}' back to ACTIVE.\n"
                    f"Directive: Respond warmly in FRIDAY's persona confirming the task resumption, and seamlessly continue helping with task '{resumed_task.name}'."
                )
                return directive_query, None
            else:
                directive_query = (
                    f"{user_prompt}\n\n"
                    f"[CONVERSATIONAL MOMENT: CONTINUATION_NO_TASK]\n"
                    f"Directive: The user asked to continue, but there are no paused tasks. Acknowledge politely as FRIDAY and ask what they would like to work on."
                )
                return directive_query, None

        # 5. Cancellation Moment
        if moment == ConversationMoment.CANCELLATION:
            canceled_task = self.task_engine.cancel_active_task(session_id, reason="User requested cancellation")
            task_name = canceled_task.name if canceled_task else "current task"
            directive_query = (
                f"{user_prompt}\n\n"
                f"[CONVERSATIONAL MOMENT: TASK_CANCELLATION]\n"
                f"Task State Changed: Task '{task_name}' is now CANCELED.\n"
                f"Directive: Acknowledge the cancellation gracefully in FRIDAY's persona and ask how else you can assist."
            )
            return directive_query, None

        # 6. Completion Moment
        if moment == ConversationMoment.COMPLETION:
            completed_task = self.task_engine.complete_active_task(session_id, result_summary="User marked completed")
            task_name = completed_task.name if completed_task else "active task"
            directive_query = (
                f"{user_prompt}\n\n"
                f"[CONVERSATIONAL MOMENT: TASK_COMPLETION]\n"
                f"Task State Changed: Task '{task_name}' is now COMPLETED.\n"
                f"Directive: Offer a brief, loyal closing in FRIDAY's persona celebrating the task completion."
            )
            return directive_query, None

        # 7. Correction Moment
        if moment == ConversationMoment.CORRECTION:
            active_task = self.task_engine.get_active_task(session_id)
            if active_task:
                active_task.context["last_correction"] = user_prompt
            directive_query = (
                f"{user_prompt}\n\n"
                f"[CONVERSATIONAL MOMENT: CORRECTION]\n"
                f"Directive: The user is correcting previous input ('{user_prompt}'). Acknowledge the correction smoothly in FRIDAY's persona and adjust the response accordingly."
            )
            return directive_query, None

        # 8. Interruption / Side Question Moment
        if moment == ConversationMoment.INTERRUPTION:
            paused = self.task_engine.pause_active_task(session_id, reason="Side question / tangent")
            task_name = paused.name if paused else "main task"
            directive_query = (
                f"{user_prompt}\n\n"
                f"[CONVERSATIONAL MOMENT: SIDE_QUESTION_INTERRUPT]\n"
                f"Task State Changed: Primary task '{task_name}' is now PAUSED for this quick side query.\n"
                f"Directive: Answer the side question clearly as FRIDAY, noting naturally that the primary task is paused for resumption whenever ready."
            )
            return directive_query, None

        # 9. General Conversational Turn
        presence_rec = self.presence_layer.evaluate_presence(
            session_id=session_id,
            user_prompt=user_prompt,
            conversation_moment=moment.value
        )
        if presence_rec.is_greeting:
            directive_query = (
                f"{user_prompt}\n\n"
                f"[CONVERSATIONAL PRESENCE RECOMMENDATION]\n"
                f"Observable State: {presence_rec.presence_state.value} | Speech Mode: {presence_rec.speech_mode.value}\n"
                f"{presence_rec.recommendation_directive}"
            )
            return directive_query, None

        return user_prompt, None

    def update_state(self, session_id: str, user_prompt: str, ai_reply: str, intent: str = "GENERAL_AI"):
        """Updates conversation state and records turn step in active TaskEngine task."""
        state = self.get_state(session_id)
        state["conversation_turns"] += 1
        state["last_user_question"] = user_prompt.strip()
        state["last_assistant_answer"] = ai_reply.strip()
        state["current_intent"] = intent

        # Extract key entities
        entities = self._extract_entities(user_prompt + " " + ai_reply)
        for e in entities:
            if e not in state["active_entities"]:
                state["active_entities"].append(e)

        state["active_entities"] = state["active_entities"][-6:]

        moment = self.classify_moment(session_id, user_prompt)
        if moment not in (ConversationMoment.META, ConversationMoment.FILLER_ONLY, ConversationMoment.CANCELLATION):
            active_task = self.task_engine.get_active_task(session_id)
            if not active_task:
                cleaned_name, _ = self.filter_filler_words(user_prompt)
                active_task = self.task_engine.create_task(session_id, name=cleaned_name[:60], intent=intent)

            if active_task:
                active_task.add_step(user_prompt, ai_reply)
                state["active_task"] = active_task.to_dict()
                state["current_topic"] = active_task.name

    def _extract_entities(self, text: str) -> List[str]:
        candidates = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        stop_words = {"You", "The", "A", "An", "If", "What", "Who", "Why", "How", "Tell", "Where", "When", "Sir", "AIGIS", "FRIDAY", "LIVE_WEB", "VERIFIED"}
        valid = [c for c in candidates if c not in stop_words and len(c) > 2]
        return list(dict.fromkeys(valid))

    def _detect_meta_type(self, lowered_prompt: str) -> Optional[str]:
        for meta_type, patterns in META_QUESTION_PATTERNS.items():
            for p in patterns:
                if re.search(p, lowered_prompt):
                    return meta_type
        return None

    def get_state_summary_string(self, session_id: str) -> str:
        """Formats active conversation state and task stack for LLM prompt injection."""
        state = self.get_state(session_id)
        task_summary = self.task_engine.get_task_context_summary(session_id)

        if not state.get("last_user_question") and not task_summary:
            return ""

        entities_str = ", ".join(state.get("active_entities", [])) or "None"
        base_state = (
            f"ACTIVE CONVERSATION STATE:\n"
            f"- Current Topic: {state.get('current_topic')}\n"
            f"- Active Entities: {entities_str}\n"
            f"- Conversation Turns: {state.get('conversation_turns')}\n"
            f"- Last User Question: {state.get('last_user_question')}\n"
            f"- Last Assistant Answer Summary: {state.get('last_assistant_answer')[:120]}..."
        )

        if task_summary:
            return f"{base_state}\n\n{task_summary}"
        return base_state
