import os
import time
import requests
from typing import List, Dict

DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

def debug_log(msg: str):
    if DEBUG:
        print(f"[DEBUG LOG] {msg}")

def search_tavily(query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """
    Dedicated Official Tavily Search API Provider.
    Reads TAVILY_API_KEY from environment variables and returns a standardized result structure:
    [
        {
            "title": "...",
            "snippet": "...",
            "summary": "...",
            "url": "..."
        }
    ]
    """
    key_loaded = bool(TAVILY_API_KEY)
    key_snippet = f"{TAVILY_API_KEY[:15]}..." if key_loaded else "None"

    debug_log(f"[TAVILY DEBUG] API Key Loaded: {'Yes' if key_loaded else 'No'} ({key_snippet})")

    if not TAVILY_API_KEY:
        print("[TAVILY WARNING] Tavily API key is not configured. Returning empty search results.")
        return []

    headers = {
        "Authorization": f"Bearer {TAVILY_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False
    }

    try:
        start_t = time.time()
        res = requests.post(TAVILY_SEARCH_URL, headers=headers, json=payload, timeout=8.0)
        duration = round(time.time() - start_t, 3)

        print(f"[TAVILY DEBUG] HTTP Status Code: {res.status_code} | Query: '{query}'")

        if res.status_code == 200:
            data = res.json()
            raw_results = data.get("results", [])
            results = []
            for item in raw_results[:max_results]:
                content = item.get("content", item.get("snippet", ""))
                pub_date = item.get("published_date", item.get("pub_date", item.get("date", "")))
                results.append({
                    "title": item.get("title", "Tavily Web Result"),
                    "snippet": content,
                    "summary": content,
                    "url": item.get("url", ""),
                    "published_date": pub_date
                })
            print(f"[TAVILY DEBUG] Number of Search Results: {len(results)} (Duration: {duration}s)")
            return results
        else:
            print(f"[TAVILY ERROR] HTTP Status {res.status_code}: {res.text}")
            return []
    except Exception as e:
        print(f"[TAVILY EXCEPTION]: {e}")
        return []
