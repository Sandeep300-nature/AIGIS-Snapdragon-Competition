"""
AIGIS Search Providers Package
Exposes modular search provider implementations for Tavily API, Google News RSS, and future providers.
"""

from .tavily_provider import search_tavily
from .rss_provider import search_google_news_rss
from .provider_router import ProviderRouter

__all__ = ["search_tavily", "search_google_news_rss", "ProviderRouter"]

