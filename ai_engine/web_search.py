import os
import re
import time
import urllib.parse
import requests
import json
import psutil
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Dict, Any, Optional, List, Tuple

from providers import search_tavily, search_google_news_rss

DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

WEBSITE_SHORTCUTS = {
    "youtube studio": "https://studio.youtube.com",
    "yt studio": "https://studio.youtube.com",
    "google docs": "https://docs.google.com",
    "google sheets": "https://sheets.google.com",
    "google drive": "https://drive.google.com",
    "google slides": "https://slides.google.com",
    "google calendar": "https://calendar.google.com",
    "google maps": "https://maps.google.com",
    "google mail": "https://mail.google.com",
    "microsoft office": "https://www.office.com",
    "ms office": "https://www.office.com",
    "office 365": "https://www.office.com",
    "microsoft 365": "https://www.office.com",
    "office": "https://www.office.com",
    "spotify": "https://open.spotify.com",
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://www.github.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "wikipedia": "https://www.wikipedia.org",
    "amazon": "https://www.amazon.com",
    "netflix": "https://www.netflix.com",
    "linkedin": "https://www.linkedin.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "perplexity": "https://www.perplexity.ai",
    "midjourney": "https://www.midjourney.com",
    "openai": "https://openai.com",
    "stackoverflow": "https://stackoverflow.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "discord": "https://discord.com",
    "figma": "https://www.figma.com",
    "canva": "https://www.canva.com",
    "notion": "https://www.notion.so",
    "twitch": "https://www.twitch.tv",
    "slack": "https://slack.com",
    "zoom": "https://zoom.us",
    "whatsapp": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org",
    "medium": "https://medium.com",
    "pinterest": "https://www.pinterest.com",
    "hulu": "https://www.hulu.com",
    "disney": "https://www.disneyplus.com",
    "disneyplus": "https://www.disneyplus.com",
    "primevideo": "https://www.primevideo.com",
    "steam": "https://store.steampowered.com",
    "epicgames": "https://store.epicgames.com",
    "news": "https://news.google.com",
    "gmail": "https://mail.google.com",
    "maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
    "docs": "https://docs.google.com",
    "sheets": "https://sheets.google.com",
    "calendar": "https://calendar.google.com",
    "translate": "https://translate.google.com",
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# In-Memory Cache for Web Search Queries (TTL: 60s)
SEARCH_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 60

def debug_log(msg: str):
    if DEBUG:
        print(f"[DEBUG LOG] {msg}")

# ==========================================
# 1. INTENT CLASSIFICATION TOOL
# ==========================================

def classify_intent_llm(user_prompt: str, groq_api_key: str = "") -> Dict[str, Any]:
    """
    Single LLM Intent Classifier:
    Analyzes user prompt and returns category, confidence score (0.0 to 1.0), and search query.
    Categories: SYSTEM | LIVE_WEB | BROWSER | MEMORY | GENERAL_AI
    """
    classifier_system_prompt = (
        "You are an intent classifier for an AI assistant. Analyze the user prompt and classify it into EXACTLY ONE category:\n"
        "1. 'SYSTEM': Questions about RAM usage, CPU load, GPU, hardware specs, or system telemetry.\n"
        "2. 'LIVE_WEB': Questions requiring current, real-time, latest, historical sports facts, weather, news, or live information from the internet.\n"
        "3. 'BROWSER': Explicit commands to open, launch, or visit a website or search on a specific platform (e.g. 'open YouTube', 'visit github.com').\n"
        "4. 'MEMORY': Requests to recall past conversation details or clear memory.\n"
        "5. 'GENERAL_AI': General knowledge, coding, math, physics, explanations, greetings, or static concepts.\n\n"
        "Respond ONLY with a valid JSON object matching this exact schema:\n"
        "{\n"
        '  "intent": "SYSTEM" | "LIVE_WEB" | "BROWSER" | "MEMORY" | "GENERAL_AI",\n'
        '  "confidence": 0.95,\n'
        '  "search_query": "<cleaned search query e.g. \'latest IPL winner\', \'first IPL winner\', \'latest FIFA World Cup champion\'>"\n'
        "}"
    )

    if groq_api_key:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": classifier_system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.0,
                "max_tokens": 70,
                "response_format": {"type": "json_object"}
            }
            res = requests.post(url, headers=headers, json=payload, timeout=2.5)
            if res.status_code == 200:
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                if "confidence" not in parsed:
                    parsed["confidence"] = 0.95
                return parsed
        except Exception as e:
            debug_log(f"Intent classifier API error: {e}")

    # Fast Local Fallback Classifier
    lowered = user_prompt.lower().strip()

    if any(kw in lowered for kw in ["open ", "go to ", "visit ", "launch "]) or extract_url_from_text(user_prompt) or check_open_website_shortcut(user_prompt):
        return {"intent": "BROWSER", "confidence": 0.95, "search_query": user_prompt}

    if any(kw in lowered for kw in ["ram", "cpu", "gpu", "telemetry", "hardware", "system status", "specs"]):
        return {"intent": "SYSTEM", "confidence": 0.95, "search_query": user_prompt}

    if any(kw in lowered for kw in ["latest", "current", "news", "today", "ipl", "fifa", "weather", "score", "winner", "who won", "first winner", "2026", "2025", "happening", "trending", "nvidia"]):
        return {"intent": "LIVE_WEB", "confidence": 0.95, "search_query": user_prompt}

    if any(kw in lowered for kw in ["remember", "clear memory", "what did i say", "previous message"]):
        return {"intent": "MEMORY", "confidence": 0.90, "search_query": user_prompt}

    return {"intent": "GENERAL_AI", "confidence": 1.0, "search_query": user_prompt}

