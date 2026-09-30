"""
AIGIS Speech Sanitization & Normalization Layer.

This module provides dedicated, separate speech-only representations of AI responses
prior to Text-to-Speech (TTS) synthesis, as well as conservative Speech-to-Text (STT)
normalization.

Key Principles:
1. The original AI response object must remain completely untouched for UI display.
2. The speech-only string converts visual formatting into understandable spoken structure
   while preventing formatting symbols or punctuation names from being spoken literally.
3. Structured reports, telemetry, and lists maintain sentence boundaries and pauses
   rather than collapsing into a flat stream of words.
4. Technical terms preserve semantic meaning:
   - AIGIS / A-I-G-I-S / A I G I S -> Aigis
   - GenieX -> Genie X
   - Qwen3-4B -> Qwen 3 4B
   - x86_64 -> x86-64
   - on-device -> on device
   - real-time -> real time
   - built-in -> built in
5. Brackets, braces, parentheses, backticks, asterisks, hash signs, etc. are stripped/rephrased
   so TTS does not speak "opening bracket", "closing parenthesis", "asterisk", "hyphen", etc.
"""

import re
from typing import Optional


# Emojis regex pattern
EMOJI_PATTERN = re.compile(
    r"[\U0001F300-\U0001F9FF"
    r"\U0001FA00-\U0001FAFF"
    r"\U00002600-\U000026FF"
    r"\U00002700-\U000027BF"
    r"\U0000FE00-\U0000FE0F"
    r"\U0001F1E0-\U0001F1FF]+",
    flags=re.UNICODE
)


