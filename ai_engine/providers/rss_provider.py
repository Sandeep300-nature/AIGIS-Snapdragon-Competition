import os
import urllib.parse
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict

DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def debug_log(msg: str):
    if DEBUG:
        print(f"[DEBUG LOG] {msg}")

def search_google_news_rss(query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """
    Google News RSS Fallback Search Provider.
    Returns standardized result structure:
    [
        {
            "title": "...",
            "snippet": "...",
            "summary": "...",
            "url": "..."
        }
    ]
    """
    headers = {"User-Agent": USER_AGENT}
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
        res = requests.get(url, headers=headers, timeout=4.0)
        if res.status_code != 200:
            return []
        root = ET.fromstring(res.text)
        results = []
        for item in root.findall(".//item")[:max_results]:
            title = item.find("title").text if item.find("title") is not None else ""
            link = item.find("link").text if item.find("link") is not None else ""
            pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
            snippet_text = f"Published: {pub_date}"
            results.append({
                "title": title,
                "snippet": snippet_text,
                "summary": snippet_text,
                "url": link,
                "published_date": pub_date
            })
        return results
    except Exception as e:
        debug_log(f"Google News RSS fallback error: {e}")
        return []