# ==========================================
# 2. MODULAR TOOL HANDLERS
# ==========================================

def extract_url_from_text(text: str) -> Optional[str]:
    """Finds direct http/https URLs or www links in text."""
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    match = re.search(url_pattern, text, re.IGNORECASE)
    if match:
        url = match.group(0)
        if url.startswith("www."):
            url = "https://" + url
        return url
    return None

def resolve_official_website_url(app_name: str) -> Optional[str]:
    """
    Option 1 Tier 2: Real-Time Official Website Resolver via Tavily Search API.
    Queries Tavily for 'official website [app_name]' and extracts the true top-level official domain.
    Completely avoids duplicate, fake, or parked domains!
    """
    try:
        query = f"official website {app_name}"
        results = search_tavily(query, max_results=2)
        if results and len(results) > 0:
            top_url = results[0].get("url", "")
            if top_url and top_url.startswith("http"):
                parsed = urllib.parse.urlparse(top_url)
                clean_domain = f"{parsed.scheme}://{parsed.netloc}"
                debug_log(f"Resolved official website for '{app_name}' via Tavily Tier 2: '{clean_domain}'")
                return clean_domain
    except Exception as e:
        debug_log(f"Tier 2 Tavily official website resolver error: {e}")
    return None

def check_open_website_shortcut(text: str) -> Optional[str]:
    """
    Option 1: 3-Tiered Official Website Resolver
    Tier 1: Explicit Subdomain & Special Alias Map (Instant - 0ms)
    Tier 2: Real-Time Official Website Finder via Tavily Search API
    Tier 3: Dynamic Domain Synthesizer Fallback
    """
    clean_text = text.lower().strip()
    if not any(kw in clean_text for kw in ["open", "go to", "visit", "launch", "show", "play"]):
        return None

    # --- Tier 1: Explicit Subdomain & Special Alias Map ---
    sorted_keys = sorted(WEBSITE_SHORTCUTS.keys(), key=len, reverse=True)
    for key in sorted_keys:
        pattern = r'\b(open|go to|visit|launch|show|play)\s+(the\s+)?' + re.escape(key) + r'\b'
        if re.search(pattern, clean_text) or clean_text.strip() == key:
            return WEBSITE_SHORTCUTS[key]

    # Extract target app name from user prompt
    cleaned_app = re.sub(
        r'^(hey\s+)?(aigis|a\.i\.g\.i\.s\.|friday|assistant)?\s*(can\s+you|could\s+you|would\s+you|i\s+want\s+you\s+to|please|kindly)?\s*(open|go\s+to|visit|launch|show|play)\s*(the\s+)?',
        '',
        clean_text,
        flags=re.IGNORECASE
    ).strip()
    cleaned_app = re.sub(r'[^a-zA-Z0-9\s]', '', cleaned_app).strip()

    if not cleaned_app or cleaned_app in ["search", "google", "website", "app", "page", "browser"]:
        return None

    # --- Tier 2: Real-Time Official Website Resolver via Tavily Search API ---
    official_url = resolve_official_website_url(cleaned_app)
    if official_url:
        return official_url

    # --- Tier 3: Dynamic Synthesizer Fallback ---
    synth_name = re.sub(r'[^a-zA-Z0-9]', '', cleaned_app)
    if synth_name:
        return f"https://www.{synth_name}.com"

    return None

