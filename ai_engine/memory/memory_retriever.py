import re
from typing import List, Dict, Any, Tuple

# Comprehensive stop-word set to filter out non-informative grammatical words during relevance scoring
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by",
    "can", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing",
    "don't", "down", "during", "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself",
    "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is",
    "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself", "no",
    "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
    "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there",
    "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to",
    "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's",
    "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've",
    "your", "yours", "yourself", "yourselves", "tell", "give", "show", "know"
}

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

        # Filter out grammatical stop-words from prompt
        raw_prompt_words = set(re.findall(r'\w+', user_prompt.lower()))
        prompt_words = {w for w in raw_prompt_words if w not in STOP_WORDS}
        if not prompt_words:
            prompt_words = raw_prompt_words

        project_scored = []
        longterm_scored = []

        for m in active_memories:
            category = m.get("category", "")
            content = m.get("content", "")
            raw_content_words = set(re.findall(r'\w+', content.lower()))
            content_words = {w for w in raw_content_words if w not in STOP_WORDS and w not in ("fact", "note", "preference")}
            if not content_words:
                content_words = raw_content_words

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
                # Long-term user memories get selected if relevant or if explicitly inquiring about stored memory notes
                is_memory_recall_query = any(kw in user_prompt.lower() for kw in [
                    "ask you to remember", "asked you to remember",
                    "tell you to remember", "told you to remember",
                    "ask you to recall", "asked you to recall",
                    "what memories", "stored memories", "all memories"
                ])
                if overlap > 0 or is_memory_recall_query:
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
