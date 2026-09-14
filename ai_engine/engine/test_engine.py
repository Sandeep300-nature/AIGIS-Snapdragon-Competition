import os
import unittest
from ai_engine.engine.base_engine import EngineResponse
from ai_engine.engine.local_engine import LocalEngine
from ai_engine.engine.cloud_engine import CloudEngine
from ai_engine.engine.router import IntentTaskRouter
from ai_engine.engine.slm_pipeline import LocalSLMPipeline
from ai_engine.engine.local_stt import LocalSTTService


class TestModularAIEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Instantiate pipeline and STT service once for efficiency across test suite
        cls.shared_pipeline = LocalSLMPipeline()
        cls.shared_stt = LocalSTTService()

    def setUp(self):
        self.local_engine = LocalEngine(slm_pipeline=self.shared_pipeline)
        self.cloud_engine = CloudEngine(api_key="")  # Unconfigured cloud key for test safety
        self.router = IntentTaskRouter(self.local_engine, self.cloud_engine)
        self.stt_service = self.shared_stt

    def test_local_engine_time_response(self):
        """1. Existing deterministic time query still works."""
        resp = self.local_engine.generate_response("What time is it?")
        self.assertIsInstance(resp, EngineResponse)
        self.assertEqual(resp.engine, "local")
        self.assertIn("Local", resp.badge)
        self.assertIn("current time is", resp.reply.lower())
        self.assertEqual(resp.metadata.get("intent"), "time")
        self.assertGreater(resp.latencyMs, 0)

    def test_local_engine_hardware_inquiry(self):
        """2. Existing hardware query still works."""
        resp = self.local_engine.generate_response("What hardware is this running on?")
        self.assertEqual(resp.engine, "local")
        self.assertIn("Workstation Hardware Telemetry", resp.reply)
        self.assertIn("Architecture", resp.reply)
        self.assertIn("Intel(R) Core(TM)", resp.reply)

    def test_genuine_local_model_inference(self):
        """3. Genuine general-AI prompt produces a generated response from the local model."""
        resp = self.local_engine.generate_response("Explain quantum computing in one sentence.")
        self.assertEqual(resp.engine, "local")
        self.assertIn("SmolLM2-135M-Instruct", resp.provider)
        self.assertIn("quantum", resp.reply.lower())
        self.assertTrue(len(resp.reply) > 20)

    def test_response_is_not_old_generic_template(self):
        """4. The response is NOT the old generic acknowledgement template."""
        resp = self.local_engine.generate_response("Explain quantum computing in one sentence.")
        self.assertNotIn("Acknowledged, sir. Processed locally on this device via", resp.reply)
        self.assertNotIn("Local core is active and operational for:", resp.reply)

    def test_local_mode_does_not_invoke_cloud_or_groq(self):
        """5 & 6. Local mode does not invoke CloudEngine or Groq."""
        resp = self.router.route_and_generate("Explain quantum computing in one sentence.", mode="local")
        self.assertEqual(resp.engine, "local")
        self.assertNotIn("groq", resp.provider.lower())
        self.assertNotIn("cloud", resp.provider.lower())
        self.assertFalse(resp.metadata.get("networkUsed", True))
        self.assertTrue(resp.metadata.get("localInference", False))

    def test_local_model_metadata_identification(self):
        """7. Local model metadata identifies model, runtime, and execution provider."""
        resp = self.local_engine.generate_response("hello")
        self.assertEqual(resp.metadata.get("model"), "SmolLM2-135M-Instruct")
        self.assertEqual(resp.metadata.get("runtime"), "PyTorch (transformers)")
        self.assertEqual(resp.metadata.get("device"), "cpu")
        self.assertGreater(resp.metadata.get("tokensGenerated", 0), 0)
        self.assertGreater(resp.metadata.get("tokensPerSec", 0), 0)

    def test_local_model_unavailable_state_is_truthful(self):
        """8. Local model unavailable state is truthful."""
        class MockUnavailablePipeline:
            model_name = "SmolLM2-135M-Instruct"
            load_error = "Weights file missing"
            def is_available(self):
                return False
            def get_pipeline_info(self):
                return {"loaded": False, "loadError": self.load_error}

        unavail_engine = LocalEngine(slm_pipeline=MockUnavailablePipeline())
        resp = unavail_engine.generate_response("hello")
        self.assertIn("Local SLM is unavailable", resp.reply)
        self.assertFalse(resp.metadata.get("localInference"))
        self.assertEqual(resp.metadata.get("error"), "Weights file missing")

    def test_router_auto_mode_policy(self):
        """9. Auto mode works according to router policy: time is deterministic local, general query is local SLM."""
        time_resp = self.router.route_and_generate("What time is it?", mode="auto")
        self.assertEqual(time_resp.engine, "local")
        self.assertEqual(time_resp.metadata.get("intent"), "time")

        general_resp = self.router.route_and_generate("hello", mode="auto")
        self.assertEqual(general_resp.engine, "local")
        self.assertEqual(general_resp.metadata.get("intent"), "general_ai")
        self.assertIn("SmolLM2-135M-Instruct", general_resp.provider)

    def test_cloud_engine_unconfigured_behavior(self):
        resp = self.cloud_engine.generate_response("Explain quantum computing")
        self.assertEqual(resp.engine, "cloud")
        self.assertIn("Cloud", resp.badge)
        self.assertIn("GROQ_API_KEY", resp.reply)

    def test_router_enforces_cloud_mode(self):
        resp = self.router.route_and_generate("What time is it?", mode="cloud")
        self.assertEqual(resp.engine, "cloud")
        self.assertEqual(resp.metadata.get("routingMode"), "enforced_cloud")

    def test_router_status_metadata(self):
        status = self.router.get_router_status()
        self.assertIn("localEngine", status)
        self.assertIn("cloudEngine", status)
        self.assertEqual(status["supportedModes"], ["auto", "local", "cloud"])
        self.assertIn("slmPipeline", status["localEngine"])
        self.assertEqual(status["localEngine"]["slmPipeline"]["modelName"], "SmolLM2-135M-Instruct")

    def test_action_open_notepad_does_not_invoke_smollm(self):
        """10. 'open notepad' reaches DesktopActionService and does not invoke SmolLM2."""
        resp = self.local_engine.generate_response("open notepad")
        self.assertEqual(resp.engine, "local")
        self.assertIn("Desktop Control", resp.provider)
        self.assertEqual(resp.metadata.get("intent"), "desktop_action")
        self.assertNotIn("SmolLM2", resp.provider)
        self.assertNotIn("SmolLM2", resp.metadata.get("model", ""))

    def test_action_open_youtube_returns_url_and_does_not_invoke_smollm(self):
        """11. 'Can you open YouTube, AIGIS?' returns the correct URL and does not invoke SmolLM2."""
        resp = self.local_engine.generate_response("Can you open YouTube, AIGIS?")
        self.assertEqual(resp.engine, "local")
        self.assertEqual(resp.urlToOpen, "https://www.youtube.com")
        self.assertIn("YouTube", resp.reply)
        self.assertIn("[OPEN_URL: https://www.youtube.com]", resp.reply)
        self.assertEqual(resp.metadata.get("intent"), "web_action")
        self.assertNotIn("SmolLM2", resp.provider)
        self.assertNotIn("SmolLM2", resp.metadata.get("model", ""))

    def test_live_web_query_never_invokes_smollm(self):
        """12. Latest/current information query routes to LIVE_WEB and NEVER invokes SmolLM2."""
        resp = self.router.route_and_generate("Who is the latest IPL winner?", mode="auto")
        self.assertEqual(resp.metadata.get("intent"), "live_web")
        self.assertNotIn("SmolLM2", resp.provider)
        self.assertNotIn("SmolLM2", resp.metadata.get("model", ""))
        self.assertNotEqual(resp.metadata.get("intent"), "general_ai")

    def test_live_web_local_engine_direct_guardrail(self):
        """13. Direct call to LocalEngine for LIVE_WEB blocks SmolLM2 and returns anti-hallucination guard."""
        resp = self.local_engine.generate_response("Who is the latest IPL winner?")
        self.assertEqual(resp.engine, "local")
        self.assertIn("Anti-Hallucination Guard", resp.provider)
        self.assertTrue(resp.metadata.get("liveInfoBlocked"))
        self.assertFalse(resp.metadata.get("localInference"))
        self.assertNotIn("SmolLM2", resp.provider)

    def test_live_search_failure_or_offline_truthful_response(self):
        """14. Live search failure or offline returns truthful inability-to-verify response."""
        from unittest.mock import patch
        with patch("ai_engine.engine.router.search_live_web", return_value={"success": False, "web_context": ""}):
            resp = self.router.route_and_generate("Who is the latest champion?", mode="auto")
            self.assertEqual(resp.metadata.get("intent"), "live_web")
            self.assertIn("cannot verify current or live information", resp.reply)
            self.assertIn("Anti-Hallucination Guard", resp.provider)
            self.assertFalse(resp.metadata.get("webSearchUsed"))

    def test_auto_mode_groq_available_routes_to_cloud(self):
        """15. AUTO mode with Groq available routes general AI to CloudEngine."""
        from unittest.mock import MagicMock
        mock_cloud = MagicMock()
        mock_cloud.get_engine_info.return_value = {"configured": True, "provider": "Groq"}
        mock_cloud.generate_response.return_value = EngineResponse(
            reply="Quantum computing explanation from cloud.",
            provider="Cloud AI -> Groq (llama-3.3-70b-versatile)",
            engine="cloud",
            badge="☁ Cloud (Processed using cloud AI)"
        )
        router_with_cloud = IntentTaskRouter(self.local_engine, mock_cloud)
        resp = router_with_cloud.route_and_generate("Explain quantum computing", mode="auto")
        self.assertEqual(resp.engine, "cloud")
        self.assertIn("Groq", resp.provider)
        mock_cloud.generate_response.assert_called_once()

    def test_explicit_local_mode_blocks_live_web_truthfully(self):
        """16. Explicit LOCAL mode does not invoke web search or SmolLM2 for live web inquiries."""
        resp = self.router.route_and_generate("Who is the latest IPL winner?", mode="local")
        self.assertEqual(resp.engine, "local")
        self.assertIn("Privacy Guard", resp.provider)
        self.assertIn("Local-Only mode", resp.reply)
        self.assertFalse(resp.metadata.get("networkUsed"))
        self.assertFalse(resp.metadata.get("localInference"))

    def test_identity_query_who_are_you_aigis(self):
        """17. 'Who are you, AIGIS?' produces grounded identity referring to AIGIS as the assistant."""
        resp = self.router.route_and_generate("Who are you, AIGIS?", mode="auto")
        self.assertEqual(resp.engine, "local")
        self.assertIn("AIGIS", resp.reply)
        self.assertIn("personal AI", resp.reply)
        self.assertIn(resp.metadata.get("intent"), ["assistant_identity", "SYSTEM_INFO"])
        self.assertNotIn("statistical modeling", resp.reply.lower())

    def test_capability_query_what_can_you_do_aigis(self):
        """18. 'What can you do, AIGIS?' describes actual verified capabilities without hallucination."""
        resp = self.router.route_and_generate("What can you do, AIGIS?", mode="auto")
        self.assertEqual(resp.engine, "local")
        self.assertIn("AIGIS", resp.reply)
        self.assertIn("SmolLM2", resp.reply)
        self.assertIn("Desktop Actions", resp.reply)
        self.assertIn("Live Web Search", resp.reply)
        self.assertIn("Tavily", resp.reply)
        self.assertNotIn("statistical modeling", resp.reply.lower())
        self.assertNotIn("data cleaning", resp.reply.lower())

    def test_capability_query_what_can_you_do(self):
        """19. 'What can you do?' describes actual verified capabilities."""
        resp = self.router.route_and_generate("What can you do?", mode="auto")
        self.assertEqual(resp.engine, "local")
        self.assertIn("AIGIS", resp.reply)
        self.assertIn("SmolLM2", resp.reply)
        self.assertIn("Desktop Actions", resp.reply)
        self.assertNotIn("statistical modeling", resp.reply.lower())

    def test_capability_query_tell_me_about_yourself(self):
        """20. 'Tell me about yourself.' provides grounded assistant introduction & capabilities."""
        resp = self.router.route_and_generate("Tell me about yourself.", mode="auto")
        self.assertEqual(resp.engine, "local")
        self.assertIn("AIGIS", resp.reply)
        self.assertIn("SmolLM2", resp.reply)
        self.assertNotIn("statistical modeling", resp.reply.lower())

    # =========================================================================
    # MILESTONE 5: LOCAL VOICE ASSISTANT TESTS
    # =========================================================================

    def test_m5_local_stt_service_initialization_and_metadata(self):
        """21. faster-whisper tiny.en service initializes correctly and exposes truthful metadata."""
        self.assertTrue(self.stt_service.is_available())
        info = self.stt_service.get_service_info()
        self.assertEqual(info.get("provider"), "faster-whisper")
        self.assertEqual(info.get("model"), "tiny.en")
        self.assertEqual(info.get("runtime"), "CTranslate2")
        self.assertEqual(info.get("device"), "cpu")
        self.assertIn(info.get("computeType"), ["int8", "float32"])
        self.assertFalse(info.get("networkUsed"))
        self.assertTrue(info.get("localInference"))
        self.assertIsNone(info.get("error"))

    def test_m5_local_stt_transcription_from_controlled_audio(self):
        """22. Local faster-whisper STT returns accurate transcript from controlled audio sample."""
        audio_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "test_sample.wav")
        self.assertTrue(os.path.exists(audio_path), f"Audio fixture missing at {audio_path}")

        res = self.stt_service.transcribe(audio_path)
        self.assertTrue(res.get("success"))
        self.assertFalse(res.get("networkUsed"))
        self.assertTrue(res.get("localInference"))
        self.assertFalse(res.get("isFallback"))
        self.assertEqual(res.get("provider"), "faster-whisper")
        self.assertEqual(res.get("model"), "tiny.en")
        self.assertGreater(res.get("latencyMs", 0), 0)
        self.assertGreater(res.get("audioDurationSec", 0), 0)

        # Confirm transcript accuracy on the controlled sample ("What time is it?")
        transcript = res.get("transcript", "").strip()
        self.assertIn("time", transcript.lower())

    def test_m5_voice_transcript_routes_to_deterministic_time(self):
        """23. Voice transcript reaches router and deterministic time query still routes locally."""
        audio_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "test_sample.wav")
        res = self.stt_service.transcribe(audio_path)
        voice_transcript = res.get("transcript", "")

        resp = self.router.route_and_generate(voice_transcript, mode="auto")
        self.assertEqual(resp.engine, "local")
        self.assertIn("Local", resp.badge)
        self.assertIn("current time is", resp.reply.lower())
        self.assertFalse(resp.metadata.get("networkUsed"))

    def test_m5_voice_transcript_routes_to_desktop_action(self):
        """24. Voice transcript for desktop action executes locally and does not invoke SmolLM2."""
        voice_transcript = "Can you open YouTube, AIGIS?"
        resp = self.router.route_and_generate(voice_transcript, mode="auto")
        self.assertEqual(resp.engine, "local")
        self.assertIn("youtube.com", resp.urlToOpen or "")
        self.assertIn(resp.metadata.get("intent"), ["ACTION", "web_action", "desktop_action"])
        self.assertFalse(resp.metadata.get("localInference"))

    def test_m5_voice_transcript_routes_to_live_web_avoiding_smollm2(self):
        """25. Voice transcript for live web query avoids SmolLM2 to prevent hallucinations."""
        voice_transcript = "Who is the latest IPL winner?"
        classification = self.router.classify_intent(voice_transcript)
        self.assertEqual(classification["intent"], "LIVE_WEB")
        self.assertEqual(classification["preferredEngine"], "live_web")


if __name__ == "__main__":
    unittest.main()

