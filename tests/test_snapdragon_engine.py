import os
import sys
import unittest
from unittest.mock import MagicMock

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
    BaseEngine
)
from ai_engine.engine.base_engine import BaseAIEngine, EngineResponse
from ai_engine.engine.local_engine import LocalEngine
from ai_engine.engine.cloud_engine import CloudEngine
from ai_engine.engine.router import IntentTaskRouter, SmolLM2Engine, GroqEngine
from ai_engine.hardware.detector import HardwareDetector


class TestSnapdragonNPUEngine(unittest.TestCase):
    """
    Unit test suite for Milestone 6 (M6) Step 1:
    Verifies SnapdragonNPUEngine abstraction contract, truthful hardware capability detection,
    defensive error handling, and polymorphic IntentTaskRouter integration.
    """

    def setUp(self):
        self.engine = SnapdragonNPUEngine(hardware_detector=HardwareDetector)

    def test_engine_contract_inheritance(self):
        """Validates that SnapdragonNPUEngine strictly conforms to BaseAIEngine and BaseEngine."""
        self.assertIsInstance(self.engine, BaseAIEngine)
        self.assertTrue(issubclass(SnapdragonNPUEngine, BaseEngine))
        self.assertTrue(issubclass(SnapdragonNPUEngine, BaseAIEngine))

    def test_default_configuration_schema(self):
        """Verifies candidate model config strictly targets Llama-3.2-1B-Instruct-w4a16."""
        config = self.engine.config
        self.assertEqual(config.model_id, "Llama-3.2-1B-Instruct")
        self.assertEqual(config.quantization, "w4a16")
        self.assertEqual(config.runtime, "QNNExecutionProvider")
        self.assertEqual(config.target_soc, "Snapdragon X Elite / X Plus")
        self.assertEqual(config.target_accelerator, "Qualcomm Hexagon NPU")
        self.assertEqual(config.context_length, 4096)

    def test_engine_info_structure(self):
        """Verifies structured telemetry dictionary returned by get_engine_info()."""
        info = self.engine.get_engine_info()
        self.assertEqual(info["engine"], "snapdragon_npu")
        self.assertEqual(info["model"], "Llama-3.2-1B-Instruct-w4a16")
        self.assertEqual(info["model_id"], "Llama-3.2-1B-Instruct")
        self.assertEqual(info["quantization"], "w4a16")
        self.assertEqual(info["runtime"], "QNNExecutionProvider")
        self.assertEqual(info["target_soc"], "Snapdragon X Elite / X Plus")
        self.assertEqual(info["target"], "Qualcomm Hexagon NPU")
        self.assertFalse(info["simulated"])
        self.assertIn("available", info)
        self.assertIn("reason", info)

    def test_truthful_unavailability_on_current_x86_machine(self):
        """Zero fabrication: verifies is_available() is False on this x86 Intel development machine."""
        available = self.engine.is_available()
        self.assertFalse(available)
        reason = self.engine.get_availability_reason()
        self.assertIn("Non-ARM64 architecture / Hexagon NPU absent", reason)

    def test_hardware_not_supported_error_without_fallback(self):
        """Verifies HardwareNotSupportedError is raised if inference is requested without NPU hardware."""
        with self.assertRaises(HardwareNotSupportedError) as ctx:
            self.engine.generate_response("Explain quantum computing.", fallback=False)
        self.assertIn("Snapdragon NPU inference requested, but host is not supported", str(ctx.exception))

        with self.assertRaises(HardwareNotSupportedError):
            list(self.engine.generate_stream("Stream test", fallback=False))

    def test_fallback_delegation_with_structured_provenance(self):
        """Verifies graceful fallback delegation to SmolLM2 with truthful provenance metadata."""
        mock_fallback = MagicMock(spec=BaseAIEngine)
        mock_fallback.generate_response.return_value = EngineResponse(
            reply="SmolLM2 fallback reply.",
            provider="AIGIS Local Engine -> SmolLM2-135M",
            engine="local",
            badge="⚡ AIGIS Local (SmolLM2 Fallback)",
            latencyMs=45,
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
        self.assertFalse(resp.metadata.get("simulated"))
        self.assertFalse(resp.metadata.get("hardware_valid"))
        self.assertTrue(resp.metadata.get("fallback_triggered"))
        self.assertIn("Non-ARM64 architecture", resp.metadata.get("fallback_reason", ""))

    def test_simulated_arm64_snapdragon_detection(self):
        """Verifies is_available() returns True when on physical ARM64 with active QNN."""
        mock_detector = MagicMock()
        mock_detector.get_capabilities.return_value = {
            "architecture": "arm64",
            "cpu": {"brand": "Snapdragon(R) X Elite - X1E80100", "isSnapdragon": True},
            "accelerators": {
                "qnn": {"providerAvailable": True, "status": "Available"},
                "snapdragonNpu": {"detected": True, "npuAccelerated": True}
            }
        }

        arm_engine = SnapdragonNPUEngine(hardware_detector=mock_detector)
        self.assertTrue(arm_engine.is_available())
        self.assertIn("Snapdragon ARM64 with active QNN Execution Provider detected", arm_engine.get_availability_reason())

        resp = arm_engine.generate_response("Hello Snapdragon")
        self.assertTrue(resp.metadata.get("hardware_valid"))
        self.assertFalse(resp.metadata.get("simulated"))
        self.assertEqual(resp.engine, "local")
        self.assertIn("Hexagon NPU", resp.reply)

    def test_intent_router_registration_and_aliases(self):
        """Verifies IntentTaskRouter registers SnapdragonNPUEngine, SmolLM2Engine, and GroqEngine."""
        router = IntentTaskRouter(hardware_detector=HardwareDetector)
        self.assertIsNotNone(router.snapdragon_engine)
        self.assertIsInstance(router.snapdragon_engine, SnapdragonNPUEngine)
        self.assertEqual(router.smollm2_engine, router.local_engine)
        self.assertEqual(router.groq_engine, router.cloud_engine)

    def test_router_hierarchy_x86_defaults_to_smollm2(self):
        """Verifies that on x86_64, the router cleanly defaults local execution to SmolLM2."""
        router = IntentTaskRouter(hardware_detector=HardwareDetector)
        # On x86, active local engine must be local_engine (SmolLM2 on CPU)
        active_local = router.get_active_local_engine()
        self.assertEqual(active_local, router.local_engine)

        status = router.get_router_status()
        self.assertEqual(status["activeLocalBackend"], "smollm2_cpu")
        self.assertIsNotNone(status["snapdragonEngine"])
        self.assertFalse(status["snapdragonEngine"]["available"])

    def test_router_hierarchy_arm64_routes_to_snapdragon(self):
        """Verifies that on ARM64 with QNN, the router automatically engages the Snapdragon NPU."""
        mock_detector = MagicMock()
        mock_detector.get_capabilities.return_value = {
            "architecture": "arm64",
            "cpu": {"isSnapdragon": True},
            "accelerators": {
                "qnn": {"providerAvailable": True},
                "snapdragonNpu": {"npuAccelerated": True}
            }
        }

        mock_snapdragon = SnapdragonNPUEngine(hardware_detector=mock_detector)
        router = IntentTaskRouter(
            hardware_detector=mock_detector,
            snapdragon_engine=mock_snapdragon
        )

        active_local = router.get_active_local_engine()
        self.assertEqual(active_local, mock_snapdragon)

        status = router.get_router_status()
        self.assertEqual(status["activeLocalBackend"], "snapdragon_npu")
        self.assertTrue(status["snapdragonEngine"]["available"])


if __name__ == "__main__":
    unittest.main()
