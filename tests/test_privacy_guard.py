import os
import sys
import unittest
from unittest.mock import MagicMock

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

ai_engine_dir = os.path.join(project_root, "ai_engine")
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)

from ai_engine.privacy.privacy_guard import (
    PrivacyGuard,
    PrivacyMode,
    ContentSensitivity,
    PrivateIntent,
    ContentClassifier,
    ContextFilterResult,
    ContextBundle,
)
from ai_engine.engine.base_engine import EngineResponse
from ai_engine.engine.router import IntentTaskRouter


class TestContentClassifier(unittest.TestCase):
    """Category 1: ContentClassifier (7 tests)"""

    def test_classify_public_text_is_public(self):
        self.assertEqual(
            ContentClassifier.classify("What is the boiling point of water?"),
            ContentSensitivity.PUBLIC
        )
        self.assertEqual(
            ContentClassifier.classify("Write a Python script to parse CSV files."),
            ContentSensitivity.PUBLIC
        )

    def test_classify_memory_prefix_is_private(self):
        self.assertEqual(
            ContentClassifier.classify("RETRIEVED MEMORY: User prefers concise answers."),
            ContentSensitivity.PRIVATE
        )
        self.assertEqual(
            ContentClassifier.classify("[MEMORY] User lives in California."),
            ContentSensitivity.PRIVATE
        )

    def test_classify_project_context_prefix_is_private(self):
        self.assertEqual(
            ContentClassifier.classify("PROJECT CONTEXT: AIGIS desktop architecture."),
            ContentSensitivity.PRIVATE
        )
        self.assertEqual(
            ContentClassifier.classify("[PROJECT] Microservices backend with Spring Boot."),
            ContentSensitivity.PRIVATE
        )

    def test_classify_document_chunk_is_private(self):
        self.assertEqual(
            ContentClassifier.classify("[Document Chunk (Score: 0.92)]: Confidential financial summary."),
            ContentSensitivity.PRIVATE
        )
        self.assertEqual(
            ContentClassifier.classify("[DOCUMENT CHUNK]: API reference notes from local PDF."),
            ContentSensitivity.PRIVATE
        )

    def test_classify_api_key_is_secret(self):
        self.assertEqual(
            ContentClassifier.classify("api_key = gsk_1234567890abcdef1234567890"),
            ContentSensitivity.SECRET
        )
        self.assertEqual(
            ContentClassifier.classify("openai_key: sk-1234567890abcdef1234567890"),
            ContentSensitivity.SECRET
        )
        self.assertEqual(
            ContentClassifier.classify("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token"),
            ContentSensitivity.SECRET
        )

    def test_classify_empty_string_is_public(self):
        self.assertEqual(ContentClassifier.classify(""), ContentSensitivity.PUBLIC)
        self.assertEqual(ContentClassifier.classify("   "), ContentSensitivity.PUBLIC)
        self.assertEqual(ContentClassifier.classify(None), ContentSensitivity.PUBLIC)

    def test_classify_rag_index_is_private(self):
        self.assertEqual(
            ContentClassifier.classify("RETRIEVED DOCUMENT INDEX (TOP RELEVANT CHUNKS):\n[file.txt]: text"),
            ContentSensitivity.PRIVATE
        )


class TestIntentClassifier(unittest.TestCase):
    """Category 2: Intent Classifier (6 tests)"""

    def test_intent_what_do_you_remember(self):
        self.assertEqual(
            ContentClassifier.classify_intent("what do you remember"),
            PrivateIntent.MEMORY_QUERY
        )
        self.assertEqual(
            ContentClassifier.classify_intent("what do you remember about my project?"),
            PrivateIntent.MEMORY_QUERY
        )

    def test_intent_what_do_you_know_about_me(self):
        self.assertEqual(
            ContentClassifier.classify_intent("what do you know about me"),
            PrivateIntent.MEMORY_QUERY
        )
        self.assertEqual(
            ContentClassifier.classify_intent("do you know about me and my preferences?"),
            PrivateIntent.MEMORY_QUERY
        )

    def test_intent_search_my_files(self):
        self.assertEqual(
            ContentClassifier.classify_intent("search my files for Q4 roadmap"),
            PrivateIntent.DOCUMENT_QUERY
        )
        self.assertEqual(
            ContentClassifier.classify_intent("search files for invoice.pdf"),
            PrivateIntent.DOCUMENT_QUERY
        )

    def test_intent_find_in_documents(self):
        self.assertEqual(
            ContentClassifier.classify_intent("find in my documents the tax return"),
            PrivateIntent.DOCUMENT_QUERY
        )
        self.assertEqual(
            ContentClassifier.classify_intent("look in documents for the architecture draft"),
            PrivateIntent.DOCUMENT_QUERY
        )

    def test_intent_my_project_status(self):
        self.assertEqual(
            ContentClassifier.classify_intent("my project status"),
            PrivateIntent.PRIVATE_PROJECT_QUERY
        )
        self.assertEqual(
            ContentClassifier.classify_intent("what is our architecture pattern?"),
            PrivateIntent.PRIVATE_PROJECT_QUERY
        )

    def test_intent_general_python_question_is_public(self):
        self.assertEqual(
            ContentClassifier.classify_intent("how to reverse a list in Python"),
            PrivateIntent.PUBLIC
        )
        self.assertEqual(
            ContentClassifier.classify_intent("explain quantum computing in one sentence"),
            PrivateIntent.PUBLIC
        )


