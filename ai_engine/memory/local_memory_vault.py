import os
import sqlite3
import json
import uuid
import threading
import numpy as np
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple

class LocalMemoryVault:
    """
    Local SQLite Memory Vault for AIGIS.
    Authoritative persistent on-device storage for long-term user memories,
    project context, user preferences, and system facts.

    Features:
    - 100% Local: Python standard library sqlite3 (zero external network dependencies).
    - Thread-safe connection handling with mutex lock.
    - Parameterized SQL queries preventing SQL injection.
    - Idempotent migration from legacy long_term_memory.json without modifying or deleting original file.
    - Deterministic local lexical search with category, importance, and expiration filtering.
    - vector_blob column initialized as NULL (ready for future M7 Step 4 embeddings).
    """

    SCHEMA_MEMORIES = """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        content TEXT NOT NULL,
        source_turn TEXT,
        confidence REAL DEFAULT 1.0,
        importance INTEGER DEFAULT 3,
        is_pinned BOOLEAN DEFAULT FALSE,
        sensitivity TEXT DEFAULT 'HIGH',
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        expires_at TIMESTAMP,
        vector_blob BLOB
    );
    """

    SCHEMA_METADATA = """
    CREATE TABLE IF NOT EXISTS vault_metadata (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """

    SCHEMA_INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
    CREATE INDEX IF NOT EXISTS idx_memories_pinned ON memories(is_pinned);
    CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
    """

    SCHEMA_DOCUMENTS = """
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        path TEXT NOT NULL UNIQUE,
        filename TEXT NOT NULL,
        extension TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        modified_at REAL NOT NULL,
        content_hash TEXT NOT NULL,
        indexed_at TIMESTAMP NOT NULL,
        extraction_status TEXT NOT NULL,
        extraction_error TEXT
    );
    """

    SCHEMA_DOCUMENT_CHUNKS = """
    CREATE TABLE IF NOT EXISTS document_chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        content TEXT NOT NULL,
        heading TEXT,
        start_offset INTEGER,
        end_offset INTEGER,
        metadata_json TEXT,
        created_at TIMESTAMP NOT NULL,
        vector_blob BLOB,
        embedding_model TEXT,
        embedding_dimension INTEGER,
        embedded_at TIMESTAMP,
        FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    """

    SCHEMA_DOC_INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path);
    CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
    CREATE INDEX IF NOT EXISTS idx_document_chunks_doc_id ON document_chunks(document_id);
    CREATE INDEX IF NOT EXISTS idx_document_chunks_doc_idx ON document_chunks(document_id, chunk_index);
    """

    DEFAULT_DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "aigis_local_vault.db"
    )

    DEFAULT_LEGACY_JSON_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "long_term_memory.json"
    )

    def __init__(
        self,
        db_path: Optional[str] = None,
        json_migration_path: Optional[str] = None,
        auto_migrate: bool = True
    ):
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self.legacy_json_path = json_migration_path or self.DEFAULT_LEGACY_JSON_PATH
        self._lock = threading.Lock()

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

        if auto_migrate and os.path.exists(self.legacy_json_path):
            self.migrate_from_json(self.legacy_json_path)

    def _init_schema(self):
        """Initializes database schema with required tables and indexes."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(self.SCHEMA_MEMORIES)
            cursor.execute(self.SCHEMA_METADATA)
            cursor.execute(self.SCHEMA_DOCUMENTS)
            cursor.execute(self.SCHEMA_DOCUMENT_CHUNKS)
            cursor.executescript(self.SCHEMA_INDEXES)
            cursor.executescript(self.SCHEMA_DOC_INDEXES)

            # Idempotent migration for existing document_chunks tables
            cursor.execute("PRAGMA table_info(document_chunks)")
            existing_cols = {r["name"] for r in cursor.fetchall()}
            if "embedding_model" not in existing_cols:
                cursor.execute("ALTER TABLE document_chunks ADD COLUMN embedding_model TEXT")
            if "embedding_dimension" not in existing_cols:
                cursor.execute("ALTER TABLE document_chunks ADD COLUMN embedding_dimension INTEGER")
            if "embedded_at" not in existing_cols:
                cursor.execute("ALTER TABLE document_chunks ADD COLUMN embedded_at TIMESTAMP")

            self._conn.commit()

    def get_metadata(self, key: str) -> Optional[str]:
        """Retrieves a metadata value by key."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT value FROM vault_metadata WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None

    def set_metadata(self, key: str, value: str):
        """Sets or updates a metadata key-value pair."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "INSERT INTO vault_metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value)
            )
            self._conn.commit()

    def add_memory(
        self,
        content: str,
        category: str = "GENERAL_KNOWLEDGE",
        importance: int = 3,
        is_pinned: bool = False,
        source_turn: str = "user_explicit",
        confidence: float = 1.0,
        sensitivity: str = "HIGH",
        expires_at: Optional[str] = None,
        memory_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Inserts a new memory or updates existing memory if duplicate content in the same category exists.
        Returns the memory dictionary.
        """
        cleaned_content = content.strip()
        if not cleaned_content:
            return None

        norm_category = category.upper().strip()
        now_str = datetime.now().isoformat()
        mid = memory_id or str(uuid.uuid4())

        with self._lock:
            cursor = self._conn.cursor()

            # Check for existing duplicate in same category
            cursor.execute(
                "SELECT id, content FROM memories WHERE category = ?",
                (norm_category,)
            )
            rows = cursor.fetchall()
            for r in rows:
                existing_c = r["content"].lower()
                new_c = cleaned_content.lower()
                if existing_c == new_c or (len(new_c) > 15 and new_c in existing_c):
                    existing_id = r["id"]
                    cursor.execute(
                        """
                        UPDATE memories
                        SET content = ?, importance = ?, is_pinned = ?, updated_at = ?, expires_at = ?
                        WHERE id = ?
                        """,
                        (cleaned_content, importance, bool(is_pinned), now_str, expires_at, existing_id)
                    )
                    self._conn.commit()
                    return self._get_memory_unlocked(existing_id)

            # Insert new record
            cursor.execute(
                """
                INSERT INTO memories (
                    id, category, content, source_turn, confidence,
                    importance, is_pinned, sensitivity, created_at, updated_at, expires_at, vector_blob
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    mid, norm_category, cleaned_content, source_turn, float(confidence),
                    int(importance), bool(is_pinned), sensitivity, now_str, now_str, expires_at
                )
            )
            self._conn.commit()
            return self._get_memory_unlocked(mid)

    def _get_memory_unlocked(self, memory_id: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single memory record by ID."""
        with self._lock:
            return self._get_memory_unlocked(memory_id)

    def list_memories(
        self,
        category: Optional[str] = None,
        include_expired: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Lists all memories, optionally filtered by category and active expiration date.
        """
        today_str = date.today().isoformat()
        with self._lock:
            cursor = self._conn.cursor()
            if category:
                cursor.execute(
                    "SELECT * FROM memories WHERE category = ? ORDER BY is_pinned DESC, importance DESC, created_at DESC",
                    (category.upper().strip(),)
                )
            else:
                cursor.execute(
                    "SELECT * FROM memories ORDER BY is_pinned DESC, importance DESC, created_at DESC"
                )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                m = dict(r)
                if not include_expired and m.get("expires_at"):
                    if m["expires_at"] < today_str:
                        continue
                results.append(m)
            return results

    def search_memories(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
        include_expired: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Performs deterministic local lexical search matching query tokens
        against memory content and category.
        """
        if not query or not query.strip():
            return self.list_memories(category=category, include_expired=include_expired)[:limit]

        query_tokens = [w.lower() for w in query.strip().split() if len(w) > 2]
        all_mems = self.list_memories(category=category, include_expired=include_expired)

        scored = []
        for m in all_mems:
            content_lower = m.get("content", "").lower()
            cat_lower = m.get("category", "").lower()
            overlap = sum(1 for t in query_tokens if t in content_lower or t in cat_lower)
            if overlap > 0 or not query_tokens:
                # Lexical score: token overlap + importance bonus + pinned bonus
                score = overlap * 2.0 + float(m.get("importance", 3)) * 0.5 + (2.0 if m.get("is_pinned") else 0.0)
                scored.append((score, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        category: Optional[str] = None,
        importance: Optional[int] = None,
        is_pinned: Optional[bool] = None,
        expires_at: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Updates specific fields of an existing memory record."""
        existing = self.get_memory(memory_id)
        if not existing:
            return None

        new_content = content.strip() if content is not None else existing["content"]
        new_category = category.upper().strip() if category is not None else existing["category"]
        new_importance = int(importance) if importance is not None else existing["importance"]
        new_pinned = bool(is_pinned) if is_pinned is not None else bool(existing["is_pinned"])
        new_expires = expires_at if expires_at is not None else existing["expires_at"]
        now_str = datetime.now().isoformat()

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE memories
                SET content = ?, category = ?, importance = ?, is_pinned = ?, expires_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_content, new_category, new_importance, new_pinned, new_expires, now_str, memory_id)
            )
            self._conn.commit()
            return self._get_memory_unlocked(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        """Deletes a memory record by ID."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def pin_memory(self, memory_id: str, is_pinned: bool = True) -> Optional[Dict[str, Any]]:
        """Sets the pinned status of a memory record."""
        return self.update_memory(memory_id, is_pinned=is_pinned)

    def count_memories(self, category: Optional[str] = None) -> int:
        """Counts stored memories."""
        with self._lock:
            cursor = self._conn.cursor()
            if category:
                cursor.execute("SELECT COUNT(*) FROM memories WHERE category = ?", (category.upper().strip(),))
            else:
                cursor.execute("SELECT COUNT(*) FROM memories")
            return cursor.fetchone()[0]

    def export_memories(self) -> List[Dict[str, Any]]:
        """Exports all memories in a JSON-serializable list format."""
        all_records = self.list_memories(include_expired=True)
        return [dict(r) for r in all_records]

    def import_memories(self, memories_list: List[Dict[str, Any]]) -> int:
        """
        Imports memory items safely without corrupting the database.
        Returns count of successfully imported records.
        """
        if not isinstance(memories_list, list):
            return 0

        imported = 0
        for item in memories_list:
            if not isinstance(item, dict) or not item.get("content"):
                continue

            content = item.get("content", "").strip()
            cat = item.get("category", "GENERAL_KNOWLEDGE")
            imp = item.get("importance", item.get("importance_score", 3))
            if isinstance(imp, str):
                imp_map = {
                    "PERMANENT": 5, "LONG_TERM": 4, "HIGH": 4, "PROJECT": 3,
                    "MEDIUM": 3, "TEMPORARY": 2, "DISPOSABLE": 1, "LOW": 1
                }
                imp = imp_map.get(imp.upper(), 3)
            pinned = bool(item.get("is_pinned", False))
            mid = item.get("id")
            source = item.get("source_turn", "imported_json")
            conf = float(item.get("confidence", 1.0))
            exp = item.get("expires_at")

            res = self.add_memory(
                content=content,
                category=cat,
                importance=int(imp),
                is_pinned=pinned,
                source_turn=source,
                confidence=conf,
                expires_at=exp,
                memory_id=mid
            )
            if res:
                imported += 1

        return imported

    def migrate_from_json(self, json_path: str) -> Tuple[bool, int, str]:
        """
        Idempotent non-destructive migration from legacy long_term_memory.json.
        Never modifies or deletes the source JSON file.
        Records migration status in vault_metadata.
        Returns: (success: bool, count: int, message: str)
        """
        migration_key = f"migration.{os.path.basename(json_path)}"
        if self.get_metadata(migration_key) == "completed":
            return True, 0, "Migration already completed."

        if not os.path.exists(json_path):
            return False, 0, f"Source JSON file not found: {json_path}"

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                return False, 0, "Source JSON format invalid (expected list of memory items)."

            count = self.import_memories(data)
            self.set_metadata(migration_key, "completed")
            self.set_metadata("migration.completed_at", datetime.now().isoformat())
            self.set_metadata("migration.records_imported", str(count))

            return True, count, f"Successfully migrated {count} memory records into SQLite vault."
        except Exception as e:
            return False, 0, f"Migration failed safely without altering source: {e}"

    # ==========================================
    # MILESTONE 7 STEP 3: DOCUMENT & CHUNK STORAGE
    # ==========================================

    def upsert_document(
        self,
        doc_id: str,
        path: str,
        filename: str,
        extension: str,
        size_bytes: int,
        modified_at: float,
        content_hash: str,
        extraction_status: str = "SUCCESS",
        extraction_error: Optional[str] = None
    ) -> Dict[str, Any]:
        """Inserts or updates a document record in the SQLite vault."""
        now_str = datetime.now().isoformat()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO documents (
                    id, path, filename, extension, size_bytes, modified_at,
                    content_hash, indexed_at, extraction_status, extraction_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    id = excluded.id,
                    filename = excluded.filename,
                    extension = excluded.extension,
                    size_bytes = excluded.size_bytes,
                    modified_at = excluded.modified_at,
                    content_hash = excluded.content_hash,
                    indexed_at = excluded.indexed_at,
                    extraction_status = excluded.extraction_status,
                    extraction_error = excluded.extraction_error
                """,
                (
                    doc_id, path, filename, extension.lower(), int(size_bytes),
                    float(modified_at), content_hash, now_str, extraction_status, extraction_error
                )
            )
            self._conn.commit()
            return self._get_document_unlocked(doc_id)

    def _get_document_unlocked(self, doc_id: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a document record by ID."""
        with self._lock:
            return self._get_document_unlocked(doc_id)

    def get_document_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        """Retrieves a document record by file path."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE path = ?", (path,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_documents(self) -> List[Dict[str, Any]]:
        """Lists all stored documents along with their chunk counts."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT d.*, COUNT(c.id) AS chunk_count
                FROM documents d
                LEFT JOIN document_chunks c ON d.id = c.document_id
                GROUP BY d.id
                ORDER BY d.indexed_at DESC
                """
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def delete_document(self, doc_id: str) -> bool:
        """Deletes a document and its associated chunks from the vault."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (doc_id,))
            cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_document_by_path(self, path: str) -> bool:
        """Deletes a document by path."""
        doc = self.get_document_by_path(path)
        if doc:
            return self.delete_document(doc["id"])
        return False

    def store_document_chunks(self, doc_id: str, chunks: List[Any]) -> int:
        """
        Stores semantic chunks for a document, atomically replacing previous chunks.
        Accepts list of DocumentChunk instances or dicts.
        """
        now_str = datetime.now().isoformat()
        with self._lock:
            cursor = self._conn.cursor()
            # Atomically remove old chunks for this document
            cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (doc_id,))

            stored = 0
            for chunk in chunks:
                if hasattr(chunk, "id"):
                    cid = chunk.id
                    c_idx = chunk.chunk_index
                    content = chunk.content
                    heading = chunk.heading
                    s_offset = chunk.start_offset
                    e_offset = chunk.end_offset
                    meta = json.dumps(chunk.metadata) if chunk.metadata else "{}"
                else:
                    cid = chunk.get("id") or chunk.get("chunk_id") or str(uuid.uuid4())
                    c_idx = chunk.get("chunk_index", stored)
                    content = chunk.get("content", "")
                    heading = chunk.get("heading")
                    s_offset = chunk.get("start_offset", 0)
                    e_offset = chunk.get("end_offset", len(content))
                    meta = json.dumps(chunk.get("metadata", {}))

                cursor.execute(
                    """
                    INSERT INTO document_chunks (
                        id, document_id, chunk_index, content, heading,
                        start_offset, end_offset, metadata_json, created_at, vector_blob
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (cid, doc_id, int(c_idx), content, heading, int(s_offset), int(e_offset), meta, now_str)
                )
                stored += 1

            self._conn.commit()
            return stored

    def get_document_chunks(self, doc_id: str) -> List[Dict[str, Any]]:
        """Retrieves all chunks for a document ordered by chunk_index."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM document_chunks WHERE document_id = ? ORDER BY chunk_index ASC",
                (doc_id,)
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                if item.get("metadata_json"):
                    try:
                        item["metadata"] = json.loads(item["metadata_json"])
                    except Exception:
                        item["metadata"] = {}
                results.append(item)
            return results

    def search_document_chunks(
        self,
        query: str,
        limit: int = 5,
        collection: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Deterministic local lexical search across document chunks.
        Scores candidate chunks by token overlap across content and heading.
        (Vector semantic embeddings deferred to M7 Step 4).
        """
        if not query or not query.strip():
            return []

        query_tokens = [w.lower() for w in query.strip().split() if len(w) > 2]
        if not query_tokens:
            return []

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT c.*, d.filename, d.path AS doc_path, d.extension
                FROM document_chunks c
                JOIN documents d ON c.document_id = d.id
                ORDER BY c.created_at DESC
                """
            )
            rows = cursor.fetchall()

        scored = []
        for r in rows:
            chunk = dict(r)
            meta = {}
            if chunk.get("metadata_json"):
                try:
                    meta = json.loads(chunk["metadata_json"])
                except Exception:
                    meta = {}
            chunk["metadata"] = meta

            if collection and meta.get("collection", "").lower() != collection.lower():
                continue

            content_lower = chunk.get("content", "").lower()
            heading_lower = (chunk.get("heading") or "").lower()

            content_overlap = sum(1 for t in query_tokens if t in content_lower)
            heading_overlap = sum(1 for t in query_tokens if t in heading_lower)

            score = content_overlap * 1.0 + heading_overlap * 2.0
            if score > 0:
                chunk["score"] = round(score, 2)
                chunk["title"] = chunk.get("filename")
                chunk["path"] = chunk.get("doc_path")
                chunk["collection"] = meta.get("collection", "Projects")
                chunk["codeMeta"] = meta.get("codeMeta", {})
                chunk["text"] = chunk.get("content")
                scored.append(chunk)

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def count_documents(self) -> int:
        """Returns the total number of indexed documents in the vault."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM documents")
            return cursor.fetchone()[0]

    def count_document_chunks(self) -> int:
        """Returns the total number of chunks stored in the vault."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM document_chunks")
            return cursor.fetchone()[0]

    # ==========================================
    # MILESTONE 7 STEP 4: VECTOR STORAGE & RETRIEVAL
    # ==========================================

    def store_chunk_vector(
        self,
        chunk_id: str,
        vector: Any,
        model_name: str = "all-MiniLM-L6-v2",
        dimension: Optional[int] = None
    ) -> bool:
        """
        Stores an embedding vector for a document chunk as serialized float32 binary bytes.
        Validates vector dimension before storage. Never uses Python pickles.
        """
        if vector is None:
            return False

        try:
            arr = np.asarray(vector, dtype=np.float32).flatten()
            actual_dim = dimension if dimension is not None else len(arr)
            if dimension is not None and len(arr) != dimension:
                return False
            blob = arr.tobytes()
        except Exception:
            return False

        now_str = datetime.now().isoformat()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE document_chunks
                SET vector_blob = ?, embedding_model = ?, embedding_dimension = ?, embedded_at = ?
                WHERE id = ?
                """,
                (blob, model_name, int(actual_dim), now_str, chunk_id)
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def batch_store_chunk_vectors(
        self,
        chunk_vectors: List[Any],
        model_name: str = "all-MiniLM-L6-v2",
        dimension: Optional[int] = None
    ) -> int:
        """
        Stores a batch of (chunk_id, vector, [model_name, dimension]) in a single transaction.
        """
        now_str = datetime.now().isoformat()
        stored = 0
        with self._lock:
            cursor = self._conn.cursor()
            for item in chunk_vectors:
                if len(item) == 4:
                    chunk_id, vector, m_name, dim = item
                elif len(item) == 2:
                    chunk_id, vector = item
                    m_name, dim = model_name, dimension
                else:
                    continue

                if vector is None:
                    continue
                try:
                    arr = np.asarray(vector, dtype=np.float32).flatten()
                    actual_dim = dim if dim is not None else len(arr)
                    if dim is not None and len(arr) != dim:
                        continue
                    blob = arr.tobytes()
                    cursor.execute(
                        """
                        UPDATE document_chunks
                        SET vector_blob = ?, embedding_model = ?, embedding_dimension = ?, embedded_at = ?
                        WHERE id = ?
                        """,
                        (blob, m_name, int(actual_dim), now_str, chunk_id)
                    )
                    stored += cursor.rowcount
                except Exception:
                    continue

            self._conn.commit()
        return stored

    def get_chunks_with_vectors(
        self,
        collection: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all chunks that have non-null vector_blob.
        Safely deserializes float32 binary bytes to NumPy array.
        Validates dimension against stored metadata.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT c.*, d.filename, d.path AS doc_path, d.extension
                FROM document_chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.vector_blob IS NOT NULL
                ORDER BY c.created_at DESC
                """
            )
            rows = cursor.fetchall()

        results = []
        for r in rows:
            item = dict(r)
            blob = item.get("vector_blob")
            if not blob:
                continue

            expected_dim = item.get("embedding_dimension") or 384
            try:
                vec = np.frombuffer(blob, dtype=np.float32)
                if len(vec) != expected_dim or not np.all(np.isfinite(vec)):
                    # Corrupt or dimension mismatch
                    continue
                item["vector"] = vec
            except Exception:
                continue

            meta = {}
            if item.get("metadata_json"):
                try:
                    meta = json.loads(item["metadata_json"])
                except Exception:
                    meta = {}
            item["metadata"] = meta

            if collection and meta.get("collection", "").lower() != collection.lower():
                continue

            results.append(item)

        return results

    def get_unembedded_chunks(
        self,
        doc_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves chunks that do not yet have vector embeddings.
        """
        with self._lock:
            cursor = self._conn.cursor()
            if doc_id:
                cursor.execute(
                    "SELECT * FROM document_chunks WHERE document_id = ? AND vector_blob IS NULL ORDER BY chunk_index ASC",
                    (doc_id,)
                )
            else:
                cursor.execute(
                    "SELECT * FROM document_chunks WHERE vector_blob IS NULL ORDER BY created_at ASC"
                )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def close(self):
        """Closes the underlying SQLite connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