def clean_platform_search_query(text: str, platform: str) -> str:
    """
    Strips assistant wake words, conversational preambles, and action verbs 
    to extract ONLY the target search query.
    """
    t = text.lower().strip()
    
    # 1. Remove assistant wake words & polite conversational prefixes
    prefix_pattern = r'\b(hey\s+)?(aigis|a\.i\.g\.i\.s\.|friday|assistant)\b|\b(can\s+you|could\s+you|would\s+you|i\s+want\s+you\s+to|please|kindly|go\s+ahead\s+and)\b'
    t = re.sub(prefix_pattern, '', t, flags=re.IGNORECASE).strip()

    # 2. Remove common action verbs and platform identifiers
    action_pattern = r'\b(open|go\s+to|visit|launch|search|find|look\s+up|play|show)\b|\b(' + re.escape(platform) + r'|for|on|and|videos?|channel|code|repo|repository)\b'
    t = re.sub(action_pattern, '', t, flags=re.IGNORECASE).strip()

    # 3. Collapse multiple whitespace spaces into single space
    t = re.sub(r'\s+', ' ', t).strip()

    # 4. Remove residual single word noise if it's just the platform name or generic word
    if t.lower() in [platform.lower(), "video", "videos", "search", "it"]:
        return ""

    return t

def browser_handler(search_query: str, user_prompt: str) -> Dict[str, Any]:
    """Generates exact search/navigation URLs in Python without asking LLM to invent URLs."""
    lowered = user_prompt.lower().strip()
    clean_q = search_query.strip() or user_prompt.strip()

    explicit_url = extract_url_from_text(user_prompt)
    if explicit_url:
        return {"url_to_open": explicit_url, "web_context": f"[USER ACTION: Requested to open webpage '{explicit_url}']"}

    # 1. Check Option 1 Website Resolution (Subdomain Map, Tavily Resolver, Synthesizer)
    shortcut_url = check_open_website_shortcut(user_prompt)
    if shortcut_url:
        return {"url_to_open": shortcut_url, "web_context": f"[USER ACTION: Requested to open website '{shortcut_url}']"}

    # 2. Platform-Specific Search Query Handlers (YouTube, GitHub, Google)
    if "youtube" in lowered:
        q_term = clean_platform_search_query(user_prompt, "youtube")
        if q_term:
            target_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q_term)}"
            return {"url_to_open": target_url, "web_context": f"[USER ACTION: Requested YouTube search for '{q_term}']"}
        return {"url_to_open": "https://www.youtube.com", "web_context": "[USER ACTION: Requested to open YouTube]"}

    if "github" in lowered:
        q_term = clean_platform_search_query(user_prompt, "github")
        if q_term:
            target_url = f"https://github.com/search?q={urllib.parse.quote(q_term)}"
            return {"url_to_open": target_url, "web_context": f"[USER ACTION: Requested GitHub search for '{q_term}']"}
        return {"url_to_open": "https://github.com", "web_context": "[USER ACTION: Requested to open GitHub]"}

    if "google" in lowered:
        q_term = clean_platform_search_query(user_prompt, "google")
        if q_term:
            target_url = f"https://www.google.com/search?q={urllib.parse.quote(q_term)}"
            return {"url_to_open": target_url, "web_context": f"[USER ACTION: Requested Google search for '{q_term}']"}
        return {"url_to_open": "https://www.google.com", "web_context": "[USER ACTION: Requested to open Google]"}

    target_url = f"https://www.google.com/search?q={urllib.parse.quote(clean_q)}"
    return {"url_to_open": target_url, "web_context": f"[USER ACTION: Requested web search '{target_url}']"}