class TestPrivacyGuardCore(unittest.TestCase):
    """Category 3: PrivacyGuard Core (7 tests)"""

    def test_guard_auto_blocks_long_memory_from_cloud(self):
        guard = PrivacyGuard(mode=PrivacyMode.AUTO)
        res = guard.filter_context_for_cloud(long_mem="User prefers concise replies.")
        self.assertEqual(res.long_memory, "")
        self.assertEqual(res.safe_long_mem, "")
        self.assertEqual(res[1], "")

    def test_guard_auto_blocks_proj_context_from_cloud(self):
        guard = PrivacyGuard(mode=PrivacyMode.AUTO)
        res = guard.filter_context_for_cloud(proj_ctx="Proprietary algorithm specification.")
        self.assertEqual(res.proj_context, "")
        self.assertEqual(res.safe_proj_ctx, "")
        self.assertEqual(res[0], "")

    def test_guard_auto_blocks_rag_from_cloud(self):
        guard = PrivacyGuard(mode=PrivacyMode.AUTO)
        res = guard.filter_context_for_cloud(rag_ctx="Confidential client proposal chunk.")
        self.assertEqual(res.rag_context, "")
        self.assertEqual(res.safe_rag, "")
        self.assertEqual(res[2], "")

    def test_guard_local_only_passes_all_context(self):
        guard = PrivacyGuard(mode=PrivacyMode.LOCAL_ONLY)
        bundle = guard.build_context_for_request(
            prompt="summarize notes",
            engine_type="local",
            proj_ctx="Project Alpha",
            long_mem="User works in DevOps",
            rag_ctx="Chunk 1: Setup guide"
        )
        self.assertEqual(bundle.proj_context, "Project Alpha")
        self.assertEqual(bundle.long_memory, "User works in DevOps")
        self.assertEqual(bundle.rag_context, "Chunk 1: Setup guide")
        self.assertTrue(bundle.private_context_used)
        self.assertTrue(bundle.allowed)

        filtered = guard.filter_context(
            proj_ctx="Project Alpha",
            long_mem="User works in DevOps",
            rag_ctx="Chunk 1: Setup guide",
            engine_type="local"
        )
        self.assertEqual(filtered.proj_context, "Project Alpha")
        self.assertEqual(filtered.long_memory, "User works in DevOps")
        self.assertEqual(filtered.rag_context, "Chunk 1: Setup guide")

    def test_guard_cloud_permitted_allows_non_secret_memory(self):
        guard = PrivacyGuard(mode=PrivacyMode.CLOUD_PERMITTED)
        res = guard.filter_context_for_cloud(
            long_mem="User prefers technical terminology."
        )
        self.assertEqual(res.long_memory, "User prefers technical terminology.")

    def test_guard_cloud_permitted_strips_secret_api_keys(self):
        guard = PrivacyGuard(mode=PrivacyMode.CLOUD_PERMITTED)
        raw_context = "Here is the key: sk-abcdef1234567890abcdef1234567890 for API calls."
        res = guard.filter_context_for_cloud(long_mem=raw_context)
        self.assertNotIn("sk-abcdef1234567890abcdef1234567890", res.long_memory)
        self.assertIn("[REDACTED_SECRET]", res.long_memory)

    def test_guard_empty_context_returns_empty_safe(self):
        guard = PrivacyGuard(mode=PrivacyMode.AUTO)
        res = guard.filter_context_for_cloud("", "", "")
        self.assertEqual(res.proj_context, "")
        self.assertEqual(res.long_memory, "")
        self.assertEqual(res.rag_context, "")