def sanitize_speech_text(text: Optional[str]) -> str:
    """
    Transforms rich response text into a natural speech-only string for TTS.
    Does NOT mutate the original text.
    
    Converts visual formatting (markdown, bullets, telemetry, dashes, parentheticals)
    into natural spoken sentences and cadence without speaking symbol names aloud.
    """
    if not text:
        return ""

    s = str(text)

    # 1. Remove decorative / status emojis so TTS does not read emoji descriptions
    s = EMOJI_PATTERN.sub(" ", s)

    # 2. Markdown Code Blocks: remove ```language / ``` markers, keep readable code content
    s = re.sub(r"```[a-zA-Z0-9_-]*\n?([\s\S]*?)```", r"\1", s)

    # 3. Markdown Inline Code: `code` -> code (prevent saying "backtick")
    s = re.sub(r"`([^`]+)`", r"\1", s)

    # 4. Markdown Images & Links: [text](url) -> text (strip URL so TTS does not read http-colon-slash)
    s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    # Strip standalone URLs
    s = re.sub(r"https?://\S+", "web link", s)

    # 5. Markdown Headers: # Heading -> Heading (prevent saying "hashtag" or "hash")
    s = re.sub(r"(?m)^\s*#{1,6}\s+(.+)$", r"\1", s)

    # 6. Markdown Blockquotes: > quote -> quote
    s = re.sub(r"(?m)^\s*>\s*(.+)$", r"\1", s)

    # 7. Decorative divider lines (---, ***, ===, ___) -> remove cleanly so they do not produce stray commas
    s = re.sub(r"(?m)^[\s\-_=*]{3,}\s*$", "", s)

    # 8. Markdown Bold / Italics / Strikethrough (prevent saying "asterisk", "star", "underscore")
    s = re.sub(r"\*{3}([^*]+)\*{3}", r"\1", s)
    s = re.sub(r"_{3}([^_]+)_{3}", r"\1", s)
    s = re.sub(r"\*{2}([^*]+)\*{2}", r"\1", s)
    s = re.sub(r"_{2}([^_]+)_{2}", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", s)
    s = re.sub(r"~~([^~]+)~~", r"\1", s)

    # 9. Table borders / cell separators (|) -> natural pause
    s = re.sub(r"\|", ", ", s)

    # 10. Trademarks & Registered symbols: Intel(R) Core(TM) -> Intel Core
    s = re.sub(r"\(\s*[rR]\s*\)", "", s)
    s = re.sub(r"\(\s*[tT][mM]\s*\)", "", s)
    s = re.sub(r"\(\s*[cC]\s*\)", "", s)
    s = re.sub(r"[®™©]", "", s)

    # 11. Technical Terms & Architecture Identifiers (processed BEFORE general symbol normalization)
    # x86_64 / x86_32 -> x86-64 / x86-32
    s = re.sub(r"\bx86_64\b", "x86-64", s, flags=re.IGNORECASE)
    s = re.sub(r"\bx86_32\b", "x86-32", s, flags=re.IGNORECASE)

    # AIGIS variants -> Aigis
    s = re.sub(r"\bA\s*-\s*I\s*-\s*G\s*-\s*I\s*-\s*S\b", "Aigis", s, flags=re.IGNORECASE)
    s = re.sub(r"\bA\s+I\s+G\s+I\s+S\b", "Aigis", s, flags=re.IGNORECASE)
    s = re.sub(r"(?:\bA\.I\.G\.I\.S\.|\bA\.I\.G\.I\.S\b)", "Aigis", s, flags=re.IGNORECASE)
    s = re.sub(r"\bAIGIS\b", "Aigis", s)

    # GenieX -> Genie X
    s = re.sub(r"\bGenieX\b", "Genie X", s)

    # Qwen3-4B -> Qwen 3 4B, Qwen3 -> Qwen 3
    s = re.sub(r"\bQwen3-4B\b", "Qwen 3 4B", s, flags=re.IGNORECASE)
    s = re.sub(r"\bQwen3\b", "Qwen 3", s, flags=re.IGNORECASE)

    # Technical word hyphens: on-device -> on device, real-time -> real time, built-in -> built in
    # (Matches alpha words only, preserving numeric technical identifiers like x86-64)
    s = re.sub(r"\b([a-zA-Z]+)-([a-zA-Z]+)\b", r"\1 \2", s)

    # 12. Em-dashes and En-dashes -> natural comma pause
    s = re.sub(r"\s*[—–]\s*", ", ", s)

    # 13. Parentheses, Braces, and Brackets Handling:
    # Empty brackets/parentheses
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\[\s*\]", "", s)
    s = re.sub(r"\{\s*\}", "", s)

    # Brackets and Braces: [local] -> local, {data} -> data
    s = re.sub(r"\[([^\]]+)\]", r" \1 ", s)
    s = re.sub(r"\{([^}]+)\}", r" \1 ", s)

    # Specific parenthetical clauses:
    # (running on x64 development machine) -> . The system is running on an x64 development machine
    s = re.sub(
        r"\(\s*running on\s+(?:an?\s+)?x64\s+development\s+machine\s*\)",
        ". The system is running on an x64 development machine",
        s,
        flags=re.IGNORECASE
    )
    s = re.sub(r"\(\s*running on\s+([^)]+)\)", r", running on \1", s, flags=re.IGNORECASE)

    # General parentheses:
    # If preceded by a linking verb or preposition, omit leading comma: e.g. "settings are (private)" -> "settings are private"
    # Otherwise, convert opening parenthesis to a natural spoken pause: "(12 threads)" -> ", 12 threads"
    def _replace_parens(match: re.Match) -> str:
        pre = match.group(1)
        inner = match.group(2).strip()
        last_word = pre.rstrip().split()[-1].lower() if pre.rstrip().split() else ""
        linking_words = {
            "is", "are", "was", "were", "be", "been", "being",
            "to", "from", "in", "of", "for", "with", "as", "and", "or"
        }
        # Multi-token clauses, explanations, or numbers/measurements (e.g. "(12 threads)", "(x86_64 CPU)")
        # get a natural spoken pause comma. Single identifiers or function args (e.g. "print(x)", "(private)") do not.
        is_clause_or_measurement = (len(inner.split()) > 1) or bool(re.match(r"^\d+", inner))
        if is_clause_or_measurement and (last_word not in linking_words):
            return f"{pre}, {inner}"
        return f"{pre} {inner}"

    s = re.sub(r"(\w+)\s*\(([^)]+)\)", _replace_parens, s)
    s = re.sub(r"\(([^)]+)\)", r" \1 ", s)
    # Strip any remaining stray brackets/braces/parentheses
    s = re.sub(r"[{}\[\]()]", " ", s)

    # 14. Structured Line-by-Line Formatting (Reports, Telemetry, Bullet Lists)
    lines = s.split("\n")
    processed_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect and convert list bullets: '• item', '- item', '* item'
        is_bullet = bool(re.match(r"^[-*•›»]\s*", stripped))
        stripped = re.sub(r"^[-*•›»]\s*", "", stripped).strip()

        # Detect and convert numbered lists: '1. item' -> '1, item'
        is_numbered = bool(re.match(r"^\d+\.\s*", stripped))
        stripped = re.sub(r"^(\d+)\.\s*", r"\1, ", stripped).strip()

        # If intro / heading line ends with a colon (e.g. 'Workstation Hardware Telemetry, sir:'),
        # convert colon to period for natural pause
        if stripped.endswith(":"):
            stripped = stripped[:-1].rstrip() + "."

        # Ensure bullet and numbered list items end with terminal sentence punctuation
        # to prevent TTS engines from flattening reports into one continuous run-on sentence
        if (is_bullet or is_numbered) and not stripped.endswith((".", "!", "?")):
            stripped += "."

        processed_lines.append(stripped)

    s = "\n".join(processed_lines)

    # 15. Remaining awkward notation / punctuation symbols
    s = re.sub(r"[~^\\<>]", " ", s)
    s = re.sub(r"[*#_]", " ", s)

    # Normalize repeated punctuation: "!!!" -> "!", "???" -> "?", "...." -> "..."
    s = re.sub(r"!{2,}", "!", s)
    s = re.sub(r"\?{2,}", "?", s)
    s = re.sub(r"\.{4,}", "...", s)

    # 16. Whitespace and comma/punctuation cleanup
    # Snap punctuation back if there is space before it (e.g. "task ." -> "task.")
    s = re.sub(r"\s+([.,!?;:])", r"\1", s)
    # Remove multiple commas like ", ," or ", , "
    s = re.sub(r",\s*,+", ", ", s)
    # Remove comma right before another punctuation mark
    s = re.sub(r"\s*,\s*\.", ".", s)
    s = re.sub(r"\s*\.\s*\.", ".", s)
    s = re.sub(r"\s*,\s*!", "!", s)
    s = re.sub(r"\s*,\s*\?", "?", s)
    # Clean leading commas on lines
    s = re.sub(r"(?m)^\s*,\s*", "", s)
    # Collapse multiple whitespace characters into single space
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)

    return s.strip()


def normalize_stt_transcript(text: Optional[str]) -> str:
    """
    Conservative Speech-to-Text normalization.
    Cleans brand recognition and accidental repeated whitespace without aggressive autocorrect.
    Preserves the user's intended wording.
    """
    if not text:
        return ""

    s = str(text)

    # 1. Conservative AIGIS recognition:
    # "A I G I S", "A-I-G-I-S", "A - I - G - I - S", "A.I.G.I.S." -> "AIGIS"
    s = re.sub(r"\bA\s*-\s*I\s*-\s*G\s*-\s*I\s*-\s*S\b", "AIGIS", s, flags=re.IGNORECASE)
    s = re.sub(r"\bA\s+I\s+G\s+I\s+S\b", "AIGIS", s, flags=re.IGNORECASE)
    s = re.sub(r"(?:\bA\.I\.G\.I\.S\.|\bA\.I\.G\.I\.S\b)", "AIGIS", s, flags=re.IGNORECASE)

    # 2. Accidental repeated whitespace cleanup
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s*\n\s*", "\n", s)

    return s.strip()