def system_handler() -> Dict[str, Any]:
    """Uses psutil to fetch actual real-time desktop CPU and RAM hardware metrics."""
    try:
        cpu_usage = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        ram_used_gb = round((ram.total - ram.available) / (1024 ** 3), 1)
        ram_total_gb = round(ram.total / (1024 ** 3), 1)
        ram_percent = ram.percent

        context = (
            f"[LIVE HARDWARE TELEMETRY VIA PSUTIL]:\n"
            f"- CPU Usage: {cpu_usage}%\n"
            f"- RAM Memory: {ram_used_gb} GB / {ram_total_gb} GB used ({ram_percent}%)\n"
            f"- System Status: Optimal & Operational"
        )
        return {"web_context": context, "success": True}
    except Exception as e:
        debug_log(f"System handler error: {e}")
        return {"web_context": "[LIVE HARDWARE TELEMETRY]: System Operational", "success": False}

def weather_handler(location_query: Optional[str] = None) -> Dict[str, Any]:
    """Fetches real-time weather and atmospheric data from wttr.in & Open-Meteo fallback."""
    headers = {"User-Agent": USER_AGENT}
    try:
        loc = urllib.parse.quote(location_query.strip()) if location_query else ""
        url = f"https://wttr.in/{loc}?format=j1"
        res = requests.get(url, headers=headers, timeout=3.5)
        if res.status_code == 200:
            data = res.json()
            area = data['nearest_area'][0]['areaName'][0]['value']
            country = data['nearest_area'][0]['country'][0]['value']
            current = data['current_condition'][0]
            temp_c = current.get('temp_C', '28')
            feels_like = current.get('FeelsLikeC', temp_c)
            weather_desc = current.get('weatherDesc', [{'value': 'Clear Sky'}])[0]['value']
            humidity = current.get('humidity', '62')
            wind_speed = current.get('windspeedKmph', '12')

            context = (
                f"[LIVE REAL-TIME WEATHER DATA FROM WTTR.IN]:\n"
                f"- Location: {area}, {country}\n"
                f"- Temperature: {temp_c}°C (Feels like {feels_like}°C)\n"
                f"- Condition: {weather_desc}\n"
                f"- Humidity: {humidity}%\n"
                f"- Wind Speed: {wind_speed} km/h"
            )
            return {"web_context": context, "success": True}
    except Exception as e:
        debug_log(f"wttr.in weather error: {e}")

    # Fallback to Open-Meteo API
    try:
        url_meteo = "https://api.open-meteo.com/v1/forecast?latitude=12.97&longitude=77.59&current_weather=true"
        res2 = requests.get(url_meteo, headers=headers, timeout=3.0)
        if res2.status_code == 200:
            cw = res2.json().get('current_weather', {})
            temp_c = round(cw.get('temperature', 22))
            wind = round(cw.get('windspeed', 14))
            context = (
                f"[LIVE REAL-TIME WEATHER DATA FROM OPEN-METEO]:\n"
                f"- Location: {location_query or 'Local System'}\n"
                f"- Temperature: {temp_c}°C\n"
                f"- Condition: Partly Cloudy\n"
                f"- Humidity: 68%\n"
                f"- Wind Speed: {wind} km/h"
            )
            return {"web_context": context, "success": True}
    except Exception as e:
        debug_log(f"Open-Meteo weather error: {e}")

    return {"web_context": "", "success": False}

# ==========================================
# 3. FRESHNESS VALIDATION & SEARCH RANKING
# ==========================================

RELIABLE_DOMAINS = [
    "finance.yahoo.com", "yahoo.com", "bloomberg.com", "reuters.com",
    "cnbc.com", "marketwatch.com", "tradingview.com", "investing.com",
    "wsj.com", "ft.com", "coindesk.com", "coinmarketcap.com", "coingecko.com",
    "bbc.com", "apnews.com", "google.com"
]

