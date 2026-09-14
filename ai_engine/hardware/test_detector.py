import unittest
import json
from ai_engine.hardware.detector import HardwareDetector


class TestHardwareDetector(unittest.TestCase):

    def test_detector_returns_capabilities(self):
        caps = HardwareDetector.get_capabilities()
        print("\n--- DETECTED HARDWARE CAPABILITIES ---")
        print(json.dumps(caps, indent=2))
        print("--------------------------------------\n")

        self.assertIn("deviceType", caps)
        self.assertIn("architecture", caps)
        self.assertIn("os", caps)
        self.assertIn("cpu", caps)
        self.assertIn("gpu", caps)
        self.assertIn("onnxruntime", caps)
        self.assertIn("accelerators", caps)

    def test_architecture_truthfulness(self):
        arch = HardwareDetector.get_architecture()
        self.assertTrue(arch["isX64"] or arch["isArm64"])
        # On this physical x64 machine, verify isX64 is True
        self.assertTrue(arch["isX64"])
        self.assertFalse(arch["isArm64"])

    def test_no_false_snapdragon_claim_on_x64(self):
        caps = HardwareDetector.get_capabilities()
        snapdragon = caps["accelerators"]["snapdragonNpu"]
        # Must NOT claim Snapdragon on an x64 Intel machine
        self.assertFalse(snapdragon["detected"])
        self.assertFalse(snapdragon["npuAccelerated"])
        self.assertEqual(caps["deviceType"], "Development Environment — x64")

    def test_gpu_and_cuda_independence(self):
        caps = HardwareDetector.get_capabilities()
        gpu = caps["gpu"]
        cuda = caps["accelerators"]["cuda"]

        # If NVIDIA GPU detected physically, CUDA status must be reported independently
        if gpu["detected"] and gpu["vendor"] == "NVIDIA":
            self.assertTrue(cuda["hardwareDetected"])
            # On this host, torch cuda is False and onnxruntime cuda is False
            self.assertFalse(cuda["torchCudaAvailable"])
            self.assertFalse(cuda["onnxruntimeCudaAvailable"])

    def test_qnn_independence(self):
        caps = HardwareDetector.get_capabilities()
        qnn = caps["accelerators"]["qnn"]
        # Must report QNN provider status truthfully
        self.assertFalse(qnn["providerAvailable"])


if __name__ == "__main__":
    unittest.main()
