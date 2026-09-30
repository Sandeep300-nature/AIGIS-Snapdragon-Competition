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
from ai_engine.engine.prompts import AIGIS_COMPETITION_SYSTEM_PROMPT, get_competition_system_prompt
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

    def test_21_geniex_cli_discovery_and_version(self):
        """21. Verifies GenieRuntimeAdapter discovers geniex.exe and extracts version."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_geniex = os.path.join(tmp_dir, "geniex.exe")
            with open(fake_geniex, "w") as f:
                f.write("echo off\n")

            with patch.dict(os.environ, {"PATH": tmp_dir}):
                adapter = GenieRuntimeAdapter()
                self.assertTrue(adapter.is_runtime_present)
                self.assertEqual(adapter.executable_path, fake_geniex)

                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="geniex 0.7.0\n", stderr="")
                    version = adapter.get_version()
                    self.assertIn("0.7.0", version)

    def test_22_geniex_non_interactive_execution_and_telemetry(self):
        """22. Verifies GenieRuntimeAdapter non-interactive --input execution and telemetry extraction."""
        adapter = GenieRuntimeAdapter()
        adapter._is_present = True
        adapter._executable_path = r"C:\fake\geniex.exe"

        sample_stdout = (
            "⏳ Loading model...\n"
            "🤖 Model ready\n"
            "encoding...I am AIGIS, an autonomous on-device personal AI assistant running on Snapdragon Hexagon NPU.\n\n"
            "— 21.7 tok/s • 44 tok • 0.1 s first token —\n"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=sample_stdout,
                stderr=""
            )

            reply, tokens, latency, meta = adapter.execute_dialog(
                config_path="dummy_config.json",
                formatted_prompt="<|im_start|>user\nHello<|im_end|>",
                max_tokens=128
            )

            # Check that subprocess.run was called with non-interactive --input flag
            self.assertTrue(mock_run.called)
            call_args = mock_run.call_args[0][0]
            self.assertEqual(call_args[0], r"C:\fake\geniex.exe")
            self.assertEqual(call_args[1], "infer")
            self.assertEqual(call_args[2], "ai-hub-models/Qwen3-4B-Instruct-2507")
            self.assertEqual(call_args[3], "--compute")
            self.assertEqual(call_args[4], "npu")
            self.assertEqual(call_args[5], "--input")
            temp_file_arg = call_args[6]
            self.assertTrue(temp_file_arg.endswith(".txt"))
            # Temporary file should have been cleaned up
            self.assertFalse(os.path.exists(temp_file_arg))
            self.assertEqual(call_args[7], "--max-tokens")
            self.assertEqual(call_args[8], "128")

            # Check response text and parsed telemetry
            self.assertEqual(reply, "I am AIGIS, an autonomous on-device personal AI assistant running on Snapdragon Hexagon NPU.")
            self.assertEqual(tokens, 44)
            self.assertEqual(meta.get("decode_tok_per_sec"), 21.7)
            self.assertEqual(meta.get("ttft_sec"), 0.1)
            self.assertEqual(meta.get("backend"), "QnnHtp")
            self.assertEqual(meta.get("target"), "Qualcomm Hexagon NPU")
            self.assertTrue(meta.get("hardware_valid"))
            self.assertFalse(meta.get("simulated"))

    def test_23_geniex_error_handling(self):
        """23. Verifies GenieRuntimeAdapter handles non-zero exit code truthfully."""
        adapter = GenieRuntimeAdapter()
        adapter._is_present = True
        adapter._executable_path = r"C:\fake\geniex.exe"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error: Model bundle corrupted."
            )

            reply, tokens, latency, meta = adapter.execute_dialog(
                config_path="dummy_config.json",
                formatted_prompt="<|im_start|>user\nHello<|im_end|>",
                max_tokens=64
            )

            self.assertIsNone(reply)
            self.assertEqual(tokens, 0)
            self.assertIn("Error: Model bundle corrupted.", meta.get("error", ""))

    def test_24_competition_system_prompt_construction(self):
        """24. Verifies AIGIS competition system prompt construction, isolation, and ChatML injection."""
        self.assertIn("powered by Qualcomm Snapdragon", AIGIS_COMPETITION_SYSTEM_PROMPT)
        self.assertIn("friendly and autonomous on-device personal AI assistant", AIGIS_COMPETITION_SYSTEM_PROMPT)
        self.assertIn("Prioritize concise, clear answers", AIGIS_COMPETITION_SYSTEM_PROMPT)
        self.assertIn("Your name is AIGIS.", AIGIS_COMPETITION_SYSTEM_PROMPT)

        # Default getter returns competition prompt
        prompt = get_competition_system_prompt()
        self.assertEqual(prompt, AIGIS_COMPETITION_SYSTEM_PROMPT)

        # Environment variable override
        with patch.dict(os.environ, {"AIGIS_SYSTEM_PROMPT": "Custom Competition Prompt"}):
            self.assertEqual(get_competition_system_prompt(), "Custom Competition Prompt")

        # Provider default injection
        provider = GenieQwenProvider()
        formatted = provider.format_chatml_prompt("Hello AIGIS")
        self.assertIn(f"<|im_start|>system\n{AIGIS_COMPETITION_SYSTEM_PROMPT}<|im_end|>", formatted)

    def test_25_snapdragon_engine_telemetry_propagation_and_fallback(self):
        """25. Verifies telemetry metadata bubbles up to EngineResponse on hardware, and falls back to CPU on Intel."""
        # A. On current Intel host: verify truthful fallback to SmolLM2
        engine_with_fallback = SnapdragonNPUEngine(
            hardware_detector=HardwareDetector,
            fallback_engine=self.router.local_engine,
            auto_fallback=True
        )
        resp = engine_with_fallback.generate_response("What time is it?", fallback=True)
        self.assertTrue(resp.metadata.get("fallback_triggered"))
        self.assertFalse(resp.metadata.get("hardware_valid"))
        self.assertFalse(resp.metadata.get("simulated"))
        self.assertIn("Local", resp.metadata.get("fallback_engine", ""))

        # B. On simulated physical hardware: verify telemetry metadata merging
        mock_runner = MagicMock()
        mock_runner.inspect_capabilities.return_value = SnapdragonCapabilityReport(
            state=SnapdragonRuntimeState.FULLY_CONFIGURED,
            state_description="Snapdragon Hexagon NPU verified",
            is_available=True,
            architecture="arm64",
            is_arm64=True,
            is_snapdragon_cpu=True,
            qnn_provider_available=True,
            qairt_runtime_available=True,
            genie_runtime_available=True,
            model_artifact_found=True,
            model_dir=r"C:\fake\model"
        )
        mock_runner.run_inference.return_value = (
            "Response from Snapdragon NPU",
            44,
            120,
            {
                "decode_tok_per_sec": 21.7,
                "ttft_sec": 0.1,
                "backend": "QnnHtp",
                "target": "Qualcomm Hexagon NPU"
            }
        )
        engine_hw = SnapdragonNPUEngine(
            hardware_detector=MagicMock(),
            runner=mock_runner
        )
        resp_hw = engine_hw.generate_response("Test prompt")
        self.assertEqual(resp_hw.reply, "Response from Snapdragon NPU")
        self.assertEqual(resp_hw.metadata.get("decode_tok_per_sec"), 21.7)
        self.assertEqual(resp_hw.metadata.get("ttft_sec"), 0.1)
        self.assertEqual(resp_hw.metadata.get("backend"), "QnnHtp")
        self.assertTrue(resp_hw.metadata.get("hardware_valid"))
        self.assertFalse(resp_hw.metadata.get("simulated"))

    def test_26_geniex_localappdata_discovery(self):
        """26. Verifies discovery of geniex.exe in %LOCALAPPDATA%\\GenieX CLI."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cli_dir = os.path.join(tmp_dir, "GenieX CLI")
            os.makedirs(cli_dir, exist_ok=True)
            fake_exe = os.path.join(cli_dir, "geniex.exe")
            with open(fake_exe, "w") as f:
                f.write("echo off\n")

            with patch.dict(os.environ, {"LOCALAPPDATA": tmp_dir}):
                adapter = GenieRuntimeAdapter()
                self.assertTrue(adapter.is_runtime_present)
                self.assertEqual(adapter.executable_path, fake_exe)

    def test_27_model_cache_discovery(self):
        """27. Verifies ~/.cache/geniex/models/qualcomm/Qwen3-4B-Instruct-2507 discovery."""
        with tempfile.TemporaryDirectory() as tmp_home:
            cache_model_dir = os.path.join(
                tmp_home, ".cache", "geniex", "models", "qualcomm", "Qwen3-4B-Instruct-2507"
            )
            os.makedirs(cache_model_dir, exist_ok=True)

            with patch("os.path.expanduser", side_effect=lambda p: os.path.normpath(p.replace("~", tmp_home))):
                provider = GenieQwenProvider()
                self.assertEqual(os.path.normpath(provider.model_dir), os.path.normpath(cache_model_dir))

                runner = QualcommModelRunner()
                self.assertEqual(os.path.normpath(runner.model_dir), os.path.normpath(cache_model_dir))

    def test_28_deterministic_clock_queries_bypass_llm(self):
        """28. Verifies all natural time query variations resolve via local OS clock without invoking LLM."""
        from datetime import datetime
        now = datetime.now()
        expected_hour_min = now.strftime("%I:%M")

        time_variations = [
            "What time is it?",
            "What is the current time?",
            "Tell me the current time",
            "what's the time?",
            "What is the time?",
            "what is the time right now",
            "tell me the time",
            "the time",
            "current time",
            "time please",
            "what time is it now",
            "AIGIS, what time is it?",
            "What time is it, AIGIS?",
            "Hey AIGIS, what is the current time?"
        ]

        for query in time_variations:
            with self.subTest(query=query):
                resp = self.router.route_and_generate(query)
                self.assertEqual(resp.engine, "local")
                self.assertFalse(resp.metadata.get("networkUsed", True))
                self.assertEqual(resp.metadata.get("intent"), "time")
                self.assertIn("current time is", resp.reply.lower())
                # Verify actual local OS clock hour and minute is in the response
                self.assertIn(expected_hour_min, resp.reply)

    def test_29_deterministic_date_and_combined_queries(self):
        """29. Verifies date and combined time+date queries resolve deterministically from OS clock."""
        from datetime import datetime
        now = datetime.now()
        expected_day = now.strftime("%A")
        expected_month = now.strftime("%B")

        date_variations = [
            "What's today's date?",
            "What is the date today?",
            "Tell me the date",
            "What day is today?",
            "What day is it?"
        ]

        for query in date_variations:
            with self.subTest(query=query):
                resp = self.router.route_and_generate(query)
                self.assertEqual(resp.engine, "local")
                self.assertFalse(resp.metadata.get("networkUsed", True))
                self.assertEqual(resp.metadata.get("intent"), "date")
                self.assertIn(expected_day, resp.reply)
                self.assertIn(expected_month, resp.reply)

        # Combined time and date query
        combo_resp = self.router.route_and_generate("What time and date is it?")
        self.assertEqual(combo_resp.engine, "local")
        self.assertEqual(combo_resp.metadata.get("intent"), "time_date")
        self.assertIn(expected_day, combo_resp.reply)
        self.assertIn(now.strftime("%I:%M"), combo_resp.reply)

    def test_30_snapdragon_npu_runner_never_invoked_for_clock_queries(self):
        """30. Verifies Snapdragon NPU LLM runner is NEVER invoked for live clock queries, but IS for general AI."""
        mock_runner = MagicMock()
        mock_snapdragon = SnapdragonNPUEngine(
            hardware_detector=HardwareDetector,
            runner=mock_runner
        )
        # Mock fully configured hardware state where runner is normally used
        mock_snapdragon.get_capability_report = MagicMock(return_value=SnapdragonCapabilityReport(
            state=SnapdragonRuntimeState.FULLY_CONFIGURED,
            state_description="Qualcomm Hexagon NPU verified",
            is_available=True,
            architecture="arm64",
            is_arm64=True,
            is_snapdragon_cpu=True,
            qnn_provider_available=True,
            qairt_runtime_available=True,
            genie_runtime_available=True,
            model_artifact_found=True,
            model_dir=r"C:\fake\model"
        ))

        router = IntentTaskRouter(
            hardware_detector=HardwareDetector,
            snapdragon_engine=mock_snapdragon,
            competition_mode=True
        )

        # 1. Clock queries MUST NOT invoke LLM runner
        resp_time = router.route_and_generate("What time is it?")
        self.assertEqual(resp_time.engine, "local")
        self.assertIn("current time is", resp_time.reply.lower())
        self.assertEqual(mock_runner.run_inference.call_count, 0, "LLM runner must NOT be invoked for clock queries!")

        resp_curr = router.route_and_generate("What is the current time?")
        self.assertEqual(resp_curr.engine, "local")
        self.assertEqual(mock_runner.run_inference.call_count, 0, "LLM runner must NOT be invoked for current time!")

        # 2. General AI queries MUST route to LLM runner
        mock_runner.run_inference.return_value = ("Quantum computing uses qubits, sir.", 15, 45, {})
        resp_gen = router.route_and_generate("Explain quantum computing in one sentence")
        self.assertGreater(mock_runner.run_inference.call_count, 0, "LLM runner MUST be invoked for general AI prompts!")
        self.assertIn("qubits", resp_gen.reply)

    def test_31_conversational_and_conceptual_queries_route_to_llm(self):
        """31. Verifies conversational greetings and time-concept queries (e.g. time dilation) route to LLM, not clock."""
        # A. Greeting prompt (e.g., 'HLO AIGIS') classifies as GENERAL_AI, not SYSTEM_INFO
        cls_greeting = self.router.classify_intent("HLO AIGIS")
        self.assertEqual(cls_greeting["intent"], "GENERAL_AI")

        # B. Conceptual time query (e.g., 'Explain time dilation') classifies as GENERAL_AI
        cls_dilation = self.router.classify_intent("Explain time dilation")
        self.assertEqual(cls_dilation["intent"], "GENERAL_AI")

        # C. Story about time travel
        cls_story = self.router.classify_intent("Tell me a story about time travel")
        self.assertEqual(cls_story["intent"], "GENERAL_AI")

    def test_32_remote_location_queries_in_competition_mode(self):
        """32. Verifies queries for remote timezones (e.g., 'What time is it in Tokyo?') do not use local clock or cloud."""
        from datetime import datetime
        now = datetime.now()
        local_hour_min = now.strftime("%I:%M %p")

        remote_queries = [
            "What time is it in Tokyo?",
            "What time is it in New York?",
            "What is the current time in London?"
        ]

        for q in remote_queries:
            with self.subTest(query=q):
                resp = self.router.route_and_generate(q)
                self.assertEqual(resp.engine, "local")
                self.assertFalse(resp.metadata.get("networkUsed", True))
                # Must NOT output local OS clock time as the answer for a remote city
                self.assertNotIn(local_hour_min, resp.reply)
                # Truthful local-only limitation in Competition Mode
                self.assertIn("cannot be verified in competition local-only mode", resp.reply.lower())


if __name__ == "__main__":
    unittest.main()


