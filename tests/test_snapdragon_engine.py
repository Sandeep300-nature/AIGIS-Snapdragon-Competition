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
from ai_engine.engine.base_engine import BaseAIEngine, EngineResponse
from ai_engine.engine.local_engine import LocalEngine
from ai_engine.engine.cloud_engine import CloudEngine
from ai_engine.engine.router import IntentTaskRouter, SmolLM2Engine, GroqEngine
from ai_engine.hardware.detector import HardwareDetector


class TestSnapdragonEngineSuite(unittest.TestCase):
    """
    Comprehensive test suite for M6 Step 3:
    - Verifies SnapdragonNPUEngine abstraction and QualcommModelRunner adapter.
    - Validates strict 6-state runtime capability detection without collapsing to a boolean.
    - Validates artifact discovery mechanism.
    - Verifies polymorphic router hierarchy (Tier 1 Snapdragon NPU, Tier 2 SmolLM2 CPU fallback, Tier 3 Groq Cloud).
    - Verifies isolation of explicit local and explicit cloud modes.
    - Verifies non-regression of desktop actions, live web anti-hallucination, and deterministic clock.
    """

    def setUp(self):
        self.engine = SnapdragonNPUEngine(hardware_detector=HardwareDetector)
        self.router = IntentTaskRouter(hardware_detector=HardwareDetector)

    def test_1_engine_contract_inheritance(self):
        """1. Validates that SnapdragonNPUEngine strictly conforms to BaseAIEngine and BaseEngine."""
        self.assertIsInstance(self.engine, BaseAIEngine)
        self.assertTrue(issubclass(SnapdragonNPUEngine, BaseEngine))
        self.assertTrue(issubclass(SnapdragonNPUEngine, BaseAIEngine))

    def test_2_default_configuration_schema(self):
        """2. Verifies candidate model config strictly targets Llama-3.2-1B-Instruct DEFAULT_W4A16."""
        config = self.engine.config
        self.assertEqual(config.model_id, "Llama-3.2-1B-Instruct")
        self.assertEqual(config.checkpoint, "DEFAULT_W4A16")
        self.assertEqual(config.quantization, "w4a16")
        self.assertEqual(config.runtime, "QNNExecutionProvider")
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
        self.assertIn("qnn execution provider", report.state_description.lower())

    def test_5_simulated_arm64_missing_runtime_dlls_state(self):
        """5. Simulated ARM64 with QNN EP registered but missing QAIRT DLLs must yield RUNTIME_INCOMPLETE."""
        mock_detector = MagicMock()
        mock_detector.get_capabilities.return_value = {
            "architecture": "arm64",
            "cpu": {"brand": "Snapdragon X Elite", "isSnapdragon": True},
            "accelerators": {
                "qnn": {"providerAvailable": True, "dllsFound": [], "hasDllsInPath": False},
                "snapdragonNpu": {"detected": True, "npuAccelerated": True}
            },
            "onnxruntime": {"availableProviders": ["QNNExecutionProvider", "CPUExecutionProvider"]}
        }

        with patch("shutil.which", return_value=None):
            runner = QualcommModelRunner(hardware_detector=mock_detector)
            report = runner.inspect_capabilities()
            self.assertEqual(report.state, SnapdragonRuntimeState.RUNTIME_INCOMPLETE)
            self.assertFalse(report.is_available)
            self.assertIn("missing", report.state_description.lower())

    def test_6_simulated_arm64_missing_model_artifact_state(self):
        """6. Simulated hardware + runtime present, but missing model artifact must yield MODEL_ARTIFACT_UNAVAILABLE."""
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

        with patch("shutil.which", side_effect=lambda x: f"C:\\Windows\\System32\\{x}"):
            non_existent_model_dir = os.path.join(tempfile.gettempdir(), "non_existent_llama_model_dir_xyz")
            runner = QualcommModelRunner(
                model_dir=non_existent_model_dir,
                hardware_detector=mock_detector
            )
            report = runner.inspect_capabilities()
            self.assertEqual(report.state, SnapdragonRuntimeState.MODEL_ARTIFACT_UNAVAILABLE)
            self.assertFalse(report.is_available)
            self.assertIn("model artifact not found", report.state_description.lower())

    def test_7_simulated_fully_configured_state(self):
        """7. Simulated ARM64 + QNN + DLLs + Model Artifact must yield FULLY_CONFIGURED."""
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

        # Create temporary mock model artifact directory
        with tempfile.TemporaryDirectory() as temp_model_dir:
            with open(os.path.join(temp_model_dir, "genai_config.json"), "w") as f:
                f.write('{"model": {"type": "llama"}}')
            with open(os.path.join(temp_model_dir, "model.onnx"), "wb") as f:
                f.write(b"mock onnx binary content")

            with patch("shutil.which", side_effect=lambda x: f"C:\\Windows\\System32\\{x}"):
                runner = QualcommModelRunner(
                    model_dir=temp_model_dir,
                    hardware_detector=mock_detector
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
        self.assertEqual(resp.metadata.get("model"), "Llama-3.2-1B-Instruct-w4a16")
        self.assertEqual(resp.metadata.get("checkpoint"), "DEFAULT_W4A16")
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
            snapdragon_engine=mock_snapdragon
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
        self.assertEqual(resp.metadata.get("routingMode"), "enforced_local")

    def test_13_explicit_cloud_mode_is_cloud_only(self):
        """13. Explicit CLOUD mode must route only to cloud and never silently fall back to local."""
        resp = self.router.route_and_generate("Explain quantum computing in one sentence", mode="cloud")
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
        self.assertEqual(resp.engine, "local")
        self.assertIn("cannot be verified in local-only mode", resp.reply.lower())
        self.assertFalse(resp.metadata.get("verified", False))

    def test_16_existing_deterministic_system_queries(self):
        """16. Deterministic system queries must resolve immediately on-device."""
        resp = self.router.route_and_generate("What time is it?")
        self.assertEqual(resp.engine, "local")
        self.assertIn("current time is", resp.reply.lower())
        self.assertEqual(resp.metadata.get("intent"), "time")
        self.assertLessEqual(resp.latencyMs, 500)


if __name__ == "__main__":
    unittest.main()
