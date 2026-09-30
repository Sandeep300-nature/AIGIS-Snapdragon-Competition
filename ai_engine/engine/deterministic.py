"""
Deterministic System Query Parser and Dispatcher.
Resolves live system clock, date, and hardware queries on-device without LLM invocation.
Ensures OS-level truth, prevents LLM hallucination, and enforces local-only boundaries.
"""

import re
from datetime import datetime
from typing import Tuple, Optional, Dict, Any


LOCAL_LOCATION_EXCEPTIONS = [
    "in local time", "in my location", "in my area", "in here",
    "at present", "at the moment", "for today", "right now"
]


CONCEPTUAL_TIME_PATTERNS = [
    r"^what\s+is\s+time$",
    r"\bwhat\s+is\s+time\s+(?:dilation|travel|zone|zones|complexity|management|space|warp|perception|flow|physics|theory)\b",
    r"\bexplain\s+(?:what\s+)?time(?:\s+dilation|\s+travel)?\b",
    r"\bdefine\s+time\b",
    r"\bdefinition\s+of\s+time\b",
    r"\bmeaning\s+of\s+time\b",
    r"\bwhat\s+does\s+time\s+mean\b",
    r"\bhow\s+does\s+time\s+work\b",
    r"\bwhy\s+does\s+time\b",
    r"\bconcept\s+of\s+time\b",
    r"\btheory\s+of\s+time\b",
    r"\bhistory\s+of\s+time\b",
    r"\bspacetime\b",
]


