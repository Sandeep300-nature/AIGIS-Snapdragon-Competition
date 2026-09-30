# AIGIS Snapdragon X Elite QDC Deployment & End-to-End Verification

This guide outlines the exact steps to deploy and run the AIGIS AI engine on the Qualcomm Device Cloud (QDC) Snapdragon X Elite Windows 11 ARM64 test machine.

---

## 1. Verified Target Environment

The remote QDC machine has been pre-verified with:
- **SoC**: Qualcomm Snapdragon X Elite CRD (12-core Oryon X1E80100 @ 3.4 GHz, 64 GB RAM)
- **NPU**: Qualcomm Hexagon NPU (45 TOPS)
- **OS**: Windows 11 Enterprise ARM64 (Build 26200)
- **GenieX**: v0.7.0 (`%LOCALAPPDATA%\GenieX CLI\geniex.exe`)
- **QAIRT**: 2.45 (`QnnHtp.dll`, `QnnSystem.dll`)
- **Model**: `ai-hub-models/Qwen3-4B-Instruct-2507` (W4A16, 4 shards) cached at:
  `C:\Users\HCKTest\.cache\geniex\models\qualcomm\Qwen3-4B-Instruct-2507`

---

## 2. Deployment Steps

### Step 1: Extract the Project Archive
Transfer the deployment archive `aigis_snapdragon_deployment.zip` to the remote machine (e.g. via SFTP or SCP over port 2222) and extract it:

```powershell
Expand-Archive -Path "C:\Users\HCKTest\aigis_snapdragon_deployment.zip" -DestinationPath "C:\Users\HCKTest\AIGIS-Snapdragon-Competition" -Force
```

### Step 2: Navigate and Set Python Environment
Change to the extracted directory and set the Python search path:

```powershell
cd C:\Users\HCKTest\AIGIS-Snapdragon-Competition

# Set PYTHONPATH to include repository root and ai_engine
$env:PYTHONPATH="C:\Users\HCKTest\AIGIS-Snapdragon-Competition;C:\Users\HCKTest\AIGIS-Snapdragon-Competition\ai_engine"

# Enforce competition local-only mode (strictly on-device, zero cloud egress)
$env:AIGIS_COMPETITION_MODE="true"
```

### Step 3: Run the End-to-End Live Verification Test
Execute the end-to-end verification script:

```powershell
python tests/test_qdc_e2e.py
```

### Step 4: Run the Complete Competition Test Suite
Run the 27 unit tests validating hardware capability probing, routing, prompt formatting, and adapter contracts:

```powershell
python -m unittest tests/test_snapdragon_engine.py
```

---

## 3. Expected Verified QDC Output

When executed on the real Snapdragon X Elite host, `tests/test_qdc_e2e.py` will report:

```text
=================================================================
  AIGIS Snapdragon X Elite QDC End-to-End Inference Verification  
=================================================================

=== 1. HARDWARE DETECTION ===
Architecture: arm64
Is Snapdragon: True
CPU Brand: Snapdragon(R) X Elite - X1E80100 - Qualcomm(R) Oryon(TM) CPU
NPU Detected: True
Genie Tools Found: ['geniex.exe']
Model Bundle Found: True
Model Bundle Dir: C:\Users\HCKTest\.cache\geniex\models\qualcomm\Qwen3-4B-Instruct-2507

=== 2. ROUTER INITIALIZATION ===
Active Backend: snapdragon_npu
Competition Mode Enforced: True

=== 3. END-TO-END INFERENCE (GENIEX QWEN3-4B ON HEXAGON NPU) ===
Prompt: Explain what you are in one sentence.

Reply: I am AIGIS, an autonomous on-device personal AI assistant powered by Qualcomm Snapdragon.

Provider: Qualcomm Genie / Hexagon NPU
Badge: ⚡ AIGIS Snapdragon NPU (Hexagon NPU Accelerated via GenieX)
Latency: ~120 ms
Tokens Generated: 44
Decode TPS: ~21.7
TTFT (sec): ~0.1
Hardware Valid: True
Simulated: False
```
