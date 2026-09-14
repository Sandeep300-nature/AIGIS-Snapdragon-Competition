import re
from typing import List, Dict, Any, Tuple

class MemoryRetriever:
    """
    Part 5 — Memory Retriever
    Retrieves the most relevant memories for the current prompt using relevance scoring.
    Injects only matching memories rather than dumping the whole database.
    """

    def __init__(self, memory_store):
        self.memory_store = memory_store

    def retrieve_relevant_memories(self, user_prompt: str, top_k: int = 3) -> Tuple[str, str]:
        """
        Calculates relevance score between prompt and active memories.
        Returns tuple: (formatted_project_context_str, formatted_long_term_memory_str).
        """
        active_memories = self.memory_store.get_active_memories()
        if not active_memories:
            return "", ""

        prompt_words = set(re.findall(r'\w+', user_prompt.lower()))

        project_scored = []
        longterm_scored = []

        for m in active_memories:
            category = m.get("category", "")
            content = m.get("content", "")
            content_words = set(re.findall(r'\w+', content.lower()))

            # Keyword overlap score with root matching for words of length >= 4
            exact_overlap = len(prompt_words.intersection(content_words))
            root_overlap = sum(
                1 for pw in prompt_words
                if len(pw) >= 4 and any(
                    (pw in cw or cw in pw) and cw != pw for cw in content_words if len(cw) >= 4
                )
            )
            overlap = exact_overlap + root_overlap

            # Importance bonus
            importance = m.get("importance", 3)
            if isinstance(importance, int):
                bonus = 2 if importance >= 4 else (1 if importance == 3 else 0)
            else:
                imp_str = str(importance).upper()
                bonus = 2 if imp_str in ["HIGH", "PERMANENT", "LONG_TERM"] else (1 if imp_str in ["MEDIUM", "PROJECT"] else 0)

            score = overlap + bonus


            if category == "PROJECT_CONTEXT":
                # Project context memories get selected if relevant or if asking about architecture/specs
                if overlap > 0 or any(kw in user_prompt.lower() for kw in ["architecture", "aigis", "backend", "python", "tavily", "provider", "spring boot"]):
                    project_scored.append((score, content))
            else:
                if overlap > 0:
                    longterm_scored.append((score, content))

        # Sort by score descending
        project_scored.sort(key=lambda x: x[0], reverse=True)
        longterm_scored.sort(key=lambda x: x[0], reverse=True)

        top_project = [item[1] for item in project_scored[:top_k]]
        top_longterm = [item[1] for item in longterm_scored[:top_k]]

        # Format output strings
        project_context_str = ""
        if top_project:
            project_context_str = "RELEVANT PROJECT CONTEXT:\n" + "\n".join([f"- {fact}" for fact in top_project])

        long_term_memory_str = ""
        if top_longterm:
            long_term_memory_str = "RELEVANT LONG-TERM MEMORY:\n" + "\n".join([f"- {mem}" for mem in top_longterm])

        return project_context_str, long_term_memory_str
