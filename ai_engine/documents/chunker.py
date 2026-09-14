import re
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from .normalizer import normalize_text


@dataclass
class DocumentChunk:
    """
    Structured document chunk with semantic metadata and offset coordinates.
    """
    id: str
    document_id: str
    chunk_index: int
    content: str
    heading: Optional[str] = None
    start_offset: int = 0
    end_offset: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    """
    Estimates token count for text using word/punctuation tokenization (~4 chars per token).
    """
    if not text:
        return 0
    # Standard subword/word heuristic: count words + punctuation symbols
    tokens = re.findall(r'\w+|[^\w\s]', text)
    return max(1, len(tokens))


class DocumentChunker:
    """
    Semantic-Aware Local Document & Code Chunker for AIGIS.
    Splits text along semantic boundaries (headings, paragraphs, sentences, code blocks)
    targeting ~350–500 tokens with ~50 tokens overlap.
    """

    DEFAULT_TARGET_TOKENS = 400
    DEFAULT_MAX_TOKENS = 500
    DEFAULT_MIN_TOKENS = 250
    DEFAULT_OVERLAP_TOKENS = 50

    HEADING_REGEX = re.compile(r'^(#{1,6}\s+.+|[A-Z0-9\s_\-]{3,60}:|[A-Z][A-Za-z0-9\s]{2,40}\n[-=]{3,})$', re.MULTILINE)
    CODE_BLOCK_REGEX = re.compile(r'^(?:\s*(?:class|def|public|private|protected|static|async|function)\s+([A-Za-z0-9_]+))', re.MULTILINE)

    def __init__(
        self,
        target_tokens: int = DEFAULT_TARGET_TOKENS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        min_tokens: int = DEFAULT_MIN_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS
    ):
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(
        self,
        document_id: str,
        text: str,
        filename: str = "",
        path: str = "",
        extension: str = "",
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> List[DocumentChunk]:
        """
        Chunks text into semantic-aware DocumentChunk items.
        """
        is_code = extension.lower() in {
            ".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".cpp", ".c", ".h", ".json", ".css", ".html"
        }
        normalized = normalize_text(text, is_code=is_code)
        if not normalized:
            return []

        base_meta = {
            "filename": filename,
            "path": path,
            "extension": extension,
            **(extra_metadata or {})
        }

        # If entire document fits within target max tokens, return single chunk
        total_tokens = estimate_tokens(normalized)
        if total_tokens <= self.max_tokens:
            return [
                DocumentChunk(
                    id=f"{document_id}_0",
                    document_id=document_id,
                    chunk_index=0,
                    content=normalized,
                    heading=self._extract_first_heading(normalized, is_code),
                    start_offset=0,
                    end_offset=len(normalized),
                    metadata=base_meta
                )
            ]

        if is_code:
            return self._chunk_code(document_id, normalized, base_meta)
        else:
            return self._chunk_prose(document_id, normalized, base_meta)

    def _extract_first_heading(self, text: str, is_code: bool) -> Optional[str]:
        """Finds leading heading or code construct title."""
        if is_code:
            match = self.CODE_BLOCK_REGEX.search(text)
            return match.group(0).strip() if match else None
        else:
            match = self.HEADING_REGEX.search(text)
            return match.group(0).strip().lstrip('#').strip() if match else None

    def _chunk_prose(
        self,
        document_id: str,
        text: str,
        base_meta: Dict[str, Any]
    ) -> List[DocumentChunk]:
        """
        Hierarchical prose chunking:
        1. Sections (Headings)
        2. Paragraphs (\n\n)
        3. Sentences ([.!?])
        4. Overlap propagation
        """
        # Split text into semantic atomic units (paragraphs / sections)
        paragraphs = re.split(r'\n{2,}', text)
        units: List[Tuple[str, Optional[str], int, int]] = []
        current_heading: Optional[str] = None
        search_start = 0

        for para in paragraphs:
            para_clean = para.strip()
            if not para_clean:
                continue

            # Check if this paragraph is or begins with a heading
            lines = para_clean.split("\n")
            if lines and (lines[0].startswith("#") or (len(lines) > 1 and re.match(r'^[-=]{3,}$', lines[1]))):
                current_heading = lines[0].lstrip('#').strip()

            start_char = text.find(para_clean, search_start)
            if start_char == -1:
                start_char = search_start
            end_char = start_char + len(para_clean)
            search_start = end_char

            # If paragraph itself is too large, break by sentences
            para_tokens = estimate_tokens(para_clean)
            if para_tokens > self.max_tokens:
                sentences = re.split(r'(?<=[.!?])\s+', para_clean)
                sub_search = start_char
                for sent in sentences:
                    s_clean = sent.strip()
                    if not s_clean:
                        continue
                    s_start = text.find(s_clean, sub_search)
                    if s_start == -1:
                        s_start = sub_search
                    s_end = s_start + len(s_clean)
                    sub_search = s_end
                    units.append((s_clean, current_heading, s_start, s_end))
            else:
                units.append((para_clean, current_heading, start_char, end_char))

        # Assemble units into chunks with token target and overlap
        return self._assemble_chunks(document_id, units, text, base_meta)

    def _chunk_code(
        self,
        document_id: str,
        text: str,
        base_meta: Dict[str, Any]
    ) -> List[DocumentChunk]:
        """
        Source code chunking preserving class and function boundaries.
        """
        lines = text.split("\n")
        blocks: List[Tuple[str, Optional[str], int, int]] = []
        current_block_lines = []
        current_heading = None
        current_start_char = 0
        running_char = 0

        for line in lines:
            line_len = len(line) + 1  # include newline
            # Check for top-level definition boundary (class or def at start or indentation 0-4)
            match = re.match(r'^(?:[ \t]{0,4})(class|def|public|private|protected|function|async function|const|let|var)\s+([A-Za-z0-9_]+)', line)

            if match and current_block_lines:
                block_text = "\n".join(current_block_lines).strip()
                if block_text:
                    blocks.append((block_text, current_heading, current_start_char, running_char))
                current_block_lines = [line]
                current_start_char = running_char
                current_heading = f"{match.group(1)} {match.group(2)}"
            else:
                if not current_block_lines and match:
                    current_heading = f"{match.group(1)} {match.group(2)}"
                    current_start_char = running_char
                current_block_lines.append(line)

            running_char += line_len

        if current_block_lines:
            block_text = "\n".join(current_block_lines).strip()
            if block_text:
                blocks.append((block_text, current_heading, current_start_char, running_char))

        return self._assemble_chunks(document_id, blocks, text, base_meta)

    def _assemble_chunks(
        self,
        document_id: str,
        units: List[Tuple[str, Optional[str], int, int]],
        full_text: str,
        base_meta: Dict[str, Any]
    ) -> List[DocumentChunk]:
        """
        Groups units into chunks matching target_tokens with overlap_tokens.
        """
        if not units:
            return []

        chunks: List[DocumentChunk] = []
        current_units: List[Tuple[str, Optional[str], int, int]] = []
        current_tokens = 0

        for unit in units:
            unit_text, heading, start, end = unit
            unit_toks = estimate_tokens(unit_text)

            if current_units and (current_tokens + unit_toks > self.max_tokens):
                # Finalize current chunk
                chunk_obj = self._build_chunk(document_id, len(chunks), current_units, base_meta)
                chunks.append(chunk_obj)

                # Prepare overlap: select units from the end of current_units
                overlap_units: List[Tuple[str, Optional[str], int, int]] = []
                overlap_toks = 0
                for u in reversed(current_units):
                    u_toks = estimate_tokens(u[0])
                    if overlap_toks + u_toks <= self.overlap_tokens or not overlap_units:
                        overlap_units.insert(0, u)
                        overlap_toks += u_toks
                    else:
                        break

                current_units = list(overlap_units)
                current_tokens = overlap_toks

            current_units.append(unit)
            current_tokens += unit_toks

        # Final trailing chunk
        if current_units:
            chunk_obj = self._build_chunk(document_id, len(chunks), current_units, base_meta)
            # Avoid duplicate identical single-unit chunk if overlap completely absorbed it
            if not chunks or chunk_obj.content != chunks[-1].content:
                chunks.append(chunk_obj)

        return chunks

    def _build_chunk(
        self,
        document_id: str,
        chunk_index: int,
        unit_list: List[Tuple[str, Optional[str], int, int]],
        base_meta: Dict[str, Any]
    ) -> DocumentChunk:
        """Constructs a single DocumentChunk with exact boundary offsets."""
        combined_text = "\n\n".join(u[0] for u in unit_list).strip()
        start_offset = unit_list[0][2]
        end_offset = unit_list[-1][3]

        # Use first non-empty heading in the chunk
        heading = next((u[1] for u in unit_list if u[1]), None)

        meta = {
            **base_meta,
            "estimated_tokens": estimate_tokens(combined_text)
        }

        return DocumentChunk(
            id=f"{document_id}_{chunk_index}",
            document_id=document_id,
            chunk_index=chunk_index,
            content=combined_text,
            heading=heading,
            start_offset=start_offset,
            end_offset=end_offset,
            metadata=meta
        )


def chunk_document(
    document_id: str,
    text: str,
    filename: str = "",
    path: str = "",
    extension: str = "",
    extra_metadata: Optional[Dict[str, Any]] = None,
    target_tokens: int = 400,
    max_tokens: int = 500,
    overlap_tokens: int = 50
) -> List[DocumentChunk]:
    """Convenience function for semantic document chunking."""
    chunker = DocumentChunker(
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens
    )
    return chunker.chunk(
        document_id=document_id,
        text=text,
        filename=filename,
        path=path,
        extension=extension,
        extra_metadata=extra_metadata
    )
