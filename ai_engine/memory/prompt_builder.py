from typing import List, Dict, Any, Optional

class PromptBuilder:
    """
    Production Layered Prompt Builder & Context Assembly Engine.
    Structures prompt construction into independent, single-responsibility layer methods:
    1. System Rules Layer — Immutable behavioral / safety rules
    2. Personality Layer — Conversational style & persona directives
    3. Conversation Moment Layer — Turn moment directives (interruption, correction, etc.)
    4. Active Task Layer — Active task & conversation state context
    5. Memory Layer — Retrieved project context, long-term memory, and RAG document indices
    6. Desktop Context Layer — Resolved desktop & system telemetry context
    7. History Layer — Rolling turn history
    8. User Message Layer — Grounded user prompt & real-time facts

    Maintains 100% backward compatibility and exact output parity for prompt assembly.
    Does NOT perform intent classification, memory retrieval, or state mutation.
    """

    # --- INDEPENDENT LAYER BUILDER METHODS ---

    @staticmethod
    def build_system_rules_layer(system_instruction: str) -> Optional[Dict[str, str]]:
        """Layer 1: Immutable Behavioral & System Safety Rules."""
        if not system_instruction:
            return None
        return {"role": "system", "content": system_instruction}

    @staticmethod
    def build_personality_layer(personality_directives: Optional[str] = None) -> Optional[Dict[str, str]]:
        """Layer 2: Aegis Conversational Personality & Speaking Style Directives."""
        if not personality_directives:
            return None
        return {"role": "system", "content": f"[PERSONALITY DIRECTIVES]\n{personality_directives}"}

    @staticmethod
    def build_conversation_moment_layer(moment_directives: Optional[str] = None) -> Optional[Dict[str, str]]:
        """Layer 3: Conversation Moment Directives (interruption, correction, continuation, waiting, etc.)."""
        if not moment_directives:
            return None
        return {"role": "system", "content": f"[CONVERSATIONAL MOMENT DIRECTIVES]\n{moment_directives}"}

    @staticmethod
    def build_active_task_layer(state_summary: str) -> Optional[Dict[str, str]]:
        """Layer 4: Current Task State & Resumable Task Context."""
        if not state_summary:
            return None
        return {"role": "system", "content": f"[CONVERSATION CONTEXT]\n{state_summary}"}

    @staticmethod
    def build_memory_layer(
        proj_context_str: str = "",
        long_memory_str: str = "",
        rag_context_str: str = ""
    ) -> Dict[str, Optional[Dict[str, str]]]:
        """
        Layer 5: Memory Layer — Already-retrieved project context, long-term memory, and RAG document indices.
        Returns a dictionary of memory layer message blocks.
        """
        proj_msg = {"role": "system", "content": proj_context_str} if proj_context_str else None
        long_msg = {"role": "system", "content": long_memory_str} if long_memory_str else None
        rag_msg = {"role": "system", "content": rag_context_str} if rag_context_str else None

        return {
            "project_context": proj_msg,
            "long_term_memory": long_msg,
            "rag_documents": rag_msg
        }

    @staticmethod
    def build_desktop_context_layer(desktop_context_str: Optional[str] = None) -> Optional[Dict[str, str]]:
        """Layer 6: Already-resolved Desktop & System Context (Telemetry/Desktop state)."""
        if not desktop_context_str:
            return None
        return {"role": "system", "content": f"[DESKTOP CONTEXT]\n{desktop_context_str}"}

    @staticmethod
    def build_history_layer(rolling_history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Layer 7: Rolling Conversation Turn History."""
        history_messages = []
        if rolling_history:
            for h in rolling_history:
                history_messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        return history_messages

    @staticmethod
    def build_user_message_layer(
        user_prompt: str,
        web_context_str: str = "",
        current_time_str: str = "",
        current_date_str: str = ""
    ) -> Dict[str, str]:
        """Layer 8: Current User Request & Grounding Directives."""
        if web_context_str:
            grounded_user_content = (
                f"CRITICAL GROUNDING DIRECTIVES:\n"
                f"1. You MUST answer exclusively using the VERIFIED REAL-TIME FACTS below. Do NOT answer from your internal memory.\n"
                f"2. IGNORE any previous assistant responses in past turns if they conflict with the facts below.\n"
                f"3. For 'latest', 'current', or 'recent' questions, identify the MOST RECENT year, quote, or date mentioned in the facts.\n"
                f"4. For 'first', 'inaugural', or 'historic' questions, identify the FIRST or original winner mentioned in the facts.\n"
                f"5. NEVER recommend external websites like 'check Capital.com' or 'visit Investing.com' unless the user specifically asks for sources or alternatives.\n"
                f"6. If a STALE DATA WARNING is present in the facts below, state clearly: \"I couldn't find a recent live quote. The newest available data is from [Date].\" Do NOT present old data as current.\n"
                f"7. SYSTEM SAFETY RULE: NEVER fabricate, estimate, or simulate personal data (health, heart rate, blood pressure, bank balance, medical history, etc.). If information is unavailable, state clearly that you don't have access to it.\n"
                f"8. SELF-AWARENESS RULE: Always state the source of your information (e.g. \"According to today's news...\", \"Based on search results...\").\n\n"
                f"{web_context_str}\n\n"
                f"USER QUESTION: {user_prompt}\n\n"
                f"Now answer as AIGIS/FRIDAY (addressing the user as 'sir', witty, sharp, concise, and loyal)."
            )
        else:
            grounded_user_content = (
                f"USER QUESTION: {user_prompt}\n\n"
                f"CURRENT SYSTEM TIME: {current_time_str} on {current_date_str}\n\n"
                f"SAFETY & SELF-AWARENESS RULES:\n"
                f"- NEVER fabricate or estimate personal data (heart rate, blood pressure, bank balance, sleep, calories, medical history, etc.).\n"
                f"- If data is unavailable, state: \"I don't currently have access to that information, sir.\"\n"
                f"- ALWAYS cite your source when reporting retrieved data (e.g. \"According to your live telemetry...\", \"Based on your reminder database...\").\n\n"
                f"Answer as AIGIS/FRIDAY."
            )
        return {"role": "user", "content": grounded_user_content}

    # --- PRIMARY PROMPT ASSEMBLY ENTRY POINT ---

    @classmethod
    def build_prompt_messages(
        cls,
        system_instruction: str,
        state_summary: str,
        proj_context_str: str,
        long_memory_str: str,
        rolling_history: List[Dict[str, str]],
        rag_context_str: str,
        web_context_str: str,
        user_prompt: str,
        current_time_str: str,
        current_date_str: str,
        personality_directives: Optional[str] = None,
        moment_directives: Optional[str] = None,
        desktop_context_str: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Assembles all memory and prompt layers into structured LLM chat messages list.
        Maintains 100% backward compatibility and exact output sequence parity.
        """
        messages: List[Dict[str, str]] = []

        # Layer 1: System Rules
        sys_msg = cls.build_system_rules_layer(system_instruction)
        if sys_msg:
            messages.append(sys_msg)

        # Layer 2: Personality Layer
        pers_msg = cls.build_personality_layer(personality_directives)
        if pers_msg:
            messages.append(pers_msg)

        # Layer 3: Conversation Moment Layer
        moment_msg = cls.build_conversation_moment_layer(moment_directives)
        if moment_msg:
            messages.append(moment_msg)

        # Layer 4: Active Task & State Summary
        task_msg = cls.build_active_task_layer(state_summary)
        if task_msg:
            messages.append(task_msg)

        # Layer 5: Memory Layers (Project Context, Long-Term Memory)
        mem_layers = cls.build_memory_layer(
            proj_context_str=proj_context_str,
            long_memory_str=long_memory_str,
            rag_context_str=rag_context_str
        )
        if mem_layers.get("project_context"):
            messages.append(mem_layers["project_context"])
        if mem_layers.get("long_term_memory"):
            messages.append(mem_layers["long_term_memory"])

        # Layer 7: Recent Conversation History
        hist_msgs = cls.build_history_layer(rolling_history)
        messages.extend(hist_msgs)

        # Layer 5 (cont.): RAG Document Index
        if mem_layers.get("rag_documents"):
            messages.append(mem_layers["rag_documents"])

        # Layer 6: Desktop Context Layer
        desk_msg = cls.build_desktop_context_layer(desktop_context_str)
        if desk_msg:
            messages.append(desk_msg)

        # Layer 8: User Message & Grounding Directives
        user_msg = cls.build_user_message_layer(
            user_prompt=user_prompt,
            web_context_str=web_context_str,
            current_time_str=current_time_str,
            current_date_str=current_date_str
        )
        messages.append(user_msg)

        return messages
