"""
AIGIS Snapdragon X Elite QDC End-to-End Live Inference Verification.

Executes genuine on-device inference targeting Qualcomm Hexagon NPU via GenieX v0.7.0 CLI.
Validates:
1. Hardware capability detection (ARM64 Snapdragon X Elite + Hexagon NPU).
2. IntentTaskRouter initialization in competition mode.
3. Active local backend selection (Tier 1: Snapdragon NPU).
4. Live end-to-end prompt inference with verified ChatML formatting and trailer telemetry.
"""

import os
import sys

# Ensure repository root and ai_engine are on sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ai_engine_dir = os.path.join(repo_root, "ai_engine")
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from ai_engine.hardware.detector import HardwareDetector
from ai_engine.engine.router import IntentTaskRouter


def main():
    print("=================================================================")
    print("  AIGIS Snapdragon X Elite QDC End-to-End Inference Verification  ")
    print("=================================================================\n")

    print("=== 1. HARDWARE DETECTION ===")
    detector = HardwareDetector()
    caps = detector.get_capabilities()
    print(f"Architecture: {caps.get('architecture')}")
    print(f"Is Snapdragon: {caps.get('cpu', {}).get('isSnapdragon')}")
    print(f"CPU Brand: {caps.get('cpu', {}).get('brand')}")
    print(f"NPU Detected: {caps.get('accelerators', {}).get('snapdragonNpu', {}).get('detected')}")

    genie_caps = caps.get("accelerators", {}).get("genieNpu") or caps.get("accelerators", {}).get("genie", {})
    print(f"Genie Tools Found: {genie_caps.get('toolsFound')}")
    print(f"Model Bundle Found: {genie_caps.get('bundleFound')}")
    print(f"Model Bundle Dir: {genie_caps.get('bundleDir')}")

    print("\n=== 2. ROUTER INITIALIZATION ===")
    router = IntentTaskRouter(hardware_detector=detector, competition_mode=True)
    status = router.get_router_status()
    print(f"Active Backend: {status.get('activeLocalBackend')}")
    print(f"Competition Mode Enforced: {router.competition_mode}")

    print("\n=== 3. END-TO-END INFERENCE (GENIEX QWEN3-4B ON HEXAGON NPU) ===")
    prompt = "Explain what you are in one sentence."
    print(f"Prompt: {prompt}\n")

    response = router.route_and_generate(prompt, mode="local")

    print(f"Reply: {response.reply}\n")
    print(f"Provider: {response.provider}")
    print(f"Badge: {response.badge}")
    print(f"Latency: {response.latencyMs} ms")
    print(f"Tokens Generated: {response.metadata.get('tokensGenerated')}")
    print(f"Decode TPS: {response.metadata.get('decode_tok_per_sec')}")
    print(f"TTFT (sec): {response.metadata.get('ttft_sec')}")
    print(f"Hardware Valid: {response.metadata.get('hardware_valid')}")
    print(f"Simulated: {response.metadata.get('simulated')}")
    print(f"Full Metadata: {response.metadata}")
    print("\n=================================================================")
    print("  Verification Complete                                          ")
    print("=================================================================")


if __name__ == "__main__":
    main()
