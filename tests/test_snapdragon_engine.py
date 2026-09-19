import os
import sys
import unittest
import tempfile
from unittest.mock import MagicMock, patch

# Add project root and ai_engine to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ai_engine_dir = os.path.join(project_root, "ai_engine")
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)

from ai_engine.snapdragon_engine import (
    SnapdragonNPUEngine,
    SnapdragonConfig,
    HardwareNotSupportedError,
    BaseEngine,
    QualcommModelRunner,
    SnapdragonRuntimeState,
    SnapdragonCapabilityReport
)
from ai_engine.engine.genie_provider import GenieQwenProvider, GenieRuntimeAdapter
from ai_engine.engine.base_engine import BaseAIEngine, EngineResponse
from ai_engine.engine.local_engine import LocalEngine
from ai_engine.engine.cloud_engine import CloudEngine
from ai_engine.engine.router import IntentTaskRouter, SmolLM2Engine, GroqEngine
from ai_engine.hardware.detector import HardwareDetector


class TestSnapdragonEngineSuite(unittest.TestCase):
    """
    Comprehensive test suite for Snapdragon Competition Architecture:
    - Verifies SnapdragonNPUEngine abstraction and QualcommModelRunner adapter.
    - Validates verified Qwen3-4B-Instruct-2507 W4A16 GenieX-QAIRT model configuration.
    - Validates strict 6-state runtime capability detection without collapsing to a boolean.
    - Validates 4-shard bundle artifact discovery mechanism.
    - Validates modular GenieRuntimeAdapter boundary (zero fabrication, no unverified import genie).
    - Validates ChatML prompt tokenization format.
    - Verifies polymorphic router hierarchy (Tier 1 Snapdragon NPU, Tier 2 SmolLM2 CPU fallback).
    - Verifies Competition Mode enforcement (strictly local-only, zero cloud fallback).
    - Verifies non-regression of desktop actions, live web anti-hallucination, and deterministic clock.
    """

    def setUp(self):
        self.engine = SnapdragonNPUEngine(hardware_detector=HardwareDetector)
        self.router = IntentTaskRouter(hardware_detector=HardwareDetector, competition_mode=True)

    def test_1_engine_contract_inheritance(self):
        """1. Validates that SnapdragonNPUEngine strictly conforms to BaseAIEngine and BaseEngine."""
        self.assertIsInstance(self.engine, BaseAIEngine)
        self.assertTrue(issubclass(SnapdragonNPUEngine, BaseEngine))
        self.assertTrue(issubclass(SnapdragonNPUEngine, BaseAIEngine))

    def test_2_default_configuration_schema(self):
        """2. Verifies candidate model config strictly targets Qwen3-4B-Instruct-2507 W4A16 GenieX-QAIRT."""
        config = self.engine.config
        self.assertEqual(config.model_id, "qwen3_4b_instruct_2507")
        self.assertEqual(config.checkpoint, "DEFAULT_W4A16")
        self.assertEqual(config.quantization, "w4a16")
        self.assertEqual(config.runtime, "GenieX-QAIRT")
        self.assertEqual(config.execution_provider, "QnnHtp")
        self.assertEqual(config.target_soc, "Snapdragon X Elite / X Plus")
        self.assertEqual(config.target_accelerator, "Qualcomm Hexagon NPU")
        self.assertEqual(config.context_length, 4096)

    def test_3_current_x86_host_state_hardware_unavailable(self):
        """3. Zero fabrication: on current x86 Intel development machine, state must be HARDWARE_UNAVAILABLE."""
        report = self.engine.get_capability_report()
        self.assertEqual(report.state, SnapdragonRuntimeState.HARDWARE_UNAVAILABLE)
        self.assertFalse(report.is_available)
        self.assertFalse(report.hardware_valid)
        self.assertFalse(report.simulated)
        self.assertIn("non-arm64", report.state_description.lower())
        self.assertFalse(self.engine.is_available())

    def test_4_simulated_arm64_missing_qnn_state(self):
        """4. Simulated ARM64 host with missing QNN EP must yield QNN_UNAVAILABLE."""
        mock_detector = MagicMock()
        mock_detector.get_capabilities.return_value = {
            "architecture": "arm64",
            "cpu": {"brand": "Snapdragon X Elite", "isSnapdragon": True},
            "accelerators": {
                "qnn": {"providerAvailable": False, "dllsFound": [], "hasDllsInPath": False},
                "snapdragonNpu": {"detected": True, "npuAccelerated": False}
            },
            "onnxruntime": {"availableProviders": ["CPUExecutionProvider"]}
        }

        runner = QualcommModelRunner(hardware_detector=mock_detector)
        report = runner.inspect_capabilities()
        self.assertEqual(report.state, SnapdragonRuntimeState.QNN_UNAVAILABLE)
        self.assertFalse(report.is_available)
        self.assertIn("qnn", report.state_description.lower())

    def test_5_simulated_arm64_missing_runtime_dlls_state(self):
        """5. Simulated ARM64 with QNN EP registered but missing Genie runtime must yield RUNTIME_INCOMPLETE."""
        mock_detector = MagicMock()
        mock_detector.get_capabilities.return_value = {
            "architecture": "arm64",
            "cpu": {"brand": "Snapdragon X Elite", "isSnapdragon": True},
            "accelerators": {
                "qnn": {"providerAvailable": True, "dllsFound": ["QnnHtp.dll", "QnnSystem.dll"], "hasDllsInPath": True},
                "snapdragonNpu": {"detected": True, "npuAccelerated": True}
            },
            "onnxruntime": {"availableProviders": ["QNNExecutionProvider", "CPUExecutionProvider"]}
        }

        mock_adapter = MagicMock(spec=GenieRuntimeAdapter)
        mock_adapter.is_runtime_present = False

        runner = QualcommModelRunner(
            hardware_detector=mock_detector,
            runtime_adapter=mock_adapter
        )
        report = runner.inspect_capabilities()
        self.assertEqual(report.state, SnapdragonRuntimeState.RUNTIME_INCOMPLETE)
        self.assertFalse(report.is_available)
        self.assertIn("genie runtime is missing", report.state_description.lower())

    def test_6_simulated_arm64_missing_model_artifact_state(self):
        """6. Simulated hardware + runtime present, but missing model bundle must yield MODEL_ARTIFACT_UNAVAILABLE."""
        mock_detector = MagicMock()
        mock_detector.get_capabilities.return_value = {
            "architecture": "arm64",
            "cpu": {"brand": "Snapdragon X Elite", "isSnapdragon": True},
            "accelerators": {
                "qnn": {"providerAvailable": True, "dllsFound": ["QnnHtp.dll", "QnnSystem.dll"], "hasDllsInPath": True},
                "snapdragonNpu": {"detected": True, "npuAccelerated": True}
            },
            "onnxruntime": {"availableProviders": ["QNNExecutionProvider", "CPUExecutionProvider"]}
        }

        mock_adapter = MagicMock(spec=GenieRuntimeAdapter)
        mock_adapter.is_runtime_present = True

        non_existent_model_dir = os.path.join(tempfile.gettempdir(), "non_existent_qwen3_bundle_dir_xyz")
        runner = QualcommModelRunner(
            model_dir=non_existent_model_dir,
            hardware_detector=mock_detector,
            runtime_adapter=mock_adapter
        )
        report = runner.inspect_capabilities()
        self.assertEqual(report.state, SnapdragonRuntimeState.MODEL_ARTIFACT_UNAVAILABLE)
        self.assertFalse(report.is_available)
        self.assertIn("missing", report.state_description.lower())

    def test_7_simulated_fully_configured_state(self):
        """7. Simulated ARM64 + QNN + Genie Runtime + 4-Shard Model Bundle must yield FULLY_CONFIGURED."""
        mock_detector = MagicMock()
        mock_detector.get_capabilities.return_value = {
            "architecture": "arm64",
            "cpu": {"brand": "Snapdragon X Elite", "isSnapdragon": True},
            "accelerators": {
                "qnn": {"providerAvailable": True, "dllsFound": ["QnnHtp.dll", "QnnSystem.dll"], "hasDllsInPath": True},
                "snapdragonNpu": {"detected": True, "npuAccelerated": True}
            },
            "onnxruntime": {"availableProviders": ["QNNExecutionProvider", "CPUExecutionProvider"]}
        }

        mock_adapter = MagicMock(spec=GenieRuntimeAdapter)
        mock_adapter.is_runtime_present = True

        # Create temporary mock 4-shard Qwen3 Genie bundle directory
        with tempfile.TemporaryDirectory() as temp_model_dir:
            with open(os.path.join(temp_model_dir, "genie_config.json"), "w") as f:
                f.write('{"model": "qwen3_4b_instruct_2507"}')
            for i in range(1, 5):
                with open(os.path.join(temp_model_dir, f"part{i}_of_4.bin"), "wb") as f:
                    f.write(b"mock context binary shard")

            runner = QualcommModelRunner(
                model_dir=temp_model_dir,
                hardware_detector=mock_detector,
                runtime_adapter=mock_adapter
            )
            report = runner.inspect_capabilities()
            self.assertEqual(report.state, SnapdragonRuntimeState.FULLY_CONFIGURED)
            self.assertTrue(report.is_available)
            self.assertTrue(report.hardware_valid)
            self.assertFalse(report.simulated)

            arm_engine = SnapdragonNPUEngine(
                hardware_detector=mock_detector,
                runner=runner
            )
            self.assertTrue(arm_engine.is_available())

    def test_8_hardware_not_supported_error_when_fallback_disabled(self):
        """8. If fallback is disabled on an unsupported host, HardwareNotSupportedError must be raised."""
        with self.assertRaises(HardwareNotSupportedError) as ctx:
            self.engine.generate_response("Explain quantum computing.", fallback=False)
        self.assertIn("Snapdragon NPU inference requested, but host is not supported", str(ctx.exception))

        with self.assertRaises(HardwareNotSupportedError):
            list(self.engine.generate_stream("Stream test", fallback=False))

    def test_9_fallback_delegation_provenance_on_x86(self):
        """9. Verifies fallback to SmolLM2 produces truthful provenance tags."""
        mock_fallback = MagicMock(spec=BaseAIEngine)
        mock_fallback.generate_response.return_value = EngineResponse(
            reply="SmolLM2 fallback reply.",
            provider="AIGIS Local Engine -> SmolLM2-135M",
            engine="local",
            badge="⚡ AIGIS Local (SmolLM2 Fallback)",
            latencyMs=40,
            metadata={"runtime": "PyTorch-CPU"}
        )

        engine_with_fallback = SnapdragonNPUEngine(
            hardware_detector=HardwareDetector,
            fallback_engine=mock_fallback,
            auto_fallback=True
        )

        resp = engine_with_fallback.generate_response("Hello AIGIS", session_id="test-session")
        mock_fallback.generate_response.assert_called_once()
        self.assertEqual(resp.reply, "SmolLM2 fallback reply.")
        
        # Verify provenance tags
        self.assertTrue(resp.metadata.get("snapdragon_requested"))
        self.assertEqual(resp.metadata.get("engine"), "snapdragon_npu")
        self.assertEqual(resp.metadata.get("target"), "Qualcomm Hexagon NPU")
        self.assertEqual(resp.metadata.get("model"), "qwen3_4b_instruct_2507-w4a16")
        self.assertEqual(resp.metadata.get("checkpoint"), "DEFAULT_W4A16")
        self.assertEqual(resp.metadata.get("runtime"), "GenieX-QAIRT")
        self.assertEqual(resp.metadata.get("executionProvider"), "QnnHtp")
        self.assertFalse(resp.metadata.get("simulated"))
        self.assertFalse(resp.metadata.get("hardware_valid"))
        self.assertTrue(resp.metadata.get("fallback_triggered"))
        self.assertEqual(resp.metadata.get("fallback_state"), SnapdragonRuntimeState.HARDWARE_UNAVAILABLE.value)

    def test_10_router_hierarchy_x86_defaults_to_smollm2(self):
        """10. On x86_64, the router cleanly defaults local execution to SmolLM2."""
        active_local = self.router.get_active_local_engine()
        self.assertEqual(active_local, self.router.local_engine)

        status = self.router.get_router_status()
        self.assertEqual(status["activeLocalBackend"], "smollm2_cpu")
        self.assertIsNotNone(status["snapdragonEngine"])
        self.assertFalse(status["snapdragonEngine"]["available"])
        self.assertEqual(status["snapdragonEngine"]["state"], SnapdragonRuntimeState.HARDWARE_UNAVAILABLE.value)

    def test_11_router_hierarchy_arm64_routes_to_snapdragon(self):
        """11. On verified fully-configured ARM64, router automatically engages Snapdragon NPU."""
        mock_snapdragon = MagicMock(spec=SnapdragonNPUEngine)
        mock_snapdragon.is_available.return_value = True
        mock_snapdragon.get_engine_info.return_value = {
            "engine": "snapdragon_npu",
            "state": "fully_configured",
            "available": True
        }

        mock_detector = MagicMock()
        mock_detector.get_capabilities.return_value = {"architecture": "arm64"}

        router_arm64 = IntentTaskRouter(
            hardware_detector=mock_detector,
            snapdragon_engine=mock_snapdragon,
            competition_mode=True
        )

        active_local = router_arm64.get_active_local_engine()
        self.assertEqual(active_local, mock_snapdragon)

        status = router_arm64.get_router_status()
        self.assertEqual(status["activeLocalBackend"], "snapdragon_npu")

    def test_12_explicit_local_mode_is_cloud_free(self):
        """12. Explicit LOCAL mode must never invoke cloud services or network egress."""
        resp = self.router.route_and_generate("Explain quantum computing in one sentence", mode="local")
        self.assertEqual(resp.engine, "local")
        self.assertFalse(resp.metadata.get("networkUsed", False))

    def test_13_explicit_cloud_mode_is_cloud_only(self):
        """13. Explicit CLOUD mode (with competition mode disabled) routes to cloud."""
        cloud_router = IntentTaskRouter(
            hardware_detector=HardwareDetector,
            competition_mode=False
        )
        resp = cloud_router.route_and_generate("Explain quantum computing in one sentence", mode="cloud")
        self.assertEqual(resp.engine, "cloud")
        self.assertEqual(resp.metadata.get("routingMode"), "enforced_cloud")

    def test_14_existing_desktop_actions_functional(self):
        """14. Desktop actions must execute deterministically on-device."""
        resp = self.router.route_and_generate("open notepad")
        self.assertEqual(resp.engine, "local")
        self.assertIn("Notepad", resp.reply)
        self.assertFalse(resp.metadata.get("networkUsed", False))

    def test_15_existing_live_web_anti_hallucination_guard(self):
        """15. Anti-hallucination guard must block local SLM from answering live/current queries in local mode."""
        resp = self.router.route_and_generate("Who is the latest IPL winner?", mode="local")
        self.assertTrue(
            "cannot be verified in local-only mode" in resp.reply.lower() or
            "cannot be verified in competition local-only mode" in resp.reply.lower()
        )
        self.assertFalse(resp.metadata.get("verified", False))

    def test_16_existing_deterministic_system_queries(self):
        """16. Deterministic system queries must resolve immediately on-device."""
        resp = self.router.route_and_generate("What time is it?")
        self.assertEqual(resp.engine, "local")
        self.assertIn("current time is", resp.reply.lower())
        self.assertEqual(resp.metadata.get("intent"), "time")
        self.assertLessEqual(resp.latencyMs, 500)

    def test_17_qwen3_chatml_prompt_formatting(self):
        """17. Verifies ChatML prompt tokenization format conforms to Qwen3."""
        provider = GenieQwenProvider()
        formatted = provider.format_chatml_prompt("What is Snapdragon X Elite?")
        self.assertIn("<|im_start|>system", formatted)
        self.assertIn("<|im_end|>", formatted)
        self.assertIn("<|im_start|>user\nWhat is Snapdragon X Elite?<|im_end|>", formatted)
        self.assertTrue(formatted.endswith("<|im_start|>assistant\n"))

        # Multi-turn messages format
        messages = [
            {"role": "user", "content": "Hello AIGIS"},
            {"role": "assistant", "content": "Hello sir, how may I assist?"},
            {"role": "user", "content": "Give me a status report"}
        ]
        multi_formatted = provider.format_chatml_prompt(messages)
        self.assertIn("<|im_start|>user\nHello AIGIS<|im_end|>", multi_formatted)
        self.assertIn("<|im_start|>assistant\nHello sir, how may I assist?<|im_end|>", multi_formatted)
        self.assertIn("<|im_start|>user\nGive me a status report<|im_end|>", multi_formatted)
        self.assertTrue(multi_formatted.endswith("<|im_start|>assistant\n"))

    def test_18_competition_mode_enforces_local_only_with_no_cloud_fallback(self):
        """18. Verifies Competition Mode strictly enforces on-device execution with zero cloud fallback."""
        router = IntentTaskRouter(hardware_detector=HardwareDetector, competition_mode=True)
        self.assertTrue(router.competition_mode)

        # Even if mode="cloud" is requested, competition mode forces local
        resp = router.route_and_generate("Write an essay on AI", mode="cloud")
        self.assertEqual(resp.engine, "local")
        self.assertFalse(resp.metadata.get("networkUsed", True))
        self.assertTrue(resp.metadata.get("competitionMode", False))
        self.assertEqual(resp.metadata.get("routingMode"), "competition_local_enforced")

        # Live web queries are held local without external egress
        web_resp = router.route_and_generate("Latest news today", mode="auto")
        self.assertEqual(web_resp.engine, "local")
        self.assertFalse(web_resp.metadata.get("networkUsed", True))
        self.assertIn("competition local-only mode", web_resp.reply.lower())

    def test_19_configurable_model_dir(self):
        """19. Verifies AIGIS_GENIE_MODEL_DIR environment variable is respected."""
        custom_path = r"C:\Custom\GenieModels\Qwen3"
        with patch.dict(os.environ, {"AIGIS_GENIE_MODEL_DIR": custom_path}):
            provider = GenieQwenProvider()
            self.assertEqual(provider.model_dir, custom_path)

            runner = QualcommModelRunner()
            self.assertEqual(runner.model_dir, custom_path)

    def test_20_modular_runtime_adapter_boundary(self):
        """20. Verifies GenieRuntimeAdapter modular boundary: no unverified import genie, zero fabrication."""
        adapter = GenieRuntimeAdapter()
        # On this development machine without genie-t2t-run.exe:
        self.assertIsNone(adapter.executable_path)
        self.assertFalse(adapter.is_runtime_present)

        # Calling execute_dialog must cleanly return None without raising or fabricating output
        reply, tokens, latency, meta = adapter.execute_dialog("dummy_config.json", "dummy prompt")
        self.assertIsNone(reply)
        self.assertEqual(tokens, 0)
        self.assertFalse(meta.get("hardware_valid", True))
        self.assertFalse(meta.get("simulated", True))
        self.assertIn("not installed", meta.get("error", ""))


if __name__ == "__main__":
    unittest.main()
