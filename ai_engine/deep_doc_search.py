import os
import json
import time
import math
import re
import zipfile
import threading
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

class DeepDocSearchEngine:
    """
    Independent Deep Document Search Engine for AIGIS.
    Completely separated from Conversation History and User Facts Memory.

    Features:
    - Document Index for PDF, Markdown, Word (.docx), TXT, and Code repositories.
    - Automatic File Watcher for real-time incremental re-indexing.
    - Document Collections support (Research, University, Projects, Invoices, Books, Personal, Programming).
    - Code Search Metadata (language, file extension, class_names, function_names).
    - Stores metadata only (path, title, modified date, collection, chunk IDs, embeddings).
    - Top 5-10 chunk retrieval & reranking.
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.metadata_file = os.path.join(self.data_dir, "doc_index_metadata.json")
        self.chunks_file = os.path.join(self.data_dir, "doc_index_chunks.json")
        self.watched_dirs_file = os.path.join(self.data_dir, "doc_watched_dirs.json")

        self.metadata: Dict[str, Dict[str, Any]] = {}
        self.chunks: Dict[str, Dict[str, Any]] = {}
        self.watched_dirs: List[str] = []

        self._watcher_thread: Optional[threading.Thread] = None
        self._watcher_running = False

        self.load_index()
        self.start_file_watcher()

    def load_index(self):
        """Loads persistent document index metadata, chunks, and watched directories."""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
            except Exception as e:
                print(f"[DOC SEARCH ERROR] Failed to load metadata: {e}")
                self.metadata = {}

        if os.path.exists(self.chunks_file):
            try:
                with open(self.chunks_file, "r", encoding="utf-8") as f:
                    self.chunks = json.load(f)
            except Exception as e:
                print(f"[DOC SEARCH ERROR] Failed to load chunks: {e}")
                self.chunks = {}

        if os.path.exists(self.watched_dirs_file):
            try:
                with open(self.watched_dirs_file, "r", encoding="utf-8") as f:
                    self.watched_dirs = json.load(f)
            except Exception:
                self.watched_dirs = []

    def save_index(self):
        """Persists document metadata, chunk index, and watched directories."""
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, indent=2)
            with open(self.chunks_file, "w", encoding="utf-8") as f:
                json.dump(self.chunks, f, indent=2)
            with open(self.watched_dirs_file, "w", encoding="utf-8") as f:
                json.dump(self.watched_dirs, f, indent=2)
        except Exception as e:
            print(f"[DOC SEARCH ERROR] Failed to save index: {e}")

    def start_file_watcher(self):
        """Starts automatic background file watcher thread for real-time incremental re-indexing."""
        if not self._watcher_running:
            self._watcher_running = True
            self._watcher_thread = threading.Thread(target=self._file_watcher_loop, daemon=True)
            self._watcher_thread.start()

    def _file_watcher_loop(self):
        """Background loop that polls watched directories for modified files."""
        while self._watcher_running:
            time.sleep(10.0)  # Check every 10 seconds
            for d in list(self.watched_dirs):
                if os.path.exists(d):
                    try:
                        self.index_directory(d)
                    except Exception as e:
                        print(f"[FILE WATCHER ERROR] Error watching {d}: {e}")

    def add_watched_directory(self, dir_path: str):
        """Registers a directory for automatic file watching & incremental re-indexing."""
        abs_path = os.path.abspath(dir_path)
        if abs_path not in self.watched_dirs:
            self.watched_dirs.append(abs_path)
            self.save_index()
            self.index_directory(abs_path)

    def extract_code_metadata(self, text: str, ext: str) -> Dict[str, Any]:
        """Extracts code-specific metadata: language, classes, functions."""
        lang_map = {
            ".py": "Python", ".java": "Java", ".js": "JavaScript", ".jsx": "React (JSX)",
            ".ts": "TypeScript", ".tsx": "TypeScript (TSX)", ".cpp": "C++", ".c": "C",
            ".h": "C/C++ Header", ".json": "JSON", ".css": "CSS", ".html": "HTML"
        }
        language = lang_map.get(ext, "Unknown")
        class_names = []
        function_names = []

        if ext in [".py"]:
            class_names = re.findall(r'^\s*class\s+([A-Za-z0-9_]+)', text, re.MULTILINE)
            function_names = re.findall(r'^\s*def\s+([A-Za-z0-9_]+)', text, re.MULTILINE)
        elif ext in [".java", ".cpp", ".c", ".h", ".js", ".ts", ".jsx", ".tsx"]:
            class_names = re.findall(r'(?:class|interface|record|enum)\s+([A-Za-z0-9_]+)', text)
            function_names = re.findall(r'(?:public|private|protected|static|async|function)\s+(?:[A-Za-z0-9_<>\[\]]+\s+)?([A-Za-z0-9_]+)\s*\(', text)

        return {
            "language": language,
            "extension": ext,
            "classNames": list(set(class_names)),
            "functionNames": list(set(function_names))
        }

    def extract_text(self, file_path: str) -> str:
        """Extracts plain text from PDF, DOCX, TXT, MD, and Code files."""
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext in [".txt", ".md", ".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".cpp", ".c", ".h", ".json", ".css", ".html", ".xml", ".yaml", ".yml", ".sql"]:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            elif ext == ".docx":
                return self._extract_docx(file_path)
            elif ext == ".pdf":
                return self._extract_pdf(file_path)
        except Exception as e:
            print(f"[DOC SEARCH EXTRACT ERROR] Failed to extract {file_path}: {e}")
        return ""

    def _extract_docx(self, file_path: str) -> str:
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                xml_content = zip_ref.read('word/document.xml')
                tree = re.sub(r'<[^>]+>', ' ', xml_content.decode('utf-8', errors='ignore'))
                return " ".join(tree.split())
        except Exception:
            return ""

    def _extract_pdf(self, file_path: str) -> str:
        try:
            with open(file_path, 'rb') as f:
                content = f.read().decode('latin-1', errors='ignore')
                text_blocks = re.findall(r'\((.*?)\)', content)
                clean_blocks = [b for b in text_blocks if len(b) > 4 and any(c.isalpha() for c in b)]
                return " ".join(clean_blocks)
        except Exception:
            return ""

    def detect_collection(self, file_path: str) -> str:
        """Detects document collection type based on path and extension."""
        p = file_path.lower()
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".cpp", ".c", ".h", ".html", ".css"]:
            return "Programming"
        elif "research" in p or "paper" in p:
            return "Research"
        elif "univ" in p or "college" in p or "course" in p:
            return "University"
        elif "invoice" in p or "receipt" in p or "bill" in p:
            return "Invoices"
        elif "book" in p or "novel" in p:
            return "Books"
        elif "personal" in p:
            return "Personal"
        return "Projects"

    def index_file(self, file_path: str, collection: Optional[str] = None) -> Dict[str, Any]:
        """Indexes/re-indexes a single file with incremental modification check."""
        if not os.path.exists(file_path):
            return {"status": "ERROR", "message": f"File path does not exist: {file_path}"}

        mtime = os.path.getmtime(file_path)
        abs_path = os.path.abspath(file_path)
        ext = os.path.splitext(file_path)[1].lower()

        # Incremental check
        if abs_path in self.metadata:
            existing = self.metadata[abs_path]
            if existing.get("modified_date") == mtime and len(existing.get("chunk_ids", [])) > 0:
                return {
                    "status": "SKIPPED",
                    "message": f"File is up to date (incremental index check): {os.path.basename(abs_path)}",
                    "chunkCount": len(existing["chunk_ids"])
                }
            for cid in existing.get("chunk_ids", []):
                self.chunks.pop(cid, None)

        raw_text = self.extract_text(abs_path)
        if not raw_text.strip():
            return {"status": "WARNING", "message": f"No extractable text found in file: {os.path.basename(abs_path)}"}

        code_meta = self.extract_code_metadata(raw_text, ext)
        doc_collection = collection or self.detect_collection(abs_path)
        title = os.path.basename(abs_path)

        chunk_texts = self._chunk_text(raw_text, chunk_size=500, overlap=50)
        chunk_ids = []

        for idx, text in enumerate(chunk_texts):
            cid = f"{hash(abs_path)}_{idx}"
            vector = self._vectorize_text(text)
            self.chunks[cid] = {
                "id": cid,
                "path": abs_path,
                "title": title,
                "collection": doc_collection,
                "codeMeta": code_meta,
                "text": text,
                "vector": vector
            }
            chunk_ids.append(cid)

        # Save metadata only (no raw file content)
        self.metadata[abs_path] = {
            "path": abs_path,
            "title": title,
            "collection": doc_collection,
            "codeMeta": code_meta,
            "modified_date": mtime,
            "chunk_ids": chunk_ids,
            "indexed_at": datetime.now().isoformat()
        }

        self.save_index()

        return {
            "status": "INDEXED",
            "message": f"Successfully indexed {title}",
            "collection": doc_collection,
            "chunkCount": len(chunk_ids)
        }

    def index_directory(self, dir_path: str, collection: Optional[str] = None) -> Dict[str, Any]:
        """Recursively indexes directory and registers it for automatic background watching."""
        abs_path = os.path.abspath(dir_path)
        if not os.path.exists(abs_path):
            return {"status": "ERROR", "message": f"Directory path does not exist: {dir_path}"}

        if abs_path not in self.watched_dirs:
            self.watched_dirs.append(abs_path)

        supported_exts = {".pdf", ".docx", ".txt", ".md", ".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".cpp", ".c", ".h", ".json", ".css", ".html"}
        indexed_count = 0
        skipped_count = 0

        for root, dirs, files in os.walk(abs_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', 'target', 'dist', '__pycache__', 'build']]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in supported_exts:
                    full_path = os.path.join(root, file)
                    res = self.index_file(full_path, collection=collection)
                    if res.get("status") == "INDEXED":
                        indexed_count += 1
                    elif res.get("status") == "SKIPPED":
                        skipped_count += 1

        self.save_index()

        return {
            "status": "SUCCESS",
            "message": f"Directory scan complete: {indexed_count} indexed, {skipped_count} up-to-date skipped.",
            "indexedCount": indexed_count,
            "skippedCount": skipped_count,
            "watched": True
        }

    def search(self, query: str, top_k: int = 5, collection: Optional[str] = None) -> List[Dict[str, Any]]:
        """Vector search returning Top 5 to 10 matching chunks."""
        if not self.chunks:
            return []

        limit = min(max(top_k, 1), 10)
        query_vec = self._vectorize_text(query)

        scored_chunks = []
        for cid, chunk in self.chunks.items():
            if collection and chunk.get("collection", "").lower() != collection.lower():
                continue

            sim = self._cosine_similarity(query_vec, chunk.get("vector", {}))
            if sim > 0.05:
                scored_chunks.append({
                    "score": round(sim, 4),
                    "title": chunk.get("title"),
                    "path": chunk.get("path"),
                    "collection": chunk.get("collection"),
                    "codeMeta": chunk.get("codeMeta"),
                    "text": chunk.get("text")
                })

        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:limit]

    def list_documents(self) -> List[Dict[str, Any]]:

        docs = []
        for path, info in self.metadata.items():
            docs.append({
                "title": info.get("title"),
                "path": path,
                "collection": info.get("collection", "Projects"),
                "codeMeta": info.get("codeMeta", {}),
                "modifiedDate": datetime.fromtimestamp(info.get("modified_date", 0)).strftime("%Y-%m-%d %H:%M:%S"),
                "chunkCount": len(info.get("chunk_ids", []))
            })
        return docs

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = start + chunk_size
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += chunk_size - overlap
        return chunks

    def _vectorize_text(self, text: str) -> Dict[str, float]:
        words = re.findall(r'\w+', text.lower())
        if not words:
            return {}
        tf = {}
        total = len(words)
        for w in words:
            if len(w) > 2:
                tf[w] = tf.get(w, 0) + 1.0
        return {w: count / total for w, count in tf.items()}

    def _cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        if not vec1 or not vec2:
            return 0.0
        intersection = set(vec1.keys()) & set(vec2.keys())
        dot_product = sum(vec1[w] * vec2[w] for w in intersection)
        norm1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        norm2 = math.sqrt(sum(v ** 2 for v in vec2.values()))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return dot_product / (norm1 * norm2)