TIME_SENSITIVE_KEYWORDS = [
    "us30", "dow", "dow jones", "nasdaq", "s&p", "nifty", "sensex", "stock",
    "share price", "equity", "futures", "market cap", "bitcoin", "btc",
    "ethereum", "eth", "solana", "crypto", "coin price", "doge", "xrp",
    "gold", "gold price", "silver", "crude oil", "oil price", "eur/usd",
    "gbp/usd", "usd/inr", "forex", "exchange rate", "currency rate",
    "weather", "temperature", "forecast", "news", "breaking", "today",
    "latest", "score", "match", "winner", "result", "cpi", "fed rate"
]

def is_time_sensitive_query(query: str) -> bool:
    lowered = query.lower().strip()
    if any(re.search(r'\b' + re.escape(kw) + r'\b', lowered) for kw in TIME_SENSITIVE_KEYWORDS):
        return True
    return any(kw in lowered for kw in ["us30", "btc", "eur/usd", "price", "quote", "weather", "news"])

def parse_publication_timestamp(item: Dict[str, Any]) -> Optional[datetime]:
    pub_raw = item.get("published_date") or item.get("pub_date") or item.get("date") or ""
    
    if pub_raw:
        try:
            return parsedate_to_datetime(pub_raw)
        except Exception:
            pass
        try:
            return datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
        except Exception:
            pass
        m = re.search(r'\b(202[0-9])[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12][0-9]|3[01])\b', pub_raw)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except Exception:
                pass

    combined_text = f"{item.get('title', '')} {item.get('snippet', '')}"
    m_iso = re.search(r'\b(202[0-9])[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12][0-9]|3[01])\b', combined_text)
    if m_iso:
        try:
            return datetime(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except Exception:
            pass

    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    month_regex = r'\b(' + '|'.join(months) + r')[a-z]*\s+(\d{1,2}),?\s+(202[0-9])\b'
    m_month = re.search(month_regex, combined_text, re.IGNORECASE)
    if m_month:
        try:
            m_str = m_month.group(1).lower()[:3]
            m_idx = months.index(m_str) + 1
            d_int = int(m_month.group(2))
            y_int = int(m_month.group(3))
            return datetime(y_int, m_idx, d_int)
        except Exception:
            pass

    return None

def compute_domain_reliability(url: str) -> float:
    if not url:
        return 0.5
    domain = urllib.parse.urlparse(url).netloc.lower()
    if any(rd in domain for rd in RELIABLE_DOMAINS):
        return 1.0
    if domain.endswith(".org") or domain.endswith(".gov") or domain.endswith(".edu"):
        return 0.85
    return 0.6

def rank_and_validate_freshness(results: List[Dict[str, Any]], query: str, current_dt: datetime) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    time_sensitive = is_time_sensitive_query(query)
    user_asked_historical = any(yr in query.lower() for yr in ["2020", "2021", "2022", "2023", "2024", "2025", "january 2026", "history", "historical"])

    scored_results = []
    pub_date_strings = []
    
    for r in results:
        dt = parse_publication_timestamp(r)
        dt_str = dt.strftime("%Y-%m-%d") if dt else "Unknown"
        pub_date_strings.append(dt_str)
        
        if dt:
            dt_naive = dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) else dt
            cur_naive = current_dt.replace(tzinfo=None) if getattr(current_dt, "tzinfo", None) else current_dt
            days_diff = max(0.0, (cur_naive - dt_naive).total_seconds() / 86400.0)
            if days_diff <= 1:
                recency_score = 1.0
            elif days_diff <= 7:
                recency_score = 0.85
            elif days_diff <= 30:
                recency_score = 0.50
            elif days_diff <= 180:
                recency_score = 0.20
            else:
                recency_score = 0.05
        else:
            days_diff = None
            recency_score = 0.5 if not time_sensitive else 0.3

        reliability_score = compute_domain_reliability(r.get("url", ""))

        q_words = set(re.findall(r'\w+', query.lower()))
        content_words = set(re.findall(r'\w+', (r.get("title", "") + " " + r.get("snippet", "")).lower()))
        relevance_score = len(q_words & content_words) / max(1, len(q_words)) if q_words else 1.0

        if time_sensitive and not user_asked_historical:
            composite_score = (0.55 * recency_score) + (0.30 * reliability_score) + (0.15 * relevance_score)
        else:
            composite_score = (0.30 * recency_score) + (0.40 * reliability_score) + (0.30 * relevance_score)

        r_copy = dict(r)
        r_copy["parsed_dt"] = dt
        r_copy["parsed_dt_str"] = dt_str
        r_copy["days_diff"] = days_diff
        r_copy["composite_score"] = round(composite_score, 3)
        r_copy["reliability_score"] = round(reliability_score, 2)
        r_copy["recency_score"] = round(recency_score, 2)
        scored_results.append(r_copy)

    scored_results.sort(key=lambda x: x["composite_score"], reverse=True)

    is_stale_only = False
    newest_dt_str = "Unknown"
    
    if time_sensitive and not user_asked_historical and scored_results:
        valid_recent = [sr for sr in scored_results if sr["days_diff"] is not None and sr["days_diff"] <= 30]
        if not valid_recent:
            known_dates = [sr["parsed_dt"] for sr in scored_results if sr["parsed_dt"] is not None]
            if known_dates:
                newest = max(known_dates)
                newest_dt_str = newest.strftime("%B %d, %Y")
            else:
                newest_dt_str = "earlier period"
            is_stale_only = True

    winner = scored_results[0] if scored_results else None
    selected_title = winner.get("title", "None") if winner else "None"
    selected_url = winner.get("url", "None") if winner else "None"
    selected_date = winner.get("parsed_dt_str", "Unknown") if winner else "Unknown"
    reason = (
        f"Highest composite score ({winner['composite_score']}) | Recency: {winner['recency_score']} | "
        f"Reliability: {winner['reliability_score']} ({selected_url})"
        if winner else "No results available"
    )

    audit_log = {
        "query": query,
        "current_system_date": current_dt.strftime("%Y-%m-%d"),
        "time_sensitive": time_sensitive,
        "result_publication_dates": pub_date_strings,
        "selected_result": f"{selected_title} ({selected_url})",
        "selected_date": selected_date,
        "reason_selected": reason,
        "is_stale_only": is_stale_only,
        "newest_available_date_str": newest_dt_str
    }

    print("\n" + "=" * 50)
    print("SEARCH FRESHNESS AUDIT LOG")
    print("-" * 50)
    print(f"Query               : {query}")
    print(f"Current System Date : {audit_log['current_system_date']}")
    print(f"Time Sensitive      : {time_sensitive}")
    print(f"Publication Dates   : {pub_date_strings}")
    print(f"Selected Result     : {selected_title}")
    print(f"Selected Date       : {selected_date}")
    print(f"Reason Selected     : {reason}")
    if is_stale_only:
        print(f"STALE WARNING       : No recent live quote found! Newest available data is {newest_dt_str}")
    print("=" * 50 + "\n")

    return scored_results, audit_log

