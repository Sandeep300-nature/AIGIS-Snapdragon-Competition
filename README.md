# AIGIS — Hardware-Aware On-Device AI Assistant

> **Qualcomm Snapdragon X Elite Competition Submission**  
> An autonomous, hardware-aware personal AI assistant featuring zero-fabrication hardware detection, multi-tier on-device inference routing, system automation, and real-time telemetry.

---

## 1. Project Overview

**AIGIS** (Autonomous Intelligent Guardian & Interface System) is an on-device, hardware-aware AI assistant designed to run locally with zero cloud egress while dynamically adapting to the host machine's physical compute accelerators.

In this **Snapdragon Competition Version**, AIGIS is optimized for the **Qualcomm Snapdragon X Elite / X Plus** platform:
- **Hardware-Aware Routing**: Probes host architecture, detects Qualcomm Hexagon NPUs and QNN Execution Providers, and dynamically chooses the optimal execution path.
- **On-Device Intelligence**: Integrates **Qualcomm AI Hub** models (`Qwen3-4B-Instruct-2507` W4A16) accelerated on the Hexagon NPU via Qualcomm GenieX / QAIRT, with automatic on-device CPU fallback (`SmolLM2-135M-Instruct`) on x86_64 systems.
- **Zero Fabrication**: AIGIS strictly reports dynamically verified hardware metrics and runtime states—it never simulates or fakes NPU execution or system telemetry.
- **Local-First Privacy**: Operating in **Competition Mode** (`AIGIS_COMPETITION_MODE=true`), all inference, conversation state, memory retrieval, and system actions execute strictly on-device.

