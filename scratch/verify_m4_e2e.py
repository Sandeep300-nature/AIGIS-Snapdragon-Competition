import urllib.request
import json
import time
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://localhost:8080/api/v1/chat"

test_prompts = [
    ("What time is it?", "system"),
    ("open notepad", "action"),
    ("Can you open YouTube, AIGIS?", "action"),
    ("Who is the latest IPL winner?", "live-web"),
    ("Explain quantum computing in one sentence.", "local")
]

def simulate_provenance_badge(data):
    provider = data.get("provider", "")
    metadata = data.get("metadata") or {}
    intent = metadata.get("intent", "")
    engine = data.get("engine", "")
    web_search = data.get("webSearchUsed", False)

    # 1. Genuine local SLM
    if metadata.get("localInference") or metadata.get("model") == "SmolLM2-135M-Instruct" or "SmolLM2" in provider:
        tok_sec = f" · {metadata.get('tokensPerSec')} tok/s" if metadata.get('tokensPerSec') else ""
        return {
            "label": f"⚡ Local SLM (SmolLM2-135M{tok_sec})",
            "type": "local",
            "title": f"Model: SmolLM2-135M-Instruct | Device: {metadata.get('device', 'CPU')} | Runtime: {metadata.get('runtime', 'PyTorch')}"
        }

    # 2. Desktop/Web Action
    if intent in ["desktop_action", "web_action"] or "Desktop Control" in provider or "Desktop Action" in provider:
        return {
            "label": "🖥️ Desktop Action (Executed)",
            "type": "action",
            "title": "Deterministic desktop or browser navigation executed on-device"
        }

    # 3. System clock / telemetry
    if intent in ["time", "hardware", "privacy"] or "Local On-Device" in provider:
        return {
            "label": "⚙️ System Telemetry (Local Clock)",
            "type": "system",
            "title": "Deterministic local system clock and hardware telemetry"
        }

    # 4. Live Web Search
    if web_search or intent == "live_web" or "Live Search" in provider:
        return {
            "label": "🌐 Live Web (Tavily/RSS Facts)",
            "type": "live-web",
            "title": "Real-time facts fetched from the internet via verified live search"
        }

    # 5. Cloud AI
    if engine == "cloud" or "Groq" in provider:
        return {
            "label": "☁️ Cloud AI (Groq)",
            "type": "cloud",
            "title": "Cloud language model synthesis"
        }

    # 6. Generic Local
    if engine == "local":
        return {
            "label": "⚡ AIGIS Local (On-Device)",
            "type": "local",
            "title": "Local on-device execution"
        }

    return {"label": provider or "AIGIS AI", "type": "default", "title": provider}

print("=" * 70)
print("AIGIS MILESTONE 4 — VERIFIED FRONTEND / SPRING BOOT PROVENANCE AUDIT")
print("=" * 70)

results = []
for prompt, expected_type in test_prompts:
    print(f"\n[TESTING PROMPT]: '{prompt}'")
    payload = json.dumps({
        "prompt": prompt,
        "sessionId": f"m4-test-{int(time.time())}",
        "responseLanguage": "en"
    }).encode("utf-8")
    
    start_t = time.perf_counter()
    req = urllib.request.Request(BASE_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed_ms = int((time.perf_counter() - start_t) * 1000)
            
            badge = simulate_provenance_badge(data)
            print(f"  -> HTTP Status   : {resp.status}")
            print(f"  -> Engine        : {data.get('engine')}")
            print(f"  -> Provider      : {data.get('provider')}")
            print(f"  -> Web Search    : {data.get('webSearchUsed')}")
            print(f"  -> Provenance UI : {badge['label']} (type: {badge['type']})")
            print(f"  -> Metadata Info : {badge['title']}")
            print(f"  -> Latency       : backend={data.get('latencyMs')}ms, roundtrip={elapsed_ms}ms")
            print(f"  -> Reply Snippet : {data.get('reply', '')[:120].strip()}...")
            if data.get("urlToOpen"):
                print(f"  -> URL to Open   : {data.get('urlToOpen')}")
            
            match = badge["type"] == expected_type
            results.append({
                "prompt": prompt,
                "expected": expected_type,
                "actual": badge["type"],
                "badge": badge["label"],
                "pass": match
            })
            print(f"  -> PASS?         : {'✅ YES' if match else '❌ NO'}")
    except Exception as e:
        print(f"  -> ERROR         : {e}")
        results.append({
            "prompt": prompt,
            "expected": expected_type,
            "actual": "ERROR",
            "badge": str(e),
            "pass": False
        })

print("\n" + "=" * 70)
print("FINAL AUDIT SUMMARY")
print("=" * 70)
all_pass = True
for r in results:
    status = "✅ PASS" if r["pass"] else "❌ FAIL"
    print(f"{status} | Prompt: '{r['prompt']}' | Badge: '{r['badge']}'")
    if not r["pass"]:
        all_pass = False

print(f"\nOVERALL RESULT: {'ALL PROMPTS PASSED PROVENANCE AUDIT' if all_pass else 'FAILURES DETECTED'}")