def parse_time_date_query(query: str) -> Tuple[bool, bool, bool]:
    """
    Parses a user query to determine if it is:
    1. A deterministic local system time query (is_time)
    2. A deterministic local system date query (is_date)
    3. A remote location / external timezone query (is_remote_location)

    Normalizes casual slang (e.g. wt, u, pls), contractions, and conversational
    prefixes (can you tell me, please, do you know) while strictly protecting
    conceptual inquiries (What is time?, Explain time dilation) for General AI.

    Returns:
        (is_time, is_date, is_remote_location)
    """
    if not query:
        return False, False, False

    raw = str(query).strip().lower()

    # 1. Normalize contractions and common casual shorthand
    text = raw
    text = re.sub(r"\bwt\x27s\b", "what is", text)
    text = re.sub(r"\bwts\b", "what is", text)
    text = re.sub(r"\bwhat\x27s\b", "what is", text)
    text = re.sub(r"\bwt\b", "what", text)
    text = re.sub(r"\bu\b", "you", text)
    text = re.sub(r"\bpls\b", "please", text)

    # Normalize punctuation to spaces
    cleaned = re.sub(r"[?!.,;:]+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return False, False, False

    # 2. Conceptual Guard: preserve abstract/physics/theoretical questions for General AI
    if any(re.search(p, cleaned) for p in CONCEPTUAL_TIME_PATTERNS):
        return False, False, False

    # 3. Strip conversational address tokens, polite wrappers, and request prefixes
    stripped = re.sub(r"\b(hey\s+)?aigis\b", " ", cleaned)
    stripped = re.sub(r"\b(can|could|would|will)\s+you\s+(?:please\s+)?(?:tell\s+me|show\s+me|give\s+me|let\s+me\s+know)?\b", " ", stripped)
    stripped = re.sub(r"\bdo\s+you\s+(?:know|have)\b", " ", stripped)
    stripped = re.sub(r"\b(?:please|sir|tell\s+me|give\s+me|show\s+me|let\s+me\s+know)\b", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()

    # 4. Deterministic Clock Time Matching
    time_patterns = [
        r"^(?:the\s+)?(?:current\s+)?time(?:\s+now)?$",
        r"\bwhat(?:\s+is)?\s+(?:the\s+)?(?:current\s+)?time\b",
        r"\bwhat\s+the\s+time\s+is\b",
        r"\bwhat\s+time\s+(?:is\s+it|it\s+is)\b",
        r"\bwhat\s+time\b",
        r"\b(?:the\s+)?current\s+time\b",
        r"\b(?:local|clock)\s+time\b",
        r"\btime\s+(?:now|right\s+now)\b",
        r"\btime\s+(?:in|at|for)\b",
    ]
    is_time = any(re.search(p, stripped) for p in time_patterns) or any(re.search(p, cleaned) for p in time_patterns)

    # 5. Deterministic Date Matching
    date_patterns = [
        r"\bwhat(?:\s+is)?(?:\s+the|\s+today\x27?s)?\s+(?:current\s+)?date\b",
        r"\bwhat\s+day\s+is\s+(?:it|today)\b",
        r"\btoday\x27?s\s+date\b",
        r"\bcurrent\s+date\b",
        r"\bdate\s+today\b",
        r"^(?:the\s+)?date(?:\s+today)?$",
        r"\bdate\s+(?:in|at|for)\b",
    ]
    is_date = any(re.search(p, stripped) for p in date_patterns) or any(re.search(p, cleaned) for p in date_patterns)

    if "time" in stripped and "date" in stripped:
        if any(w in stripped for w in ["what", "current", "and"]):
            is_time = True
            is_date = True

    # 6. Remote location / external timezone check (e.g., "What time is it in Tokyo?")
    if is_time or is_date:
        remote_match = re.search(r"\b(?:in|at|for)\s+([a-z\s]+)$", cleaned)
        if remote_match:
            loc = remote_match.group(1).strip()
            if not any(exc in loc for exc in LOCAL_LOCATION_EXCEPTIONS):
                return False, False, True

    return is_time, is_date, False


def build_time_date_response(
    is_time: bool,
    is_date: bool,
    now: Optional[datetime] = None
) -> Tuple[str, str]:
    """
    Constructs canonical deterministic system response using the local operating system clock.

    Returns:
        (reply_text, intent_tag)
    """
    ts = now or datetime.now()

    if is_time and is_date:
        reply = f"It is {ts.strftime('%I:%M %p')} on {ts.strftime('%A, %B %d, %Y')}, sir."
        intent = "time_date"
    elif is_time:
        reply = f"The current time is {ts.strftime('%I:%M %p')}, sir."
        intent = "time"
    elif is_date:
        reply = f"Today is {ts.strftime('%A, %B %d, %Y')}, sir."
        intent = "date"
    else:
        reply = f"The current time is {ts.strftime('%I:%M %p')}, sir."
        intent = "time"

    return reply, intent


CONCEPTUAL_TELEMETRY_PATTERNS = [
    r"^(?:what\s+(?:is|are)\s+(?:a\s+|an\s+)?|explain\s+(?:what\s+)?|define\s+|definition\s+of\s+|meaning\s+of\s+|what\s+does\s+)(?:cpu|gpu|npu|ram|vram|telemetry|system\s+telemetry|gpu\s+telemetry|cpu\s+temperature|gpu\s+temperature)\b",
    r"\bwhat\s+does\s+(?:cpu|gpu|npu|ram|vram)\s+(?:stand\s+for|mean)\b",
    r"\bhow\s+does\s+(?:a\s+|an\s+)?(?:cpu|gpu|npu|ram)\s+work\b",
    r"\b(?:what\s+is\s+a\s+|what\s+is\s+an\s+)(?:cpu|gpu|npu|processor)\b",
    r"\bexplain\s+(?:ram|cpu|gpu|npu|telemetry|system\s+telemetry|gpu\s+telemetry|gpu\s+temperature|cpu\s+temperature)\b",
    r"^what\s+is\s+(?:system\s+)?telemetry$",
    r"^what\s+is\s+gpu\s+telemetry$",
    r"^what\s+is\s+a\s+cpu$",
    r"^what\s+is\s+a\s+gpu$",
    r"^what\s+is\s+an\s+npu$",
]

PERSONAL_TELEMETRY_MARKERS = (
    r"\b(my|our|this|current|installed|detected|i have|am i using|running on|"
    r"on this (?:machine|pc|device|laptop|system)|in (?:my|the|this) (?:system|machine|pc|device)|"
    r"on my machine|in my system)\b"
)


def parse_telemetry_query(query: str) -> bool:
    """
    Parses a user query to determine if it is a local system telemetry or hardware inquiry.
    Guards against conceptual questions (e.g. 'What is system telemetry?', 'Explain RAM'),
    preserving them for General AI / LLM knowledge processing.

    Returns:
        bool: True if query asks for local system hardware telemetry, False otherwise.
    """
    if not query:
        return False
    raw = str(query).strip().lower()
    raw = raw.replace("’", "'").replace("‘", "'").replace("`", "'").replace("“", '"').replace("”", '"')
    cleaned = re.sub(r"[?!.,;:]+", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 1. Conceptual Guard
    # Questions asking for definitions, explanations, or concepts in the abstract without referring to this device
    is_conceptual = any(re.search(p, cleaned) for p in CONCEPTUAL_TELEMETRY_PATTERNS)
    has_personal = bool(re.search(PERSONAL_TELEMETRY_MARKERS, cleaned))
    if is_conceptual and not has_personal:
        return False

    # 2. General telemetry inquiries
    gen_patterns = [
        r"\b(?:system\s+)?telemetry\b",
        r"\b(?:system|hardware|device|machine|workstation)\s+(?:status|specs?|specifications|metrics|info|information)\b",
        r"\btell\s+me\s+about\s+(?:my\s+|the\s+|this\s+)?(?:system|machine|device|workstation|pc|hardware)\b",
        r"\bwhat(?:\x27s|'s|\s+is)\s+(?:happening|going\s+on)\s+(?:in|on|with)\s+(?:my|the|this)?\s*(?:system|machine|pc|workstation)\b",
        r"\bwhat(?:\x27s|'s|\s+is)?\s+happening\s+on\s+(?:my|this)\s+(?:machine|system|device|pc)\b",
        r"\bshow\s+(?:me\s+)?(?:my\s+|the\s+)?hardware\s+(?:status|telemetry|specs?)\b",
        r"\bcan\s+(?:u|you)\s+tell\s+me\s+(?:my\s+|the\s+)?system\s+telemetry\b",
        r"\bcan\s+(?:u|you)\s+tell\s+me\s+what(?:\x27s|'s|\s+is)\s+happening\s+in\s+my\s+system\b",
        r"\bwhat\s+is\s+my\s+system\s+status\b",
        r"\bwhat(?:\x27s|'s|\s+is)\s+(?:my\s+|the\s+)?system\s+status\b",
        r"\b(?:my|the|our|this)\s+(?:hardware|telemetry|specs?|specifications)\b",
        r"\bwhat\s+(?:hardware|specs?|specifications)\s+(?:do\s+(?:i|we|you)\s+have|are\s+(?:you|we)\s+using|are\s+you\s+running\s+on|am\s+i\s+(?:using|on|running\s+on))\b",
        r"\bwhat\s+(?:machine|device|system|pc)\s+(?:are\s+you|am\s+i)\s+(?:running|executing)\s+on\b",
        r"\bwhat\s+hardware\s+(?:are\s+you|am\s+i|is\s+this|is\s+detected|is\s+installed)\b",
        r"\bwhat\s+are\s+you\s+running\s+on\b",
        r"\bwhat\s+are\s+(?:my\s+|your\s+|our\s+|the\s+)?(?:system\s+)?specs\b",
    ]
    if any(re.search(p, cleaned) for p in gen_patterns):
        return True

    # 3. Component inquiries with personal context or direct state queries
    comp_patterns = [
        r"\bwhat(?:\x27s|'s|\s+is)\s+(?:my\s+|the\s+|our\s+)?(?:cpu|gpu|ram|storage|battery|architecture|vram|processor|graphics)\b",
        r"\bwhat\s+(?:cpu|gpu|processor|graphics(?:\s+card)?|video\s+card)\s+(?:do\s+i\s+have|am\s+i\s+using|do\s+we\s+have|is\s+(?:this|installed|detected))\b",
        r"\bhow\s+much\s+(?:ram|storage|memory|disk\s+space|vram|gpu\s+memory|space)\s+(?:do\s+i\s+have|am\s+i\s+using|is\s+(?:used|free|available|left|remaining))\b",
        r"\bhow\s+much\s+space\s+is\s+(?:free|left|available)\s+(?:on|in)\s+(?:c|c:|c\s+drive|drive|disk)\b",
        r"\bwhat(?:\x27s|'s|\s+is)?(?:\s+(?:the|my|current))?\s+(?:ram|cpu|gpu|storage|disk|memory|vram)\s+(?:usage|utilization|load|temp|temperature)\b",
        r"\bwhat(?:\x27s|'s|\s+is)\s+(?:my\s+|the\s+)?(?:cpu|gpu|processor|graphics)\s+temp(?:erature)?\b",
        r"\bwhat\s+is\s+(?:my\s+|the\s+)?(?:cpu|gpu|processor|graphics)\s+temperature\b",
        r"\bhow\s+hot\s+(?:is|are)\s+(?:my\s+|the\s+|this\s+)?(?:cpu|gpu|processor|graphics|system|machine|device|laptop)\b",
        r"\b(?:what(?:\x27s|'s|\s+is)\s+(?:the\s+|my\s+)?)?(?:temp|temperature)\s+of\s+(?:my\s+|the\s+)?(?:cpu|gpu|processor|graphics|system|machine)\b",
        r"\bis\s+(?:my\s+|the\s+)?(?:cpu|gpu|processor|graphics|system)\s+(?:hot|overheating)\b",
        r"\btell\s+me\s+my\s+cpu\s+and\s+gpu\b",
        r"\b(?:cpu\s+and\s+gpu|gpu\s+and\s+cpu)\b",
        r"\b(?:is|are)\s+(?:the\s+|my\s+)?(?:snapdragon|npu|hexagon|gpu|cpu|cuda|accelerator)\s+(?:detected|active|available|running|present)\b",
        r"\b(?:npu|snapdragon)\s+detected\b",
        r"\b(?:what\s+is|what\s+are|tell\s+me|show\s+me|check)\s+(?:my|the|this|our)?\s*(?:cpu|gpu|npu|architecture|processor|hardware|vram|ram|storage)\b",
    ]
    if any(re.search(p, cleaned) for p in comp_patterns):
        return True

    return False


def get_telemetry_focus(query: str) -> str:
    """
    Determines the specific hardware focus of a telemetry inquiry.
    Returns: 'cpu', 'cpu_usage', 'gpu', 'gpu_usage', 'vram', 'cpu_and_gpu',
             'memory', 'storage', 'temperature_cpu', 'temperature_gpu', 'temperature',
             'host_hardware', 'npu', 'battery', 'architecture', or 'all'.
    """
    if not query:
        return "all"
    raw = str(query).strip().lower()
    raw = raw.replace("’", "'").replace("‘", "'").replace("`", "'")
    cleaned = re.sub(r"[?!.,;:]+", " ", raw).strip()

    # Temperature specific
    if any(k in cleaned for k in ["temperature", "temp", "hot", "thermal", "overheat"]):
        if any(c in cleaned for c in ["cpu", "processor"]):
            return "temperature_cpu"
        elif any(g in cleaned for g in ["gpu", "graphics", "video card", "display card"]):
            return "temperature_gpu"
        return "temperature"

    # CPU and GPU combined
    if ("cpu" in cleaned and "gpu" in cleaned) or ("processor" in cleaned and "graphics" in cleaned):
        return "cpu_and_gpu"

    # VRAM / GPU memory specific
    if "vram" in cleaned or ("gpu" in cleaned and "memory" in cleaned) or ("graphics" in cleaned and "memory" in cleaned):
        return "vram"

    # CPU usage specific
    if ("cpu" in cleaned or "processor" in cleaned) and any(u in cleaned for u in ["usage", "utilization", "load", "percent", "%"]):
        return "cpu_usage"

    # CPU specific
    if any(k in cleaned for k in ["cpu", "processor"]) and not any(k in cleaned for k in ["gpu", "npu"]):
        return "cpu"

    # GPU usage specific
    if any(k in cleaned for k in ["gpu", "graphics"]) and any(u in cleaned for u in ["usage", "utilization", "load"]):
        return "gpu_usage"

    # GPU specific
    if any(k in cleaned for k in ["gpu", "graphics", "video card", "display card"]):
        return "gpu"

    # Memory / RAM specific
    if any(k in cleaned for k in ["ram", "memory"]):
        return "memory"

    # Storage / Disk specific
    if any(k in cleaned for k in ["storage", "disk", "drive", "space"]):
        return "storage"

    # Battery specific
    if "battery" in cleaned:
        return "battery"

    # Architecture specific
    if "architecture" in cleaned:
        return "architecture"

    # NPU specific
    if any(k in cleaned for k in ["npu", "snapdragon", "hexagon"]):
        return "npu"

    # Host hardware specific
    if any(p in cleaned for p in [
        "hardware are you", "are you running on", "machine are you", "what hardware",
        "what are you running on", "what machine", "my specs", "your specs", "our specs",
        "system specs", "hardware specs", "machine specs", "system info",
        "about my system", "tell me about my system", "what are my specs"
    ]) or re.search(r"\b(?:what\s+are\s+)?(?:my\s+|the\s+)?(?:system\s+)?specs\b", cleaned):
        return "host_hardware"

    return "all"


def build_telemetry_response(
    caps: Optional[Dict[str, Any]] = None,
    accelerator_label: Optional[str] = None,
    query: Optional[str] = None,
    telemetry_data: Optional[Dict[str, Any]] = None
) -> Tuple[str, str]:
    """
    Constructs canonical deterministic system response using verified HardwareDetector capabilities.
    Zero fabricated values. Consumes the same live telemetry payload that powers the frontend.

    Returns:
        (reply_text, intent_tag)
    """
    try:
        from hardware.detector import HardwareDetector
    except ImportError:
        try:
            from ai_engine.hardware.detector import HardwareDetector
        except Exception:
            HardwareDetector = None

    if telemetry_data is None and HardwareDetector is not None:
        try:
            telemetry_data = HardwareDetector.get_system_telemetry(accelerator_label)
        except Exception:
            telemetry_data = {}

    if caps is None and HardwareDetector is not None:
        try:
            caps = HardwareDetector.get_capabilities()
        except Exception:
            caps = {}
    elif caps is None:
        caps = {}

    t = telemetry_data or {}
    ident = t.get("identity", {})
    cpu = t.get("cpu", {})
    gpu = t.get("gpu", {})
    mem = t.get("memory", {})
    storage = t.get("storage", {})
    battery = t.get("battery", {})
    ai_hw = t.get("aiHardware", {})
    sys_info = t.get("system", {})

    device_type = ident.get("deviceType") or caps.get("deviceType", "Host")
    arch = ident.get("architecture") or caps.get("architecture", "Unknown")
    cpu_brand = cpu.get("brand") or caps.get("cpu", {}).get("brand", "Unknown CPU")
    logical_cores = cpu.get("logicalCores") or caps.get("cpu", {}).get("logicalCores", 0)
    physical_cores = cpu.get("physicalCores") or caps.get("cpu", {}).get("physicalCores", 0)
    cpu_usage = cpu.get("usage", 0)
    clock_speed = cpu.get("clockSpeed", "unavailable")
    cpu_temp = cpu.get("temp", "unavailable")
    if cpu_temp != "unavailable" and isinstance(cpu_temp, (int, float)):
        cpu_temp_str = f"{cpu_temp}°C"
    else:
        cpu_temp_str = "unavailable"

    gpu_name = gpu.get("name") or caps.get("gpu", {}).get("name", "Unknown GPU")
    gpu_usage = gpu.get("usage", 0)
    vram_str = gpu.get("vramStr", "unavailable")
    gpu_temp = gpu.get("temp", "unavailable")
    if gpu_temp != "unavailable" and isinstance(gpu_temp, (int, float)):
        gpu_temp_str = f"{gpu_temp}°C"
    else:
        gpu_temp_str = "unavailable"

    ram_used = mem.get("ramUsed", 0.0)
    ram_total = mem.get("ramTotal", 0.0)
    ram_usage = mem.get("usage", 0.0)
    avail_ram = mem.get("availableGb", 0.0)

    disk_used = storage.get("cDriveUsed", 0.0)
    disk_total = storage.get("cDriveTotal", 0.0)
    free_disk = storage.get("freeGb", 0.0)
    disk_usage = storage.get("usage", 0.0)
    disk_read = storage.get("readSpeed", "unavailable")
    disk_write = storage.get("writeSpeed", "unavailable")

    battery_str = battery.get("batteryStr", "unavailable")
    npu_status = ai_hw.get("npuStatus") or caps.get("accelerators", {}).get("snapdragonNpu", {}).get("status", "Not detected")
    runtime = accelerator_label or ai_hw.get("activeRuntime") or "Local On-Device"

    uptime_str = sys_info.get("uptime", "unavailable")
    process_count = sys_info.get("processCount", "unavailable")
    active_threads = sys_info.get("activeThreads", "unavailable")

    focus = get_telemetry_focus(query or "")

    if focus == "cpu":
        reply = (
            f"Workstation Hardware Telemetry — Processor, sir:\n"
            f"• Processor: {cpu_brand} ({physical_cores} physical cores, {logical_cores} logical threads)\n"
            f"• CPU Usage: {cpu_usage}%\n"
            f"• CPU Clock Speed: {clock_speed}\n"
            f"• CPU Temperature: {cpu_temp_str}\n"
            f"• Active AI Execution Runtime: {runtime}"
        )
    elif focus == "cpu_usage":
        reply = (
            f"Workstation Hardware Telemetry — CPU Usage, sir:\n"
            f"• Processor: {cpu_brand}\n"
            f"• CPU Usage: {cpu_usage}%\n"
            f"• CPU Clock Speed: {clock_speed}\n"
            f"• CPU Temperature: {cpu_temp_str}\n"
            f"• Active AI Execution Runtime: {runtime}"
        )
    elif focus == "gpu":
        reply = (
            f"Workstation Hardware Telemetry — Physical GPU, sir:\n"
            f"• Physical GPU: {gpu_name}\n"
            f"• GPU Memory: {vram_str}\n"
            f"• GPU Utilization: {gpu_usage}%\n"
            f"• GPU Temperature: {gpu_temp_str}\n"
            f"• Active AI Execution Runtime: {runtime}"
        )
    elif focus == "gpu_usage":
        reply = (
            f"Workstation Hardware Telemetry — GPU Utilization, sir:\n"
            f"• Physical GPU: {gpu_name}\n"
            f"• GPU Utilization: {gpu_usage}%\n"
            f"• GPU Temperature: {gpu_temp_str}\n"
            f"• GPU Memory: {vram_str}"
        )
    elif focus == "vram":
        reply = (
            f"Workstation Hardware Telemetry — GPU Memory (VRAM), sir:\n"
            f"• Physical GPU: {gpu_name}\n"
            f"• VRAM (Dedicated GPU Memory): {vram_str}\n"
            f"• GPU Utilization: {gpu_usage}%\n"
            f"• GPU Temperature: {gpu_temp_str}"
        )
    elif focus == "cpu_and_gpu":
        reply = (
            f"Workstation Hardware Telemetry — Processor and GPU, sir:\n"
            f"• Processor: {cpu_brand} ({logical_cores} threads)\n"
            f"• CPU Usage: {cpu_usage}%\n"
            f"• Physical GPU: {gpu_name}\n"
            f"• GPU Memory: {vram_str}\n"
            f"• GPU Temperature: {gpu_temp_str}\n"
            f"• Active AI Execution Runtime: {runtime}"
        )
    elif focus == "memory":
        reply = (
            f"Workstation Hardware Telemetry — Memory, sir:\n"
            f"• Memory: {ram_used} GB of {ram_total} GB used ({ram_usage}%)\n"
            f"• Available RAM: {avail_ram} GB\n"
            f"• RAM Usage: {ram_usage}%"
        )
    elif focus == "storage":
        io_info = f"\n• Disk I/O Activity: {disk_read} read, {disk_write} write" if disk_read != "unavailable" else ""
        reply = (
            f"Workstation Hardware Telemetry — Storage, sir:\n"
            f"• Storage: {disk_used} GB of {disk_total} GB used ({disk_usage}%)\n"
            f"• Free Storage: {free_disk} GB available on C: Drive{io_info}\n"
            f"• Utilization: {disk_usage}%"
        )
    elif focus == "temperature_cpu":
        note = " (hardware thermal sensors not exposed via standard operating system interfaces without third-party kernel drivers)" if cpu_temp_str == "unavailable" else ""
        reply = (
            f"Workstation Hardware Telemetry — CPU Temperature, sir:\n"
            f"• Processor: {cpu_brand}\n"
            f"• CPU Temperature: {cpu_temp_str}{note}"
        )
    elif focus == "temperature_gpu":
        reply = (
            f"Workstation Hardware Telemetry — GPU Temperature, sir:\n"
            f"• Physical GPU: {gpu_name}\n"
            f"• GPU Temperature: {gpu_temp_str}\n"
            f"• GPU Utilization: {gpu_usage}%"
        )
    elif focus == "temperature":
        reply = (
            f"Workstation Hardware Telemetry — Thermal Status, sir:\n"
            f"• CPU Temperature: {cpu_temp_str}\n"
            f"• GPU Temperature: {gpu_temp_str}"
        )
    elif focus == "host_hardware":
        reply = (
            f"Workstation Hardware Telemetry — Host System, sir:\n"
            f"• Device Environment: {device_type}\n"
            f"• Architecture: {arch}\n"
            f"• Processor: {cpu_brand} ({logical_cores} threads)\n"
            f"• Dedicated GPU: {gpu_name}\n"
            f"• Memory: {ram_used} GB of {ram_total} GB used ({ram_usage}%)\n"
            f"• Storage: {disk_used} GB of {disk_total} GB used ({free_disk} GB free)\n"
            f"• Snapdragon NPU Status: {npu_status}\n"
            f"• Active AI Execution Runtime: {runtime}"
        )
    elif focus == "npu":
        reply = (
            f"Workstation Hardware Telemetry — NPU Status, sir:\n"
            f"• Snapdragon NPU Status: {npu_status}\n"
            f"• Active AI Execution Runtime: {runtime}"
        )
    elif focus == "battery":
        reply = (
            f"Workstation Hardware Telemetry — Battery, sir:\n"
            f"• Battery: {battery_str}"
        )
    elif focus == "architecture":
        reply = (
            f"Workstation Hardware Telemetry — Architecture, sir:\n"
            f"• Architecture: {arch}\n"
            f"• Device Environment: {device_type}\n"
            f"• Active AI Execution Runtime: {runtime}"
        )
    else:
        # Full comprehensive Workstation Hardware Telemetry report
        sys_details = f"\n• System State: {uptime_str} uptime"
        if process_count != "unavailable":
            sys_details += f" ({process_count} processes"
            if active_threads != "unavailable":
                sys_details += f", {active_threads} active threads"
            sys_details += ")"
        reply = (
            f"Workstation Hardware Telemetry, sir:\n"
            f"• Device Environment: {device_type}\n"
            f"• Architecture: {arch}\n"
            f"• Processor: {cpu_brand} ({logical_cores} threads)\n"
            f"• CPU Usage: {cpu_usage}%\n"
            f"• CPU Temperature: {cpu_temp_str}\n"
            f"• Memory: {ram_used} GB of {ram_total} GB used ({ram_usage}%)\n"
            f"• Storage: {disk_used} GB of {disk_total} GB used ({free_disk} GB free)\n"
            f"• Physical GPU: {gpu_name}\n"
            f"• GPU Memory: {vram_str}\n"
            f"• GPU Temperature: {gpu_temp_str}\n"
            f"• Battery: {battery_str}{sys_details}\n"
            f"• Snapdragon NPU Status: {npu_status}\n"
            f"• Active AI Execution Runtime: {runtime}"
        )

    return reply, "hardware_telemetry"