class TestRouterPrivacyIntegration(unittest.TestCase):
    """Category 4: Router Privacy Integration (4 tests)"""

    def setUp(self):
        self.mock_local = MagicMock()
        self.mock_local.generate_response.return_value = EngineResponse(
            reply="Local engine processed response.",
            provider="AIGIS Local Mock",
            engine="local",
            badge="⚡ AIGIS Local",
            latencyMs=5,
            metadata={"model": "SmolLM2-135M-Instruct"}
        )
        self.mock_local.get_engine_info.return_value = {"configured": True, "provider": "Local"}

        self.mock_cloud = MagicMock()
        self.mock_cloud.generate_response.return_value = EngineResponse(
            reply="Cloud engine processed response.",
            provider="AIGIS Cloud Mock",
            engine="cloud",
            badge="☁ Cloud",
            latencyMs=120,
            metadata={"model": "Llama-3.3-70b-Versatile", "statusCode": 200}
        )
        self.mock_cloud.get_engine_info.return_value = {"configured": True, "provider": "Groq"}

        self.router = IntentTaskRouter(
            local_engine=self.mock_local,
            cloud_engine=self.mock_cloud
        )

    def test_router_memory_query_routes_local(self):
        classification = self.router.classify_intent("what do you remember about me?")
        self.assertEqual(classification["intent"], "MEMORY_QUERY")
        self.assertEqual(classification["preferredEngine"], "local")

        resp = self.router.route_and_generate("what do you remember about me?")
        self.assertEqual(resp.engine, "local")
        self.assertFalse(resp.metadata.get("networkUsed", True))
        self.assertEqual(resp.metadata.get("privacyIntent"), "MEMORY_QUERY")
        self.mock_local.generate_response.assert_called_once()
        self.mock_cloud.generate_response.assert_not_called()

    def test_router_document_query_routes_local(self):
        classification = self.router.classify_intent("search my files for notes")
        self.assertEqual(classification["intent"], "DOCUMENT_QUERY")
        self.assertEqual(classification["preferredEngine"], "local")

        resp = self.router.route_and_generate("search my files for notes")
        self.assertEqual(resp.engine, "local")
        self.assertFalse(resp.metadata.get("networkUsed", True))
        self.assertEqual(resp.metadata.get("privacyIntent"), "DOCUMENT_QUERY")
        self.mock_local.generate_response.assert_called_once()
        self.mock_cloud.generate_response.assert_not_called()

    def test_router_project_query_routes_local(self):
        classification = self.router.classify_intent("what is my project architecture?")
        self.assertEqual(classification["intent"], "PRIVATE_PROJECT_QUERY")
        self.assertEqual(classification["preferredEngine"], "local")

        resp = self.router.route_and_generate("what is my project architecture?")
        self.assertEqual(resp.engine, "local")
        self.assertFalse(resp.metadata.get("networkUsed", True))
        self.assertEqual(resp.metadata.get("privacyIntent"), "PRIVATE_PROJECT_QUERY")
        self.mock_local.generate_response.assert_called_once()
        self.mock_cloud.generate_response.assert_not_called()

    def test_router_general_ai_cloud_no_private_context_leak(self):
        resp = self.router.route_and_generate(
            prompt="Explain quantum computing in one sentence",
            memory_context="Confidential user memory: User has $50k in account.",
            doc_context="Confidential document chunk: Project secret code.",
            mode="auto",
            privacy_mode="AUTO"
        )
        self.mock_cloud.generate_response.assert_called_once()
        cloud_call_args = self.mock_cloud.generate_response.call_args
        prompt_passed_to_cloud = cloud_call_args[1].get("prompt", cloud_call_args[0][0] if cloud_call_args[0] else "")
        self.assertNotIn("Confidential user memory", prompt_passed_to_cloud)
        self.assertNotIn("Confidential document chunk", prompt_passed_to_cloud)
        self.assertFalse(resp.metadata.get("privateContextUsed", True))


class TestProvenanceMetadata(unittest.TestCase):
    """Category 5: Provenance Metadata (2 tests)"""

    def test_provenance_metadata_contains_privacy_mode_key(self):
        guard = PrivacyGuard(mode=PrivacyMode.AUTO)
        meta = guard.create_provenance_metadata(
            engine_type="local",
            private_context_used=False,
            privacy_mode=PrivacyMode.AUTO,
            network_used=False
        )
        self.assertIn("privacyMode", meta)
        self.assertEqual(meta["privacyMode"], "AUTO")

    def test_provenance_metadata_network_used_false_local(self):
        guard = PrivacyGuard(mode=PrivacyMode.LOCAL_ONLY)
        meta = guard.create_provenance_metadata(
            engine_type="local",
            private_context_used=True,
            privacy_mode=PrivacyMode.LOCAL_ONLY,
            network_used=False,
            privacy_intent="MEMORY_QUERY"
        )
        self.assertIn("networkUsed", meta)
        self.assertFalse(meta["networkUsed"])
        self.assertTrue(meta["privateContextUsed"])
        self.assertEqual(meta["privacyIntent"], "MEMORY_QUERY")


if __name__ == "__main__":
    unittest.main()
