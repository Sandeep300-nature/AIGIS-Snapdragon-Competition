import re
from typing import Optional

# Non-printable control characters excluding \t (0x09) and \n (0x0A)
_CONTROL_CHAR_REGEX = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Excessive consecutive newlines (3 or more)
_EXCESSIVE_NEWLINES_REGEX = re.compile(r'\n{3,}')


def normalize_text(text: Optional[str], is_code: bool = False) -> str:
    """
    Normalizes extracted document or source code text while preserving source fidelity.

    Features:
    - Normalizes line endings (\\r\\n and \\r -> \\n).
    - Removes non-printable control characters while preserving \\t and \\n.
    - Normalizes excessive blank lines (3+ newlines -> 2 newlines).
    - Preserves Unicode characters (accents, emojis, multilingual text).
    - Preserves indentation and formatting for source code (leading whitespace intact).
    """
    if not text:
        return ""

    # 1. Normalize line endings
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    # 2. Strip non-printable control characters
    normalized = _CONTROL_CHAR_REGEX.sub("", normalized)

    # 3. Line-by-line whitespace cleanup
    lines = normalized.split("\n")
    cleaned_lines = []
    for line in lines:
        if is_code:
            # For code: preserve leading indentation, strip trailing whitespace
            cleaned_lines.append(line.rstrip())
        else:
            # For prose/markdown: strip trailing whitespace, normalize internal tabs
            cleaned_lines.append(line.rstrip())

    normalized = "\n".join(cleaned_lines)

    # 4. Collapse excessive consecutive blank lines (3+ to 2)
    normalized = _EXCESSIVE_NEWLINES_REGEX.sub("\n\n", normalized)

    # 5. Trim leading and trailing document whitespace
    return normalized.strip()