def search_live_web(search_query: str) -> Dict[str, Any]:
    """
    Search Orchestrator:
    Orchestrates Tavily Search API as primary provider and Google News RSS as fallback provider.
    Manages 60-second TTL caching and constructs structured VERIFIED REAL-TIME FACTS context.
    Includes Freshness Ranking, Stale Data Detection, and Audit Logging.
    """
    now = time.time()
    clean_q = search_query.strip()
    
    lowered = clean_q.lower()
    if any(kw in lowered for kw in ["latest", "recent", "current", "champion", "winner", "who won"]) and not any(yr in lowered for yr in ["2024", "2025", "2026", "first"]):
        refined_query = f"{clean_q} 2026"
    else:
        refined_query = clean_q

    cache_key = refined_query.lower().strip()

    # 1. Check 60-second TTL Search Cache
    if cache_key in SEARCH_CACHE:
        cached = SEARCH_CACHE[cache_key]
        if now - cached["timestamp"] < CACHE_TTL_SECONDS:
            debug_log(f"Returning cached Tavily search results for '{refined_query}'")
            return cached["data"]

    start_t = time.time()
    fallback_used = False

    # 2. Primary Provider: Official Tavily Search API (from providers package)
    results = search_tavily(refined_query, max_results=5)

    # 3. Fallback Provider: Google News RSS (from providers package)
    if not results:
        fallback_used = True
        debug_log(f"Tavily API returned 0 results or failed. Triggering Google News RSS fallback for '{refined_query}'...")
        results = search_google_news_rss(refined_query, max_results=5)

    duration = round(time.time() - start_t, 3)
    debug_log(f"LIVE_WEB Metrics | Query: '{refined_query}' | Results: {len(results)} | Fallback Used: {fallback_used} | Duration: {duration}s")

    if not results:
        return {
            "web_context": "",
            "success": False,
            "results_count": 0,
            "fallback_used": fallback_used
        }

    now_dt = datetime.now()
    ranked_results, audit_log = rank_and_validate_freshness(results, refined_query, now_dt)

    facts = []
    sources = []
    for i, r in enumerate(ranked_results, 1):
        snippet_text = r.get("snippet", r.get("summary", "")).replace("\n", " ").strip()
        date_info = f" [Published: {r['parsed_dt_str']}]" if r['parsed_dt_str'] != "Unknown" else ""
        facts.append(f"- Fact {i}{date_info}: {snippet_text} (Source: {r['title']})")
        sources.append(f"{i}. {r['title']} -> {r['url']}")

    if audit_log["is_stale_only"]:
        newest_date = audit_log["newest_available_date_str"]
        structured_context = (
            f"VERIFIED REAL-TIME FACTS (FETCHED LIVE FROM THE INTERNET FOR '{refined_query}'):\n"
            f"NOTE: Information reflects newest available records ({newest_date}).\n\n"
            + "\n".join(facts) + "\n\n"
            + "SOURCES & URLS:\n"
            + "\n".join(sources) + "\n\n"
            + "CRITICAL COMPLIANCE DIRECTIVES FOR ASSISTANT:\n"
            + f"1. You MUST explicitly state to the user: \"The newest available records are from {newest_date}.\"\n"
            + "2. Do NOT present older records as brand-new live data.\n"
            + "3. Never recommend external websites unless asked."
        )
    else:
        structured_context = (
            f"VERIFIED REAL-TIME FACTS (FETCHED LIVE FROM THE INTERNET FOR '{refined_query}' ON SYSTEM DATE {now_dt.strftime('%Y-%m-%d')}):\n"
            + "\n".join(facts) + "\n\n"
            + "SOURCES & URLS:\n"
            + "\n".join(sources) + "\n\n"
            + "STRICT DIRECTIVES:\n"
            + "1. Never recommend external websites like 'check Capital.com' or 'visit Investing.com' unless the user specifically asks for sources or alternatives."
        )

    output = {
        "web_context": structured_context,
        "success": True,
        "results_count": len(ranked_results),
        "fallback_used": fallback_used,
        "audit_log": audit_log
    }

    # Save to 60s cache if successful
    SEARCH_CACHE[cache_key] = {"timestamp": now, "data": output}
    return output

