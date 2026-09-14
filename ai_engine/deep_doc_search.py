import os
import json
import time
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    from memory.local_memory_vault import LocalMemoryVault
    from documents import (
        extract_file,
        normalize_text,
        chunk_document,
        SUPPORTED_EXTENSIONS,
        ExtractedDocument
    )
    from embeddings import LocalONNXEmbedder, VectorSearchEngine
except ImportError:
    from ai_engine.memory.local_memory_vault import LocalMemoryVault
    from ai_engine.documents import (
        extract_file,
        normalize_text,
        chunk_document,
        SUPPORTED_EXTENSIONS,
        ExtractedDocument
    )
    from ai_engine.embeddings import LocalONNXEmbedder, VectorSearchEngine


class DeepDocSearchEngine:
    """
    Robust Local Deep Document Search & Ingestion Engine for AIGIS.
    100% On-Device & Zero-Cloud: No remote APIs, vector clouds, or third-party web calls.

    Features:
    - Authoritative on-device SQLite storage (documents & document_chunks in aigis_local_vault.db).
    - Robust local extraction for PDF, DOCX, Markdown, Text, and Code.
    - Semantic-aware hierarchical chunking (~350-500 tokens with ~50 token overlap).
    - Local ONNX sentence embedding generation (all-MiniLM-L6-v2) stored as float32 in SQLite.
    - Semantic vector similarity, lexical keyword matching, and hybrid retrieval.
    - Content-hash based incremental change detection (skips unchanged files).
    - Automatic background file watcher for registered directories.
    - Preserves backward compatibility for all existing /api/v1/docs/* endpoints.
    """

    def __init__(
        self,
        data_dir: Optional[str] = None,
        vault: Optional[LocalMemoryVault] = None,
        embedder: Optional[LocalONNXEmbedder] = None
    ):
        self.data_dir = data_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.watched_dirs_file = os.path.join(self.data_dir, "doc_watched_dirs.json")

        self.vault = vault or LocalMemoryVault()
        self.embedder = embedder or LocalONNXEmbedder()
        self.vector_search = VectorSearchEngine(vault=self.vault, embedder=self.embedder)

        self.watched_dirs: List[str] = []
        self._watcher_thread: Optional[threading.Thread] = None
        self._watcher_running = False

        self.load_watched_dirs()
        self.start_file_watcher()

    def load_watched_dirs(self):
        """Loads watched directory paths from persistence."""
        if os.path.exists(self.watched_dirs_file):
            try:
                with open(self.watched_dirs_file, "r", encoding="utf-8") as f:
                    self.watched_dirs = json.load(f)
            except Exception:
                self.watched_dirs = []

    def save_watched_dirs(self):
        """Persists watched directory list."""
        try:
            with open(self.watched_dirs_file, "w", encoding="utf-8") as f:
                json.dump(self.watched_dirs, f, indent=2)
        except Exception as e:
            print(f"[DOC SEARCH ERROR] Failed to save watched dirs: {e}")

    def start_file_watcher(self):
        """Starts automatic background file watcher thread for real-time incremental re-indexing."""
        if not self._watcher_running:
            self._watcher_running = True
            self._watcher_thread = threading.Thread(target=self._file_watcher_loop, daemon=True)
            self._watcher_thread.start()

    def stop_file_watcher(self):
        """Stops the file watcher thread."""
        self._watcher_running = False
        if self._watcher_thread and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=2.0)

    def _file_watcher_loop(self):
        """Background loop polling registered directories every 10 seconds for file changes."""
        while self._watcher_running:
            time.sleep(10.0)
            for d in list(self.watched_dirs):
                if os.path.exists(d):
                    try:
                        self.index_directory(d)
                    except Exception as e:
                        print(f"[FILE WATCHER ERROR] Error checking watched directory {d}: {e}")

    def add_watched_directory(self, dir_path: str):
        """Registers a directory for automatic background watching & incremental indexing."""
        abs_path = os.path.abspath(dir_path)
        if abs_path not in self.watched_dirs:
            self.watched_dirs.append(abs_path)
            self.save_watched_dirs()
            self.index_directory(abs_path)

    def detect_collection(self, file_path: str) -> str:
        """Detects document collection category based on file path and extension."""
        p = file_path.lower()
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".cpp", ".c", ".h", ".html", ".css", ".json"]:
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
        """
        Extracts, normalizes, chunks, embeds (if model available), and indexes a local file into SQLite storage.
        Idempotent: Uses SHA-256 content hashing to skip unchanged files.
        Safe: Extraction failures do not destroy existing valid index data.
        """
        if not os.path.exists(file_path):
            return {"status": "ERROR", "message": f"File path does not exist: {file_path}"}

        abs_path = os.path.abspath(file_path)
        filename = os.path.basename(abs_path)
        ext = os.path.splitext(abs_path)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            return {"status": "ERROR", "message": f"Unsupported file extension '{ext}'."}

        mtime = os.path.getmtime(abs_path)
        size_bytes = os.path.getsize(abs_path)
        doc_collection = collection or self.detect_collection(abs_path)

        # Check existing index in SQLite vault
        existing_doc = self.vault.get_document_by_path(abs_path)
        doc_id = existing_doc["id"] if existing_doc else f"doc_{abs(hash(abs_path))}"

        # 1. Robust Extraction
        extracted: ExtractedDocument = extract_file(abs_path)

        if extracted.status == "ERROR":
            # Safety rule: If extraction fails but valid index exists, do NOT destroy valid chunks
            if existing_doc and existing_doc.get("extraction_status") == "SUCCESS":
                return {
                    "status": "WARNING",
                    "message": f"Extraction failed ({extracted.error_message}); preserving previous valid index for {filename}.",
                    "chunkCount": len(self.vault.get_document_chunks(doc_id))
                }
            # Record failed extraction
            self.vault.upsert_document(
                doc_id=doc_id,
                path=abs_path,
                filename=filename,
                extension=ext,
                size_bytes=size_bytes,
                modified_at=mtime,
                content_hash="",
                extraction_status="ERROR",
                extraction_error=extracted.error_message
            )
            return {"status": "ERROR", "message": extracted.error_message}

        content_hash = extracted.content_hash

        # 2. Content-hash based incremental check
        if existing_doc and existing_doc.get("content_hash") == content_hash and existing_doc.get("extraction_status") == "SUCCESS":
            existing_chunks = self.vault.get_document_chunks(doc_id)
            if len(existing_chunks) > 0:
                return {
                    "status": "SKIPPED",
                    "message": f"File is up to date (content hash match): {filename}",
                    "chunkCount": len(existing_chunks)
                }

        # 3. Empty file handling
        if not extracted.text.strip():
            self.vault.upsert_document(
                doc_id=doc_id,
                path=abs_path,
                filename=filename,
                extension=ext,
                size_bytes=size_bytes,
                modified_at=mtime,
                content_hash=content_hash,
                extraction_status="SUCCESS",
                extraction_error=None
            )
            self.vault.store_document_chunks(doc_id, [])
            return {
                "status": "WARNING",
                "message": f"No extractable text found in file: {filename}",
                "chunkCount": 0,
                "embeddingStatus": "NONE"
            }

        # 4. Semantic-Aware Chunking (~350–500 tokens, ~50 tokens overlap)
        chunks = chunk_document(
            document_id=doc_id,
            text=extracted.text,
            filename=filename,
            path=abs_path,
            extension=ext,
            extra_metadata={
                "collection": doc_collection,
                "codeMeta": extracted.metadata,
                "content_hash": content_hash
            }
        )

        # 5. Persist Document & Chunks in SQLite vault
        self.vault.upsert_document(
            doc_id=doc_id,
            path=abs_path,
            filename=filename,
            extension=ext,
            size_bytes=size_bytes,
            modified_at=mtime,
            content_hash=content_hash,
            extraction_status="SUCCESS",
            extraction_error=None
        )

        stored_count = self.vault.store_document_chunks(doc_id, chunks)

        # 6. Incremental Vector Embedding Generation (if model available)
        embedding_status = "EMBEDDING_MODEL_UNAVAILABLE"
        if self.embedder.is_available() and chunks:
            batch_size = int(os.getenv("AIGIS_EMBEDDING_BATCH_SIZE", "16"))
            chunk_vectors = []
            for i in range(0, len(chunks), batch_size):
                sub_batch = chunks[i:i + batch_size]
                texts = [c.content for c in sub_batch]
                vecs = self.embedder.embed_batch(texts)
                if vecs is not None:
                    for c_obj, v in zip(sub_batch, vecs):
                        chunk_vectors.append((c_obj.id, v, self.embedder.MODEL_NAME, self.embedder.EXPECTED_DIMENSION))
            if chunk_vectors:
                self.vault.batch_store_chunk_vectors(chunk_vectors)
                embedding_status = "READY"
        else:
            embedding_status = self.embedder.status().get("status", "EMBEDDING_MODEL_UNAVAILABLE")

        return {
            "status": "INDEXED",
            "message": f"Successfully indexed {filename}",
            "collection": doc_collection,
            "chunkCount": stored_count,
            "embeddingStatus": embedding_status
        }

    def index_directory(self, dir_path: str, collection: Optional[str] = None) -> Dict[str, Any]:
        """
        Recursively indexes supported documents in a directory.
        Registers directory for automatic background monitoring.
        """
        abs_path = os.path.abspath(dir_path)
        if not os.path.exists(abs_path):
            return {"status": "ERROR", "message": f"Directory path does not exist: {dir_path}"}

        if abs_path not in self.watched_dirs:
            self.watched_dirs.append(abs_path)
            self.save_watched_dirs()

        indexed_count = 0
        skipped_count = 0
        ignored_dirs = {
            'node_modules', 'target', 'dist', '__pycache__', 'build', '.git', '.idea', '.vscode'
        }

        for root, dirs, files in os.walk(abs_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ignored_dirs]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    full_path = os.path.join(root, file)
                    res = self.index_file(full_path, collection=collection)
                    if res.get("status") == "INDEXED":
                        indexed_count += 1
                    elif res.get("status") == "SKIPPED":
                        skipped_count += 1

        return {
            "status": "SUCCESS",
            "message": f"Directory scan complete: {indexed_count} indexed, {skipped_count} up-to-date skipped.",
            "indexedCount": indexed_count,
            "skippedCount": skipped_count,
            "watched": True
        }

    def search(
        self,
        query: str,
        top_k: int = 5,
        collection: Optional[str] = None,
        mode: str = "hybrid",
        lexical_weight: float = 0.30,
        semantic_weight: float = 0.70
    ) -> List[Dict[str, Any]]:
        """
        Retrieves document chunks based on retrieval mode:
        - "lexical": Keyword token matching across chunk content and heading.
        - "semantic": Pure vector cosine similarity over float32 on-device embeddings.
        - "hybrid": Weighted combination of lexical and semantic retrieval (with safe fallback).
        """
        norm_mode = (mode or "hybrid").lower().strip()
        limit = min(max(top_k, 1), 20)

        if norm_mode == "lexical":
            results = self.vault.search_document_chunks(query=query, limit=limit, collection=collection)
            for r in results:
                r["retrieval_mode"] = "LEXICAL"
            return results
        elif norm_mode == "semantic":
            sem_res = self.vector_search.search_semantic(query=query, top_k=limit, collection=collection)
            return sem_res.get("results", [])
        else:
            # Hybrid default
            hyb_res = self.vector_search.search_hybrid(
                query=query,
                top_k=limit,
                collection=collection,
                lexical_weight=lexical_weight,
                semantic_weight=semantic_weight
            )
            return hyb_res.get("results", [])

    def search_detailed(
        self,
        query: str,
        top_k: int = 5,
        collection: Optional[str] = None,
        mode: str = "hybrid"
    ) -> Dict[str, Any]:
        """
        Returns full search response envelope with retrieval mode, status, and embedding metadata.
        """
        norm_mode = (mode or "hybrid").lower().strip()
        limit = min(max(top_k, 1), 20)
        embedder_status = self.embedder.status()

        if norm_mode == "lexical":
            results = self.vault.search_document_chunks(query=query, limit=limit, collection=collection)
            for r in results:
                r["retrieval_mode"] = "LEXICAL"
            return {
                "status": "SUCCESS",
                "message": f"Retrieved {len(results)} chunks via lexical search.",
                "query": query,
                "mode": "lexical",
                "retrievalMode": "LEXICAL",
                "fallbackUsed": False,
                "results": results,
                "count": len(results),
                "embeddingStatus": embedder_status
            }
        elif norm_mode == "semantic":
            sem_res = self.vector_search.search_semantic(query=query, top_k=limit, collection=collection)
            results = sem_res.get("results", [])
            status = sem_res.get("status", "SUCCESS")
            message = sem_res.get("message", "")
            return {
                "status": status,
                "message": message or f"Retrieved {len(results)} chunks via semantic vector search.",
                "query": query,
                "mode": "semantic",
                "retrievalMode": "SEMANTIC",
                "fallbackUsed": False,
                "results": results,
                "count": len(results),
                "embeddingStatus": embedder_status
            }
        else:
            hyb_res = self.vector_search.search_hybrid(
                query=query,
                top_k=limit,
                collection=collection
            )
            results = hyb_res.get("results", [])
            ret_mode = hyb_res.get("retrieval_mode", "HYBRID")
            status = hyb_res.get("status", "SUCCESS")
            message = hyb_res.get("message", "")
            fallback = (ret_mode == "LEXICAL_FALLBACK") or not self.embedder.is_available()
            return {
                "status": status,
                "message": message or f"Retrieved {len(results)} chunks via hybrid retrieval.",
                "query": query,
                "mode": "hybrid",
                "retrievalMode": ret_mode,
                "fallbackUsed": fallback,
                "results": results,
                "count": len(results),
                "embeddingStatus": embedder_status
            }

    def list_documents(self) -> List[Dict[str, Any]]:
        """Lists all indexed documents with metadata and chunk counts."""
        docs = self.vault.list_documents()
        result = []
        for d in docs:
            mtime = d.get("modified_at", 0)
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S") if mtime else "Unknown"
            result.append({
                "title": d.get("filename"),
                "path": d.get("path"),
                "collection": self.detect_collection(d.get("path", "")),
                "extension": d.get("extension"),
                "sizeBytes": d.get("size_bytes"),
                "modifiedDate": mtime_str,
                "chunkCount": d.get("chunk_count", 0),
                "status": d.get("extraction_status")
            })
        return result
