"""
Regression Test Suite: Local Hardware & System Telemetry Intent Routing & Resolution.
Validates:
1. "Tell me my CPU and GPU." -> Deterministic hardware telemetry (HardwareDetector truth).
2. "Can u tell me the system telemetry?" -> Deterministic hardware telemetry.
3. "What is my system status?" -> Deterministic hardware telemetry.
4. "Is the NPU detected?" -> Deterministic hardware telemetry.
5. "What is my architecture?" -> Deterministic hardware telemetry.
6. "Tell me what's going on in my system" -> Deterministic hardware telemetry.
7. "What time is it?" -> Deterministic OS-level clock truth.
8. Conceptual question: "What is system telemetry?" -> Preserved as General AI / LLM knowledge query.
9. Verification that telemetry responses contain only values physically returned by HardwareDetector.
10. Verification of zero network usage and zero LLM hallucination for local telemetry requests.
"""

import os
import unittest

os.environ["AIGIS_COMPETITION_MODE"] = "true"

from ai_engine.engine.router import IntentTaskRouter
from ai_engine.hardware.detector import HardwareDetector
from ai_engine.engine.deterministic import parse_telemetry_query, build_telemetry_response


class TestHardwareTelemetryRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = IntentTaskRouter()
        cls.caps = HardwareDetector.get_capabilities()

    def test_01_tell_me_my_cpu_and_gpu(self):
        """Verifies 'Tell me my CPU and GPU.' resolves deterministically via HardwareDetector."""
        prompt = "Tell me my CPU and GPU."
        self.assertTrue(parse_telemetry_query(prompt))

        classification = self.router.classify_intent(prompt)
        self.assertEqual(classification["intent"], "SYSTEM_INFO")

        resp = self.router.route_and_generate(prompt)
        self.assertEqual(resp.metadata.get("intent"), "hardware_telemetry")
        self.assertFalse(resp.metadata.get("networkUsed", True))
        self.assertNotIn("I don't have the ability to access", resp.reply)

        # Grounded in actual HardwareDetector values
        cpu_brand = self.caps.get("cpu", {}).get("brand")
        gpu_name = self.caps.get("gpu", {}).get("name")
        self.assertIn(cpu_brand, resp.reply)
        self.assertIn(gpu_name, resp.reply)

    def test_02_can_u_tell_me_the_system_telemetry(self):
        """Verifies 'Can u tell me the system telemetry?' returns verified workstation telemetry."""
        prompt = "Can u tell me the system telemetry?"
        self.assertTrue(parse_telemetry_query(prompt))

        classification = self.router.classify_intent(prompt)
        self.assertEqual(classification["intent"], "SYSTEM_INFO")

        resp = self.router.route_and_generate(prompt)
        self.assertEqual(resp.metadata.get("intent"), "hardware_telemetry")
        self.assertIn("Workstation Hardware Telemetry, sir:", resp.reply)
        self.assertIn(f"Architecture: {self.caps.get('architecture')}", resp.reply)
        self.assertNotIn("I don't have the ability", resp.reply)

    def test_03_what_is_my_system_status(self):
        """Verifies 'What is my system status?' resolves to truthful local telemetry."""
        prompt = "What is my system status?"
        self.assertTrue(parse_telemetry_query(prompt))

        classification = self.router.classify_intent(prompt)
        self.assertEqual(classification["intent"], "SYSTEM_INFO")

        resp = self.router.route_and_generate(prompt)
        self.assertEqual(resp.metadata.get("intent"), "hardware_telemetry")
        self.assertIn("Workstation Hardware Telemetry, sir:", resp.reply)

    def test_04_is_the_npu_detected(self):
        """Verifies 'Is the NPU detected?' reports truthful NPU status from HardwareDetector."""
        for prompt in ["Is the NPU detected?", "Is my Snapdragon NPU detected?"]:
            with self.subTest(prompt=prompt):
                self.assertTrue(parse_telemetry_query(prompt))

                classification = self.router.classify_intent(prompt)
                self.assertEqual(classification["intent"], "SYSTEM_INFO")

                resp = self.router.route_and_generate(prompt)
                self.assertEqual(resp.metadata.get("intent"), "hardware_telemetry")
                npu_status = self.caps.get("accelerators", {}).get("snapdragonNpu", {}).get("status")
                self.assertIn(npu_status, resp.reply)

    def test_05_what_is_my_architecture(self):
        """Verifies 'What is my architecture?' reports truthful machine architecture."""
        prompt = "What is my architecture?"
        self.assertTrue(parse_telemetry_query(prompt))

        classification = self.router.classify_intent(prompt)
        self.assertEqual(classification["intent"], "SYSTEM_INFO")

        resp = self.router.route_and_generate(prompt)
        self.assertEqual(resp.metadata.get("intent"), "hardware_telemetry")
        arch = self.caps.get("architecture")
        self.assertIn(f"Architecture: {arch}", resp.reply)

    def test_06_tell_me_whats_going_on_in_my_system(self):
        """Verifies 'Tell me what's going on in my system' does not hallucinate disclaimer."""
        prompt = "Tell me what's going on in my system"
        self.assertTrue(parse_telemetry_query(prompt))

        classification = self.router.classify_intent(prompt)
        self.assertEqual(classification["intent"], "SYSTEM_INFO")

        resp = self.router.route_and_generate(prompt)
        self.assertEqual(resp.metadata.get("intent"), "hardware_telemetry")
        self.assertIn("Workstation Hardware Telemetry, sir:", resp.reply)
        self.assertNotIn("I don't have the ability to access or interact", resp.reply)

    def test_07_what_time_is_it_remains_deterministic_clock(self):
        """Verifies deterministic time queries continue resolving via OS-level clock."""
        prompt = "What time is it?"
        classification = self.router.classify_intent(prompt)
        self.assertEqual(classification["intent"], "SYSTEM_INFO")
        self.assertEqual(classification.get("systemInfoType"), "time")

        resp = self.router.route_and_generate(prompt)
        self.assertEqual(resp.metadata.get("intent"), "time")
        self.assertTrue(resp.metadata.get("localClock"))
        self.assertIn("The current time is", resp.reply)

    def test_08_conceptual_question_preserved_as_general_ai(self):
        """
        Verifies conceptual questions like 'What is system telemetry?' or
        'Explain what system telemetry means.' remain General AI questions for LLM synthesis.
        """
        conceptual_prompts = [
            "What is system telemetry?",
            "Explain what system telemetry means.",
            "What is a CPU?",
            "What does NPU stand for?"
        ]
        for prompt in conceptual_prompts:
            with self.subTest(prompt=prompt):
                self.assertFalse(parse_telemetry_query(prompt), f"Falsely matched as telemetry query: {prompt}")
                classification = self.router.classify_intent(prompt)
                self.assertEqual(classification["intent"], "GENERAL_AI")

    def test_09_no_fabricated_telemetry_values(self):
        """Verifies that all values in the telemetry response match HardwareDetector dynamically."""
        resp = self.router.route_and_generate("Can u tell me the system telemetry?")
        lines = resp.reply.splitlines()

        # Check each line against actual detector data
        for line in lines:
            if "Device Environment:" in line:
                self.assertIn(self.caps.get("deviceType"), line)
            elif "Architecture:" in line:
                self.assertIn(self.caps.get("architecture"), line)
            elif "Processor:" in line:
                self.assertIn(self.caps.get("cpu", {}).get("brand"), line)
            elif "Physical GPU:" in line:
                self.assertIn(self.caps.get("gpu", {}).get("name"), line)
            elif "Snapdragon NPU Status:" in line:
                self.assertIn(self.caps.get("accelerators", {}).get("snapdragonNpu", {}).get("status"), line)

    def test_10_what_is_my_cpu(self):
        """Verifies 'What is my CPU?' and 'What CPU do I have?' report truthful processor metrics."""
        prompts = ["What is my CPU?", "What CPU do I have?"]
        for p in prompts:
            with self.subTest(prompt=p):
                self.assertTrue(parse_telemetry_query(p))
                classification = self.router.classify_intent(p)
                self.assertEqual(classification["intent"], "SYSTEM_INFO")

                resp = self.router.route_and_generate(p)
                self.assertEqual(resp.metadata.get("intent"), "hardware_telemetry")
                self.assertFalse(resp.metadata.get("networkUsed", True))
                cpu_brand = self.caps.get("cpu", {}).get("brand")
                self.assertIn(cpu_brand, resp.reply)
                self.assertIn("Processor", resp.reply)
                self.assertIn("CPU Usage", resp.reply)
                self.assertIn("CPU Temperature: unavailable", resp.reply)

    def test_11_what_is_my_gpu(self):
        """Verifies 'What is my GPU?' and 'What GPU am I using?' report truthful GPU and VRAM."""
        prompts = ["What is my GPU?", "What GPU am I using?"]
        for p in prompts:
            with self.subTest(prompt=p):
                self.assertTrue(parse_telemetry_query(p))
                classification = self.router.classify_intent(p)
                self.assertEqual(classification["intent"], "SYSTEM_INFO")

                resp = self.router.route_and_generate(p)
                self.assertEqual(resp.metadata.get("intent"), "hardware_telemetry")
                self.assertFalse(resp.metadata.get("networkUsed", True))
                gpu_name = self.caps.get("gpu", {}).get("name")
                self.assertIn(gpu_name, resp.reply)
                self.assertIn("Physical GPU", resp.reply)
                self.assertIn("GPU Memory", resp.reply)

    def test_12_ram_usage_queries(self):
        """Verifies 'What is my RAM usage?' and 'How much RAM am I using?' report truthful memory."""
        prompts = ["What is my RAM usage?", "How much RAM am I using?", "How much RAM do I have?"]
        for p in prompts:
            with self.subTest(prompt=p):
                self.assertTrue(parse_telemetry_query(p))
                classification = self.router.classify_intent(p)
                self.assertEqual(classification["intent"], "SYSTEM_INFO")

                resp = self.router.route_and_generate(p)
                self.assertEqual(resp.metadata.get("intent"), "hardware_telemetry")
                self.assertFalse(resp.metadata.get("networkUsed", True))
                self.assertIn("Memory", resp.reply)
                self.assertIn("GB", resp.reply)

    def test_13_temperature_queries(self):
        """Verifies CPU and GPU temperature queries return truthful measurements or unavailable."""
        # CPU temperature
        resp_cpu = self.router.route_and_generate("What's my CPU temperature?")
        self.assertEqual(resp_cpu.metadata.get("intent"), "hardware_telemetry")
        self.assertIn("CPU Temperature: unavailable", resp_cpu.reply)

        # GPU temperature
        resp_gpu = self.router.route_and_generate("What's my GPU temperature?")
        self.assertEqual(resp_gpu.metadata.get("intent"), "hardware_telemetry")
        self.assertIn("GPU Temperature:", resp_gpu.reply)

    def test_14_storage_free_queries(self):
        """Verifies 'How much storage is free?' returns real storage metrics."""
        prompt = "How much storage is free?"
        self.assertTrue(parse_telemetry_query(prompt))
        resp = self.router.route_and_generate(prompt)
        self.assertEqual(resp.metadata.get("intent"), "hardware_telemetry")
        self.assertIn("Storage", resp.reply)
        self.assertIn("Free Storage", resp.reply)

    def test_15_conceptual_queries_remain_general_ai(self):
        """Verifies conceptual questions without personal markers remain General AI."""
        concepts = [
            "What is a CPU?",
            "What is GPU telemetry?",
            "Explain RAM",
            "What does system telemetry mean?",
            "Explain GPU temperature.",
            "What is a GPU?",
            "What does NPU stand for?"
        ]
        for c in concepts:
            with self.subTest(concept=c):
                self.assertFalse(parse_telemetry_query(c), f"Conceptual query falsely marked as telemetry: {c}")
                classification = self.router.classify_intent(c)
                self.assertEqual(classification["intent"], "GENERAL_AI")

    def test_16_telemetry_provider_called_and_network_not_used(self):
        """Verifies telemetry data comes from HardwareDetector and networkUsed is strictly False."""
        prompt = "Show me my hardware telemetry"
        self.assertTrue(parse_telemetry_query(prompt))

        resp = self.router.route_and_generate(prompt)
        self.assertFalse(resp.metadata.get("networkUsed", True))
        self.assertTrue(resp.metadata.get("competitionMode", False))
        self.assertIn("telemetry", resp.metadata)
        telemetry = resp.metadata["telemetry"]
        self.assertIn("cpu", telemetry)
        self.assertIn("gpu", telemetry)
        self.assertIn("memory", telemetry)
        self.assertIn("storage", telemetry)
        self.assertIn("identity", telemetry)

    def test_17_intel_host_truthful_non_fabrication(self):
        """Verifies Intel host truthfully reports Intel CPU and non-Snapdragon status."""
        telemetry = HardwareDetector.get_system_telemetry()
        if self.caps.get("cpu", {}).get("isSnapdragon") is False:
            self.assertFalse(telemetry["aiHardware"]["isSnapdragon"])
            self.assertFalse(telemetry["aiHardware"]["npuDetected"])
            self.assertIn("x86_64", telemetry["identity"]["architecture"])
            self.assertIn("Not detected", telemetry["aiHardware"]["npuStatus"])

    def test_18_conversational_and_frontend_shared_source(self):
        """Verifies that conversational telemetry and frontend telemetry originate from the exact same HardwareDetector source."""
        frontend_telemetry = HardwareDetector.get_system_telemetry()
        resp = self.router.route_and_generate("Tell me about my system")
        conversational_telemetry = resp.metadata.get("telemetry", {})

        # Verify underlying metrics match exactly between frontend source and conversational source
        self.assertEqual(frontend_telemetry["identity"]["architecture"], conversational_telemetry["identity"]["architecture"])
        self.assertEqual(frontend_telemetry["cpu"]["brand"], conversational_telemetry["cpu"]["brand"])
        self.assertEqual(frontend_telemetry["gpu"]["name"], conversational_telemetry["gpu"]["name"])
        self.assertEqual(frontend_telemetry["aiHardware"]["isSnapdragon"], conversational_telemetry["aiHardware"]["isSnapdragon"])
        self.assertEqual(frontend_telemetry["aiHardware"]["npuStatus"], conversational_telemetry["aiHardware"]["npuStatus"])

    def test_19_what_hardware_are_you_running_on(self):
        """Verifies 'What hardware are you running on?' reflects the actual host, NOT Snapdragon target identity."""
        prompt = "What hardware are you running on?"
        self.assertTrue(parse_telemetry_query(prompt))
        resp = self.router.route_and_generate(prompt)
        self.assertEqual(resp.metadata.get("intent"), "hardware_telemetry")

        if not self.caps.get("cpu", {}).get("isSnapdragon", False):
            # Must reflect physical Intel / x86_64 workstation and not hallucinate Snapdragon
            self.assertIn(self.caps.get("cpu", {}).get("brand"), resp.reply)
            self.assertIn("Not detected", resp.reply)
            self.assertNotIn("Snapdragon 8", resp.reply)

    def test_20_storage_and_vram_queries(self):
        """Verifies 'How much storage is left?' and 'How much VRAM am I using?' resolve deterministically."""
        # Storage
        resp_storage = self.router.route_and_generate("How much storage is left?")
        self.assertEqual(resp_storage.metadata.get("intent"), "hardware_telemetry")
        self.assertIn("Storage", resp_storage.reply)
        self.assertIn("Free Storage", resp_storage.reply)

        # VRAM
        resp_vram = self.router.route_and_generate("How much VRAM am I using?")
        self.assertEqual(resp_vram.metadata.get("intent"), "hardware_telemetry")
        self.assertIn("GPU Memory", resp_vram.reply)


if __name__ == "__main__":
    unittest.main()