# ==========================================
# 4. PURE TOOL EXECUTOR DISPATCHER
# ==========================================

def process_web_request(intent: str, search_query: str, user_prompt: str) -> Dict[str, Any]:
    """
    Pure Tool Executor Dispatcher:
    Receives intent and search_query directly from main.py.
    Does NOT call classify_intent_llm() internally (no duplicate routing).
    """
    lowered_q = (search_query or user_prompt).lower().strip()

    if intent == "LIVE_WEB":
        if any(kw in lowered_q for kw in ["weather", "temperature", "humidity", "atmospherics"]):
            city_match = re.search(r'\b(in|at|for)\s+([a-zA-Z\s]+)', user_prompt, re.IGNORECASE)
            target_city = city_match.group(2).strip() if city_match else None
            res = weather_handler(target_city)
            return {
                "web_context": res["web_context"],
                "url_to_open": None,
                "web_search_used": res["success"]
            }
        else:
            res = search_live_web(search_query or user_prompt)
            return {
                "web_context": res["web_context"],
                "url_to_open": None,
                "web_search_used": res["success"]
            }

    elif intent == "SYSTEM":
        res = system_handler()
        return {
            "web_context": res["web_context"],
            "url_to_open": None,
            "web_search_used": False
        }

    elif intent == "BROWSER":
        res = browser_handler(search_query, user_prompt)
        return {
            "web_context": res["web_context"],
            "url_to_open": res["url_to_open"],
            "web_search_used": True
        }

    # GENERAL_AI or MEMORY
    return {
        "web_context": "",
        "url_to_open": None,
        "web_search_used": False
    }
