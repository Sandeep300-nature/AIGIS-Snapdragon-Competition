# AIGIS Model Assets & Qualcomm AI Hub Integration

This directory contains configuration metadata and local caches for on-device models in AIGIS.

---

## 1. Verified Model Inventory

| Model Name | Task | Active Target | Runtime / Provider | Source |
| :--- | :--- | :--- | :--- | :--- |
| **SmolLM2-135M-Instruct** | Local General AI (Portable) | x86_64 Host CPU | PyTorch (`transformers`) | Hugging Face Hub (Public Apache-2.0) |
| **faster-whisper-tiny.en** | Local Voice STT | x86_64 Host CPU | CTranslate2 (`int8` compute) | Systran / OpenAI (MIT) |
| **Llama-v3.2-1B-Instruct** | Snapdragon Accelerated AI | Qualcomm Hexagon NPU | ONNX Runtime GenAI (`QNNExecutionProvider`) | Qualcomm AI Hub (Meta Llama 3.2 License) |

---

## 2. Qualcomm Model Distribution Policy (Strict Zero Redistribution)

> [!IMPORTANT]
> **Licensing Notice:** Due to Meta Llama 3.2 community license terms and Qualcomm AI Hub terms of use, compiled model binaries (`.onnx`, `.bin`, `.dlc`, `.data`) are **NOT committed to Git**.
> 
> AIGIS utilizes an **authenticated local discovery strategy**:
> - The application inspects `ai_engine/models/Llama-v3.2-1B-Instruct-w4a16` (or the directory pointed to by `AIGIS_SNAPDRAGON_MODEL_DIR`).
> - If the model artifact is missing, AIGIS truthfully reports `state: "model_artifact_unavailable"` and automatically delegates local queries to `SmolLM2-135M-Instruct` on CPU.

---

## 3. How to Obtain the Qualcomm Model via Qualcomm AI Hub CLI

To generate and install the verified `Llama-v3.2-1B-Instruct` (`DEFAULT_W4A16`) checkpoint for Snapdragon X Elite / X Plus:

### Step 1: Create a Dedicated Python 3.11 Environment
Qualcomm model compilation tooling currently requires Python < 3.14. Use an isolated virtual environment:
```powershell
py -3.11 -m venv .venv_qai
.venv_qai\Scripts\activate
pip install qai-hub
```

### Step 2: Authenticate with Qualcomm AI Hub
Obtain your API token from [aihub.qualcomm.com](https://aihub.qualcomm.com) and configure the CLI:
```powershell
qai-hub configure --api_token <YOUR_QUALCOMM_AI_HUB_API_TOKEN>
```

### Step 3: Compile and Export for Snapdragon X Elite (Windows on ARM)
Submit the compilation job to Qualcomm AI Hub:
```powershell
qai-hub export-model `
  --model llama_v3_2_1b_instruct `
  --checkpoint DEFAULT_W4A16 `
  --device "Snapdragon X Elite CRD" `
  --runtime onnx `
  --output-dir ./Llama-v3.2-1B-Instruct-w4a16
```

### Step 4: Place the Model in AIGIS
Move the exported assets into `ai_engine/models/Llama-v3.2-1B-Instruct-w4a16`:
```text
ai_engine/models/Llama-v3.2-1B-Instruct-w4a16/
├── genai_config.json
├── model.onnx
├── model.onnx.data
├── tokenizer.json
└── tokenizer_config.json
```

Once placed, AIGIS's `QualcommModelRunner` automatically transitions from `model_artifact_unavailable` to `fully_configured` when running on a physical Snapdragon Copilot+ PC.
