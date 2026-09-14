import os
import sys
import unittest
import tempfile
import json
import sqlite3
import socket
import urllib.request
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.memory.local_memory_vault import LocalMemoryVault
from ai_engine.memory.long_term_memory import LongTermMemoryStore, resolve_importance
from ai_engine.memory.memory_extractor import MemoryExtractor
from ai_engine.memory.memory_retriever import MemoryRetriever


class TestMemoryVault(unittest.TestCase):
    """
    Comprehensive test suite for Milestone 7 Step 2:
    Local Memory Vault, SQLite persistence, non-destructive migration,
    backward-compatible memory store, zero-cloud deterministic extraction,
    and secret scrubbing.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_vault.db")
        self.json_path = os.path.join(self.temp_dir.name, "legacy_memory.json")

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # 1. SQLite schema creation
    def test_01_schema_creation(self):
        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        self.assertIn("memories", tables)
        self.assertIn("vault_metadata", tables)

        cursor.execute("PRAGMA table_info(memories)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}
        self.assertIn("id", columns)
        self.assertIn("category", columns)
        self.assertIn("content", columns)
        self.assertIn("importance", columns)
        self.assertIn("is_pinned", columns)
        self.assertIn("vector_blob", columns)
        self.assertIn("expires_at", columns)

        conn.close()
        vault.close()

    # 2. Memory creation
    def test_02_memory_creation(self):
        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        mem = vault.add_memory(
            content="User prefers dark mode in all editors.",
            category="USER_PREFERENCE",
            importance=5,
            is_pinned=True
        )
        self.assertIsNotNone(mem)
        self.assertEqual(mem["category"], "USER_PREFERENCE")
        self.assertEqual(mem["content"], "User prefers dark mode in all editors.")
        self.assertEqual(mem["importance"], 5)
        self.assertTrue(mem["is_pinned"])
        self.assertIsNone(mem["vector_blob"])  # vector_blob initialized as NULL
        vault.close()

    # 3. Memory retrieval
    def test_03_memory_retrieval(self):
        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        created = vault.add_memory("FastAPI runs on port 8000.", category="PROJECT_CONTEXT")
        retrieved = vault.get_memory(created["id"])
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["id"], created["id"])
        self.assertEqual(retrieved["content"], "FastAPI runs on port 8000.")
        vault.close()

    # 4. Memory update
    def test_04_memory_update(self):
        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        created = vault.add_memory("Initial version text.", category="GENERAL_KNOWLEDGE", importance=2)
        updated = vault.update_memory(
            memory_id=created["id"],
            content="Updated version text.",
            importance=4
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["content"], "Updated version text.")
        self.assertEqual(updated["importance"], 4)
        vault.close()

    # 5. Memory deletion
    def test_05_memory_deletion(self):
        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        created = vault.add_memory("To be deleted soon.", category="TASK")
        del_result = vault.delete_memory(created["id"])
        self.assertTrue(del_result)
        self.assertIsNone(vault.get_memory(created["id"]))
        vault.close()

    # 6. Pin/unpin
    def test_06_pin_unpin(self):
        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        created = vault.add_memory("Crucial core principle.", category="PROJECT_CONTEXT", is_pinned=False)
        self.assertFalse(created["is_pinned"])

        pinned = vault.pin_memory(created["id"], is_pinned=True)
        self.assertTrue(pinned["is_pinned"])

        unpinned = vault.pin_memory(created["id"], is_pinned=False)
        self.assertFalse(unpinned["is_pinned"])
        vault.close()

    # 7. Local lexical search
    def test_07_local_lexical_search(self):
        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        vault.add_memory("React Vite frontend is styled with modern CSS.", category="PROJECT_CONTEXT", importance=4)
        vault.add_memory("Python AI Engine uses ONNX Runtime on CPU.", category="PROJECT_CONTEXT", importance=5)
        vault.add_memory("Qualcomm Hexagon NPU execution target.", category="PROJECT_CONTEXT", importance=3)

        results = vault.search_memories("React Vite frontend")
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("React Vite frontend", results[0]["content"])

        npu_results = vault.search_memories("Hexagon")
        self.assertEqual(len(npu_results), 1)
        self.assertIn("Qualcomm Hexagon", npu_results[0]["content"])
        vault.close()

    # 8. Importance handling
    def test_08_importance_handling(self):
        self.assertEqual(resolve_importance(5)["stars"], "★★★★★")
        self.assertEqual(resolve_importance(4)["stars"], "★★★★☆")
        self.assertEqual(resolve_importance(3)["stars"], "★★★☆☆")
        self.assertEqual(resolve_importance("PERMANENT")["score"], 5)
        self.assertEqual(resolve_importance("HIGH")["score"], 4)
        self.assertEqual(resolve_importance("PROJECT")["score"], 3)
        self.assertEqual(resolve_importance("LOW")["score"], 1)

        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        mem = vault.add_memory("High importance note.", importance=5)
        self.assertEqual(mem["importance"], 5)
        vault.close()

    # 9. Expiration handling
    def test_09_expiration_handling(self):
        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        vault.add_memory("Expired temporary news item", category="TEMPORARY_NEWS", expires_at=yesterday)
        vault.add_memory("Active temporary news item", category="TEMPORARY_NEWS", expires_at=tomorrow)

        active = vault.list_memories(include_expired=False)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["content"], "Active temporary news item")

        all_mems = vault.list_memories(include_expired=True)
        self.assertEqual(len(all_mems), 2)
        vault.close()

    # 10. JSON -> SQLite migration
    def test_10_json_to_sqlite_migration(self):
        legacy_data = [
            {"id": "m1", "category": "PROJECT_CONTEXT", "content": "Migrated memory 1", "importance": "HIGH"},
            {"id": "m2", "category": "USER_PREFERENCE", "content": "Migrated memory 2", "importance": 4}
        ]
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        vault = LocalMemoryVault(db_path=self.db_path, json_migration_path=self.json_path, auto_migrate=True)
        self.assertEqual(vault.count_memories(), 2)
        self.assertEqual(vault.get_metadata(f"migration.{os.path.basename(self.json_path)}"), "completed")

        # Confirm original JSON file is completely untouched
        self.assertTrue(os.path.exists(self.json_path))
        with open(self.json_path, "r", encoding="utf-8") as f:
            persisted = json.load(f)
        self.assertEqual(len(persisted), 2)
        vault.close()

    # 11. Migration idempotency
    def test_11_migration_idempotency(self):
        legacy_data = [
            {"id": "m1", "category": "PROJECT_CONTEXT", "content": "Idempotent item", "importance": 3}
        ]
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        vault = LocalMemoryVault(db_path=self.db_path, json_migration_path=self.json_path, auto_migrate=True)
        self.assertEqual(vault.count_memories(), 1)

        # Call migration again explicitly
        success, count, msg = vault.migrate_from_json(self.json_path)
        self.assertTrue(success)
        self.assertEqual(count, 0)
        self.assertEqual(vault.count_memories(), 1)
        vault.close()

    # 12. Migration failure safety
    def test_12_migration_failure_safety(self):
        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        # Attempt migration with non-existent file
        success, count, msg = vault.migrate_from_json("non_existent_file.json")
        self.assertFalse(success)
        self.assertEqual(count, 0)

        # Attempt migration with corrupt file
        corrupt_path = os.path.join(self.temp_dir.name, "corrupt.json")
        with open(corrupt_path, "w", encoding="utf-8") as f:
            f.write("{invalid json...")
        success, count, msg = vault.migrate_from_json(corrupt_path)
        self.assertFalse(success)
        self.assertEqual(count, 0)
        vault.close()

    # 13. JSON export
    def test_13_json_export(self):
        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        vault.add_memory("Exportable item 1", category="TASK")
        vault.add_memory("Exportable item 2", category="USER_PREFERENCE")

        exported = vault.export_memories()
        self.assertEqual(len(exported), 2)
        contents = [e["content"] for e in exported]
        self.assertIn("Exportable item 1", contents)
        self.assertIn("Exportable item 2", contents)
        vault.close()

    # 14. JSON import
    def test_14_json_import(self):
        vault = LocalMemoryVault(db_path=self.db_path, auto_migrate=False)
        items = [
            {"content": "Imported item 1", "category": "GENERAL_KNOWLEDGE", "importance": 3},
            {"content": "Imported item 2", "category": "USER_PREFERENCE", "importance": "PERMANENT"}
        ]
        count = vault.import_memories(items)
        self.assertEqual(count, 2)
        self.assertEqual(vault.count_memories(), 2)
        vault.close()

    # 15. Explicit preference extraction
    def test_15_explicit_preference_extraction(self):
        store = LongTermMemoryStore(memory_filepath=self.json_path, db_path=self.db_path)
        extractor = MemoryExtractor(memory_store=store)

        memories = extractor.extract_and_store(
            user_prompt="I prefer dark mode in all code editors.",
            ai_reply="Understood, sir. Dark mode preference noted."
        )
        self.assertGreaterEqual(len(memories), 1)
        self.assertEqual(memories[0]["category"], "USER_PREFERENCE")
        self.assertIn("dark mode", memories[0]["content"])
        store.vault.close()

    # 16. Project-context extraction
    def test_16_project_context_extraction(self):
        store = LongTermMemoryStore(memory_filepath=self.json_path, db_path=self.db_path)
        extractor = MemoryExtractor(memory_store=store)

        memories = extractor.extract_and_store(
            user_prompt="Our project uses Spring Boot 3 and FastAPI.",
            ai_reply="Duly noted. Spring Boot 3 and FastAPI architecture recorded."
        )
        self.assertGreaterEqual(len(memories), 1)
        self.assertEqual(memories[0]["category"], "PROJECT_CONTEXT")
        self.assertIn("Spring Boot 3", memories[0]["content"])
        store.vault.close()

    # 17. Low-confidence conversational text not automatically becoming memory
    def test_17_conversational_text_rejection(self):
        store = LongTermMemoryStore(memory_filepath=self.json_path, db_path=self.db_path)
        extractor = MemoryExtractor(memory_store=store)

        initial_count = store.vault.count_memories()

        # Casual greeting
        mems = extractor.extract_and_store(user_prompt="Hello, how are you today?", ai_reply="I'm functioning at full capacity.")
        self.assertEqual(len(mems), 0)

        # Question without preference
        mems2 = extractor.extract_and_store(user_prompt="What is the weather like in Tokyo?", ai_reply="It is currently sunny.")
        self.assertEqual(len(mems2), 0)

        # Small talk
        mems3 = extractor.extract_and_store(user_prompt="Thanks, cool!", ai_reply="You are welcome.")
        self.assertEqual(len(mems3), 0)

        self.assertEqual(store.vault.count_memories(), initial_count)
        store.vault.close()

    # 18. Secret/API-key rejection
    def test_18_secret_rejection(self):
        store = LongTermMemoryStore(memory_filepath=self.json_path, db_path=self.db_path)
        extractor = MemoryExtractor(memory_store=store)

        initial_count = store.vault.count_memories()

        # Attempt to store Groq API key
        mems1 = extractor.extract_and_store(
            user_prompt="I prefer using gsk_1234567890abcdef1234567890abcdef for authentication.",
            ai_reply="Acknowledged."
        )
        self.assertEqual(len(mems1), 0)

        # Direct add_memory with secret
        added = store.add_memory(
            category="USER_PREFERENCE",
            content="My secret is tvly-abc123secrettoken456"
        )
        self.assertIsNone(added)

        # Attempt with sk- openai pattern
        added2 = store.add_memory(
            category="GENERAL_KNOWLEDGE",
            content="sk-1234567890abcdefghijklmnop"
        )
        self.assertIsNone(added2)

        self.assertEqual(store.vault.count_memories(), initial_count)
        store.vault.close()

    # 19. MemoryExtractor makes zero network calls (monkeypatched network socket)
    def test_19_zero_network_calls_guarantee(self):
        store = LongTermMemoryStore(memory_filepath=self.json_path, db_path=self.db_path)
        extractor = MemoryExtractor(memory_store=store)

        def mock_forbidden_network(*args, **kwargs):
            raise AssertionError("NETWORK VIOLATION: MemoryExtractor attempted a network call!")

        # Monkeypatch socket.socket.connect and urllib.request.urlopen
        with patch.object(socket.socket, "connect", side_effect=mock_forbidden_network), \
             patch.object(urllib.request, "urlopen", side_effect=mock_forbidden_network):

            # Perform multiple extractions across categories
            res1 = extractor.extract_and_store(
                user_prompt="I prefer working with Python 3.11.",
                ai_reply="Preference registered."
            )
            self.assertGreaterEqual(len(res1), 1)

            res2 = extractor.extract_and_store(
                user_prompt="Our project deadline is October 15.",
                ai_reply="Deadline noted."
            )
            self.assertGreaterEqual(len(res2), 1)

            res3 = extractor.extract_and_store(
                user_prompt="Remember to run unit tests before push.",
                ai_reply="Task recorded."
            )
            self.assertGreaterEqual(len(res3), 1)

        store.vault.close()

    # 20. Groq is never invoked by MemoryExtractor
    def test_20_groq_never_invoked(self):
        store = LongTermMemoryStore(memory_filepath=self.json_path, db_path=self.db_path)
        # Pass a fake groq api key
        extractor = MemoryExtractor(memory_store=store, groq_api_key="gsk_fake_key_never_used")

        # Verify no Groq client attribute or network caller exists
        self.assertFalse(hasattr(extractor, "groq_client"))
        self.assertFalse(hasattr(extractor, "client"))
        self.assertEqual(extractor._cloud_calls_made, 0)

        # Run extraction
        extractor.extract_and_store("I prefer using pytest.", "Noted.")
        self.assertEqual(extractor._cloud_calls_made, 0)
        store.vault.close()

    # 21. Existing MemoryManagerModal/API compatibility
    def test_21_modal_api_compatibility(self):
        store = LongTermMemoryStore(memory_filepath=self.json_path, db_path=self.db_path)
        store.add_memory(category="USER_PREFERENCE", content="User prefers TypeScript.", importance="PERMANENT")
        store.add_memory(category="PROJECT_CONTEXT", content="Project backend is Spring Boot.", importance="HIGH")
        store.add_memory(category="GENERAL_KNOWLEDGE", content="Common law fact.", importance="MEDIUM")

        dashboard = store.get_dashboard_categorized()
        self.assertIn("facts", dashboard)
        self.assertIn("preferences", dashboard)
        self.assertIn("longTerm", dashboard)
        self.assertIn("recent", dashboard)
        self.assertIn("totalCount", dashboard)
        self.assertGreaterEqual(dashboard["totalCount"], 3)

        # Check that items contain formatted star ratings for UI modal
        for pref in dashboard["preferences"]:
            self.assertIn("stars", pref)
            self.assertIn("importance_score", pref)
            self.assertIn("importance_label", pref)
            self.assertEqual(pref["stars"], "★★★★★")
            self.assertEqual(pref["importance_score"], 5)

        # Test search through dashboard
        search_res = store.get_dashboard_categorized(query="TypeScript")
        self.assertGreaterEqual(len(search_res["preferences"]), 1)
        store.vault.close()

    # 22. Integration with MemoryRetriever
    def test_22_retriever_integration(self):
        store = LongTermMemoryStore(memory_filepath=self.json_path, db_path=self.db_path)
        store.add_memory(category="PROJECT_CONTEXT", content="AIGIS uses Java Spring Boot on port 8080.", importance="HIGH")
        store.add_memory(category="USER_PREFERENCE", content="User prefers Python for data tasks.", importance="HIGH")

        retriever = MemoryRetriever(memory_store=store)
        proj_ctx, lt_mem = retriever.retrieve_relevant_memories("Tell me about the Spring Boot architecture")

        self.assertIn("RELEVANT PROJECT CONTEXT:", proj_ctx)
        self.assertIn("Spring Boot", proj_ctx)

        proj_ctx2, lt_mem2 = retriever.retrieve_relevant_memories("What programming language do I prefer?")
        self.assertIn("RELEVANT LONG-TERM MEMORY:", lt_mem2)
        self.assertIn("Python", lt_mem2)
        store.vault.close()


if __name__ == "__main__":
    unittest.main()