### Multi-Tier Distributed Architecture
AIGIS is engineered across three interconnected services:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        React 19 + Vite Frontend                        │
│                         (http://localhost:5173)                        │
│   • 3D Plasma Canvas HUD   • Real-Time Metrics HUD   • Terminal HUD    │
└───────────────────▲───────────────────────────────▲────────────────────┘
                    │                               │
                    │ REST / SSE                    │ Direct Telemetry &
                    │ (Port 8080)                   │ STT Audio (Port 8000)
                    ▼                               │
┌──────────────────────────────────────────────┐    │
│           Spring Boot 3.4.2 Backend          │    │
│            (http://localhost:8080)           │    │
│   • REST Controllers   • H2 Memory Vault     │    │
│   • Session Management • AI Gateway Proxy    │    │
└───────────────────▲──────────────────────────┘    │
                    │                               │
                    │ HTTP Forwarding (Port 8000)   │
                    ▼                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         Python FastAPI AI Engine                       │
│                         (http://localhost:8000)                        │
│   • HardwareDetector (Probing CPU, GPU, NPU, RAM, Disks, Batteries)    │
│   • IntentTaskRouter (Deterministic vs Local SLM vs Snapdragon NPU)    │
│   • SnapdragonNPUEngine (GenieX / QAIRT / QNN Hexagon NPU Runner)      │
│   • LocalEngine (SmolLM2-135M CPU Fallback)                            │
│   • DesktopActionService (App Launcher, Explorer, Volume & Media)      │
│   • Native Reminder Scheduler & Deep Document Search (RAG)             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture & Components

### 1. Frontend (`frontend/`)
- **Technology**: React 19, Vite 8, Three.js, Vanilla CSS.
- **User Interface**:
  - **Dynamic 3D Plasma Sphere**: Interactive WebGL mesh with audio-reactive reactivity representing AI thought and voice states.
  - **System Metrics HUD**: Live telemetry cards displaying real-time CPU utilization, GPU metrics, RAM usage, disk space, and active AI engine badge.
  - **Weather & Time HUD**: Local OS time, date, and weather widgets.
  - **Terminal HUD**: Multi-modal chat console supporting text input, voice transcription, and system action logs.
  - **Management Modals**: Dedicated interfaces for Memory Management, Document Knowledge Vault, and Native Reminders.

### 2. Backend (`backend/`)
- **Technology**: Java 21, Spring Boot 3.4.2, Spring Data JPA, Apache Tomcat.
- **Persistence**: Embedded H2 database engine (`jdbc:h2:file:./data/aigisdb`) providing zero-external-dependency persistence for conversation memory, user sessions, and preferences.
- **Service Layer**:
  - `ChatController`: Exposes `/api/v1/chat` and session history endpoints.
  - `GroqAiService`: Proxies and routes inference requests to the Python AI Engine.
  - `MemoryManagementController`: Manages conversation memory persistence.
  - `DesktopControlController` & `DeepDocSearchController`: Exposes desktop automation and local document search APIs.
  - `WebConfig`: Configures CORS policy permitting local frontend communication.

### 3. Python AI Engine (`ai_engine/`)
- **Technology**: Python 3.10+ (tested on 3.13), FastAPI, Uvicorn, PyTorch, Transformers, ONNX Runtime, Faster-Whisper.
- **Key Modules**:
  - `hardware/detector.py`: Truthful hardware detection layer inspecting OS, CPU brand, cores, GPU, RAM, ONNX Execution Providers, and Qualcomm runtime DLLs.
  - `engine/router.py` (`IntentTaskRouter`): Hardware-aware polymorphic task dispatcher enforcing on-device competition boundaries.
  - `engine/snapdragon_engine.py` & `engine/genie_provider.py`: Qualcomm GenieX and QAIRT execution runtime for Snapdragon Hexagon NPUs.
  - `engine/local_engine.py`: Portable CPU engine running `SmolLM2-135M-Instruct`.
  - `engine/deterministic.py`: Instant deterministic handlers for clock, date, and hardware telemetry queries without LLM invocation.
  - `desktop_control.py`: Windows desktop automation executing application launches, media keys, volume control, and session locking.
  - `reminders/`: Native background scheduler managing time-based alerts and active notifications.
  - `privacy/`: Security guard evaluating PII safety and preventing unintended cloud transmission.

---

## 3. System & Hardware Telemetry

AIGIS implements a **truthful telemetry subsystem** (`HardwareDetector`) that serves as the single source of truth for both the frontend HUD and conversational responses.

### Telemetry Capabilities Implemented
| Component | Metrics Captured | Detection Method |
| :--- | :--- | :--- |
| **CPU** | Brand, model, physical & logical core count, live usage %, clock speed (GHz) | `psutil`, `winreg` (Windows CentralProcessor registry), `os.cpu_count()` |
| **RAM / Memory** | Total GB, used GB, available GB, usage % | `psutil.virtual_memory()` |
| **GPU** | Discrete vs. integrated GPU, vendor (NVIDIA/Intel/AMD/Qualcomm), VRAM total/used/free, usage %, temperature | `nvidia-smi` (NVIDIA) or `Win32_VideoController` PowerShell CIM probe |
| **Storage** | Primary drive (C:) total GB, used GB, free GB, usage %, read/write delta speeds | `psutil.disk_usage()`, `psutil.disk_io_counters()` |
| **Battery** | Charge percentage, AC power connection state, charging/discharging status, estimated time remaining | `psutil.sensors_battery()` |
| **Operating System** | OS system, release, build version, platform, uptime | `platform`, `psutil.boot_time()` |
| **Process Count** | Total running processes, active thread count | Native Windows `psapi.GetPerformanceInfo()` (<0.5ms) with `psutil` fallback |
| **Network I/O** | Real-time upload and download speeds (KB/s or MB/s) | `psutil.net_io_counters()` delta tracking |

### Distinction: Detection vs. Telemetry vs. Inference
- **Hardware Detection**: Identifies whether the processor is an ARM64 Qualcomm Snapdragon (e.g. Snapdragon X Elite) and whether Qualcomm runtime DLLs (`QnnHtp.dll`, `genie.dll`) or tools (`geniex.exe`) exist.
- **Hardware Telemetry**: Collects live, point-in-time performance counters (CPU %, RAM %, disk I/O, battery). If a sensor is not accessible via standard OS APIs (such as CPU core temperature without kernel drivers), AIGIS **truthfully reports `unavailable`**.
- **Accelerated Inference**: Executes neural network weights physically on the Hexagon NPU via GenieX/QAIRT. If running on an x86_64 host or without NPU runtime libraries, AIGIS does **not** claim NPU acceleration and routes inference to the CPU engine.

---

## 4. Assistant Capabilities

AIGIS provides natural language intent routing that translates conversational user input into actions, queries, or AI responses.

### 1. Application Launching
AIGIS launches authorized desktop applications using natural language:
- `"Open Notepad"` $\rightarrow$ Launches `notepad.exe`
- `"Open Calculator"` / `"Open calc"` $\rightarrow$ Launches `calc.exe`
- `"Open File Explorer"` / `"Open Explorer"` $\rightarrow$ Launches `explorer.exe`
- `"Open Chrome"` / `"Open Edge"` / `"Open browser"` $\rightarrow$ Launches browser
- `"Open VS Code"` / `"Open Code"` $\rightarrow$ Launches `code`
- `"Open Spotify"` $\rightarrow$ Launches `spotify.exe`
- `"Open Terminal"` / `"Open cmd"` $\rightarrow$ Launches Windows Terminal / Command Prompt

### 2. Folder Navigation
- `"Open Downloads folder"` $\rightarrow$ Opens `%USERPROFILE%\Downloads` in Explorer
- `"Open Documents"` $\rightarrow$ Opens `%USERPROFILE%\Documents`
- `"Open Desktop"` $\rightarrow$ Opens `%USERPROFILE%\Desktop`
- `"Open C drive"` $\rightarrow$ Opens `C:\`

### 3. Media & Volume Controls
Simulates native Windows multimedia virtual keystrokes:
- `"Mute volume"` / `"Mute"` $\rightarrow$ Toggles system audio mute
- `"Volume up"` / `"Increase volume"` $\rightarrow$ Increases audio level
- `"Volume down"` / `"Lower volume"` $\rightarrow$ Decreases audio level
- `"Play music"` / `"Pause media"` $\rightarrow$ Toggles media playback
- `"Next track"` / `"Skip song"` $\rightarrow$ Skips to next track
- `"Previous track"` $\rightarrow$ Navigates to previous track

### 4. Workstation Security & Power Actions
- `"Lock workstation"` / `"Lock screen"` $\rightarrow$ Executes `LockWorkStation` immediately.
- `"Put PC to sleep"` $\rightarrow$ Suspends workstation.
- Destructive commands (`"Shutdown"`, `"Restart"`) trigger a **Safety Interceptor** requiring the user to explicitly confirm with `"CONFIRM"` before execution.

### 5. Web Shortcuts & Browser Navigation
- `"Open YouTube"` $\rightarrow$ Resolves URL to `https://www.youtube.com`
- `"Search on YouTube for Snapdragon X Elite"` $\rightarrow$ Opens `https://www.youtube.com/results?search_query=Snapdragon+X+Elite`
- Supports shortcuts for GitHub, Google, Wikipedia, Twitter, and Reddit.

### 6. Deterministic Clock & System Telemetry Queries
Bypasses LLMs entirely to return instantaneous, exact OS metrics:
- `"What time is it?"` / `"Current time"` $\rightarrow$ Instant local clock response
- `"What's today's date?"` $\rightarrow$ Instant calendar response
- `"What is my CPU usage?"` $\rightarrow$ Live CPU percentage from `psutil`
- `"Show system information"` / `"What is the current system status?"` $\rightarrow$ Aggregated CPU, RAM, OS, and GPU report
- `"How much RAM is free?"` $\rightarrow$ Available memory metrics
- `"What hardware is available?"` $\rightarrow$ Probed CPU, GPU, and NPU availability

---

## 5. Snapdragon & Qualcomm AI Hub Integration

The repository features dedicated integration code for Qualcomm hardware:

### 1. Hardware Awareness (`HardwareDetector`)
- Reads Windows registry (`HARDWARE\DESCRIPTION\System\CentralProcessor\0`) and CPU brand strings to identify Snapdragon SoCs (`X Elite`, `X Plus`, `SC8`, `Kryo`).
- Probes for ARM64 machine architecture (`platform.machine() in ["ARM64", "AARCH64"]`).
- Inspects system paths and `%LOCALAPPDATA%\GenieX CLI\` for verified executables (`geniex.exe`, `genie-t2t-run.exe`, `geniex-bench.exe`).
- Verifies QAIRT / QNN runtime libraries (`QnnHtp.dll`, `QnnSystem.dll`, `genie.dll`).

### 2. Qualcomm AI Hub Model Bundle
- Configured for `Qwen3-4B-Instruct-2507` (W4A16, 4 shards).
- Checks local model cache directories:
  - `%USERPROFILE%\.cache\geniex\models\qualcomm\Qwen3-4B-Instruct-2507`
  - Custom location via environment variable `$env:AIGIS_GENIE_MODEL_DIR`.

### 3. Execution Provider & Runtime Support
- Probes `onnxruntime` for registered providers: `QNNExecutionProvider`, `CUDAExecutionProvider`, `DmlExecutionProvider`, `CPUExecutionProvider`.
- Probes environment variables: `QNN_SDK_ROOT`, `QUALCOMM_SDK_ROOT`, `GENIE_ROOT`, `QAIRT_SDK_ROOT`.

### 4. Strict 6-State Runtime Lifecycle
Rather than collapsing into a simple boolean, `SnapdragonRuntimeState` distinguishes:
1. `HARDWARE_UNAVAILABLE`: Host is non-ARM64 / non-Snapdragon CPU.
2. `QNN_UNAVAILABLE`: ARM64 host, but QNN Execution Provider not registered.
3. `RUNTIME_INCOMPLETE`: QNN present, but Qualcomm Genie runtime DLLs missing.
4. `MODEL_ARTIFACT_UNAVAILABLE`: Hardware & runtime detected, but model weights missing.
5. `FULLY_CONFIGURED`: Hardware + QNN + Genie Runtime + Model Artifact verified.
6. `INFERENCE_SUCCESSFUL`: Physical execution on Hexagon NPU verified.

---

## 6. Quick Start Guide

### Prerequisites
| Tool | Required Version | Checked / Supported |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 (x64 or ARM64 Snapdragon) | Windows 11 Enterprise / Pro |
| **Python** | 3.10+ | Python 3.13 |
| **Java (JDK)** | 21+ | Java 21 / 25 |
| **Maven** | 3.9+ | Apache Maven 3.9 |
| **Node.js** | 18+ | Node.js v24 |
| **npm** | 9+ | npm 11 |

---

### Step 1: Install Dependencies

#### Python AI Engine
From the repository root:
```powershell
pip install -r ai_engine/requirements.txt
```
*(Optional: For local on-device SLM inference and local voice transcription, ensure `torch`, `transformers`, `faster-whisper`, and `onnxruntime` are installed in your Python environment).*

#### Java Backend
From the repository root:
```powershell
cd backend
mvn clean compile
cd ..
```

#### React Frontend
From the repository root:
```powershell
cd frontend
npm install
cd ..
```

---

### Step 2: Configure Environment
Set `PYTHONPATH` so the AI engine resolves all root and sub-package modules, and enforce competition local mode:

```powershell
# Set PYTHONPATH to include repository root and ai_engine
$env:PYTHONPATH="$PWD;$PWD\ai_engine"

# Enforce competition mode (strictly on-device inference, zero cloud egress)
$env:AIGIS_COMPETITION_MODE="true"
```

---

### Step 3: Start the Services

Open three separate terminal windows:

#### Terminal 1 — Start Python AI Engine (Port 8000)
```powershell
cd ai_engine
$env:PYTHONPATH="..;."
$env:AIGIS_COMPETITION_MODE="true"
python main.py
```
*Health Check*: Verify at `http://localhost:8000/api/v1/ai/status`

#### Terminal 2 — Start Spring Boot Backend (Port 8080)
```powershell
cd backend
mvn spring-boot:run
```
*Health Check*: Verify at `http://localhost:8080/hello`

#### Terminal 3 — Start React Frontend (Port 5173)
```powershell
cd frontend
npm run dev
```
*Access Application*: Open your browser to **`http://localhost:5173`**

---

## 7. Evaluator Run Flow

```
Clone Repository
      │
      ▼
Verify Prerequisites (Python 3.10+, Java 21+, Maven 3.9+, Node 18+)
      │
      ▼
Install Dependencies (pip install, mvn compile, npm install)
      │
      ▼
Set Environment Variables ($env:PYTHONPATH, $env:AIGIS_COMPETITION_MODE="true")
      │
      ▼
Start Python AI Engine  ──► http://localhost:8000  (FastAPI + IntentTaskRouter)
      │
      ▼
Start Spring Boot API   ──► http://localhost:8080  (Spring Boot 3 + H2 Database)
      │
      ▼
Start React Frontend    ──► http://localhost:5173  (Interactive HUD & 3D Canvas)
      │
      ▼
Open Browser to http://localhost:5173
      │
      ▼
Run Live Verification & Unit Tests
```

---

## 8. Example Demo Commands

Evaluators can test these natural language prompts in the Terminal HUD or via direct REST API calls:

| Input Command | Subsystem / Intent | Expected Behavior |
| :--- | :--- | :--- |
| `"Open Notepad"` | Desktop Action | Launches Windows Notepad (`notepad.exe`) on the host system. |
| `"Open Calculator"` | Desktop Action | Launches Windows Calculator (`calc.exe`). |
| `"Open Downloads folder"` | Desktop Action | Opens `%USERPROFILE%\Downloads` in Windows File Explorer. |
| `"Open YouTube"` | Web Shortcut | Resolves YouTube and returns launch action. |
| `"What time is it?"` | Deterministic Clock | Instant response with current local OS time without calling LLM. |
| `"What is today's date?"` | Deterministic Clock | Instant response with current day, month, date, and year. |
| `"What is my CPU usage?"` | Telemetry | Queries real-time CPU utilization % from `HardwareDetector`. |
| `"Show system information"` | Telemetry | Returns summary of OS, CPU brand, RAM used/total, and GPU. |
| `"How much RAM is free?"` | Telemetry | Returns available and total system memory metrics. |
| `"Is Snapdragon NPU detected?"` | Hardware Probing | Truthfully reports if Qualcomm Hexagon NPU is physically detected. |
| `"Explain what you are in one sentence."` | General AI Inference | Generates on-device assistant description via local SLM or NPU. |

---

## 9. Project Structure

```
AIGIS-Snapdragon-Competition/
├── README.md                  # This evaluator documentation
├── README_QDC.md              # Qualcomm Device Cloud (QDC) deployment guide
├── ai_engine/                 # Python AI Engine service (FastAPI, Port 8000)
│   ├── main.py                # FastAPI entry point, REST endpoints, startup handlers
│   ├── snapdragon_engine.py   # Top-level export for Snapdragon NPU engine & runner
│   ├── desktop_control.py     # Windows application launcher & media key controller
│   ├── web_search.py          # Anti-hallucination web search & website shortcut router
│   ├── workflow_scheduler.py  # Automation and routine scheduler
│   ├── deep_doc_search.py     # Document indexing & local RAG engine
│   ├── realtime_tool_gateway.py # Tool schemas for real-time assistant execution
│   ├── memory_backup.py       # Local memory backup and restore engine
│   ├── requirements.txt       # Python dependencies
│   ├── actions/               # Action safety guard & confirmation interceptors
│   ├── engine/                # Core AI execution abstractions
│   │   ├── base_engine.py     # Abstract BaseAIEngine interface
│   │   ├── router.py          # Hardware-aware IntentTaskRouter
│   │   ├── local_engine.py    # SmolLM2-135M CPU engine
│   │   ├── snapdragon_engine.py # SnapdragonNPUEngine implementation
│   │   ├── genie_provider.py  # GenieX / QAIRT adapter & 6-state runtime validator
│   │   ├── qualcomm_runner.py # Qualcomm AI Hub model execution boundary
│   │   ├── deterministic.py   # OS clock, date, and telemetry query parsers
│   │   └── prompts.py         # Competition system prompts
│   ├── hardware/              # Hardware capability probing
│   │   └── detector.py        # Truthful CPU, GPU, NPU, RAM, OS detector
│   ├── memory/                # Conversation state, long-term memory store & journal
│   ├── models/                # Local model assets & tokenizers
│   ├── privacy/               # Local privacy guard & PII classifier
│   ├── providers/             # Legacy provider router
│   └── reminders/             # Native reminder scheduler & notification manager
├── backend/                   # Spring Boot Backend service (Port 8080)
│   ├── pom.xml                # Maven project definition (Java 21, Spring Boot 3.4.2)
│   ├── src/main/java/com/aigis/backend/
│   │   ├── AigisBackendApplication.java # Spring Boot main entry point
│   │   ├── config/            # WebConfig (CORS) & application beans
│   │   ├── controller/        # REST Controllers (Chat, Hello, Memory, Desktop, Docs)
│   │   ├── model/             # DTOs and JPA Entities for conversation memory
│   │   ├── repository/        # Spring Data JPA repositories
│   │   └── service/           # Business logic & AI routing implementation
│   └── src/main/resources/    # application.yml configuration (H2 DB, port 8080)
├── frontend/                  # React 19 + Vite Frontend (Port 5173)
│   ├── package.json           # Frontend dependencies (React 19, Three.js, Vite 8)
│   ├── vite.config.js         # Vite dev server configuration
│   ├── index.html             # Application entry HTML
│   └── src/                   # React components
│       ├── App.jsx            # Main view orchestrator & backend connection watcher
│       ├── Blob.jsx           # Three.js 3D interactive plasma canvas
│       ├── TerminalHUD.jsx    # Chat interface, prompt suggestions & command logs
│       ├── SystemMetricsHUD.jsx # Real-time CPU, GPU, RAM, Engine telemetry card
│       ├── WeatherTimeHUD.jsx # Local time and weather display
│       ├── Navbar.jsx         # Status bar, voice selector & modal navigation
│       └── utils/             # Session management & client speech handlers
├── tests/                     # Comprehensive automated test suite
│   ├── test_qdc_e2e.py        # Live QDC Snapdragon X Elite end-to-end verification
│   ├── test_snapdragon_engine.py # 32-test Snapdragon engine & routing unit tests
│   ├── test_hardware_telemetry_routing.py # Hardware probing & telemetry routing tests
│   ├── test_action_guard.py   # Desktop action safety interceptor tests
│   ├── test_privacy_guard.py  # Local privacy & PII evaluation tests
│   ├── test_memory_vault.py   # Long-term memory store & retrieval tests
│   ├── test_vector_search.py  # Local embedding vector search tests
│   ├── test_speech_voice.py   # Speech recognition & voice tests
│   ├── test_time_query_routing.py # Deterministic clock query tests
│   └── test_document_chunking.py  # Document RAG chunking tests
└── scratch/                   # Verification scripts (`verify_m4_e2e.py`)
```

---

## 10. Automated Test Suite

The repository contains an automated test suite validating hardware detection, safety interceptors, prompt formatting, and fallback behaviors.

### Run the End-to-End Live Verification
Executes the live end-to-end inference verification script:
```powershell
python tests/test_qdc_e2e.py
```
*Expected Output on Snapdragon*: Probes Qualcomm Hexagon NPU, verifies GenieX CLI, executes `Qwen3-4B-Instruct-2507`, and reports decode token-per-second telemetry.  
*Expected Output on x86_64*: Detects non-ARM64 processor, truthfully reports `hardware_unavailable`, and executes inference on the CPU engine.

### Run Unit Tests
```powershell
# Run the complete Snapdragon engine & router suite (32 tests)
python -m unittest tests/test_snapdragon_engine.py

# Run hardware telemetry routing tests
python -m unittest tests/test_hardware_telemetry_routing.py

# Run action safety guard tests
python -m unittest tests/test_action_guard.py

# Run privacy guard tests
python -m unittest tests/test_privacy_guard.py

# Run memory vault persistence tests
python -m unittest tests/test_memory_vault.py
```

---

## 11. Privacy & Local Processing Architecture

AIGIS is engineered with a strict **Local-First Privacy Architecture**:

1. **Competition Mode Enforcement**: Setting `$env:AIGIS_COMPETITION_MODE="true"` prevents any outgoing cloud calls. Private queries (memories, indexed documents, project architecture) are held exclusively on-device.
2. **Deterministic Query Interception**: Time, date, and hardware telemetry queries are answered directly from local Windows APIs without transmitting prompt text to any neural network or network endpoint.
3. **Local Database Persistence**: All session logs and conversation memories are stored locally in an embedded H2 file database (`backend/data/aigisdb`) with zero external database dependencies.
4. **Action Authorization Guard**: All desktop actions operate on local binaries with an explicit confirmation protocol for destructive operations.

---

## 12. Known Limitations

- **Physical Hexagon NPU Requirement**: Qualcomm Hexagon NPU acceleration is strictly available on physical Qualcomm Snapdragon ARM64 hardware (e.g. Snapdragon X Elite / X Plus) with Windows on ARM and the Qualcomm Genie / QAIRT runtime.
- **x86_64 Development Host Fallback**: On x86_64 development machines, the engine automatically and truthfully delegates to the portable `SmolLM2-135M-Instruct` CPU engine.
- **Hardware Temperature Sensors**: Standard Windows user-space APIs do not expose CPU core temperatures without third-party kernel drivers. AIGIS truthfully reports temperature as `unavailable` rather than hallucinating values.
- **External Web Search**: Web search via Tavily requires an active API key (`GROQ_API_KEY` / `TAVILY_API_KEY`) and is intentionally disabled in Competition Mode to guarantee on-device privacy.

---

## 13. Troubleshooting

### 1. Spring Boot Backend Unavailable (`http://localhost:8080`)
- **Symptom**: Frontend HUD displays `Backend offline (http://localhost:8080)`.
- **Fix**: Ensure Java 21+ is in your `PATH` (`java -version`). Run `mvn spring-boot:run` in the `backend/` directory and wait until Tomcat reports `Started AigisBackendApplication on port 8080`.

### 2. Python AI Engine Unavailable (`http://localhost:8000`)
- **Symptom**: Chat queries report connection failure or HTTP 500.
- **Fix**: Ensure `PYTHONPATH` includes both the repository root and `ai_engine`. Run `python main.py` inside the `ai_engine/` directory.

### 3. Missing Dependencies on Fresh Environment
- **Symptom**: `ModuleNotFoundError: No module named 'fastapi'` or `'psutil'`.
- **Fix**: Run `pip install -r ai_engine/requirements.txt`. For local neural network inference, install `torch` and `transformers`.

### 4. "Host architecture is non-ARM64; Qualcomm Hexagon NPU is physically absent"
- **Status**: **Normal behavior on x86_64 PCs.** This confirms the zero-fabrication capability detector is working truthfully. The system will automatically utilize the Tier-2 local CPU engine.

---

## 14. Competition Context

This repository represents the official competition submission for the **Qualcomm Snapdragon X Elite AI Assistant Challenge**.

The codebase demonstrates:
- **Truthful Hardware Adaptation**: Clean multi-tier abstraction gracefully handling both physical Snapdragon X Elite NPU hardware and developer fallback environments.
- **Comprehensive Local Assistant**: A fully working, distributed assistant combining modern 3D UI, robust Java enterprise middleware, and low-latency Python AI engine.
- **Zero Cloud Egress**: Strict local-only operation adhering to the competition's privacy and on-device execution goals.
