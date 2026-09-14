"""
Provider clients + free-tier quota config.

Rotation priority: monthly-reset providers first (use it or lose it),
one-time credit pools (Serper) last as the buffer.

Verified free tiers (Sep 2026):
  Tavily      1,000 credits/month, resets monthly. NOT true Google positions.
  ScraperAPI  1,000 credits/month, resets monthly. Google = 25 credits -> 40 searches.
  SerpAPI     250 searches/month, resets monthly. (optional, recommended)
  Serper.dev  2,500 credits ONE-TIME. 1 credit per top-10 search.
"""

import os
from urllib.parse import urlparse

import requests

TARGET_DOMAIN = os.environ.get("TARGET_DOMAIN", "").lower().replace("www.", "")
GL = os.environ.get("GL", "us")


def _match(link: str) -> bool:
    domain = urlparse(link).netloc.lower().replace("www.", "")
    return domain == TARGET_DOMAIN or domain.endswith("." + TARGET_DOMAIN)


def _find_position(results: list, link_key: str = "link") -> tuple[int | None, str | None]:
    for i, r in enumerate(results[:10], start=1):
        if _match(r.get(link_key, "") or ""):
            return r.get("position", i), r.get(link_key)
    return None, None


# ---------- provider clients: return position 1-10 or None ----------

def search_brightdata(keyword: str) -> int | None:
    """Bright Data SERP API. 5,000 free credits/month, resets on the 1st.
    Requires a SERP API zone (default name: serp_api1) and an API key."""
    import urllib.parse
    zone = os.environ.get("BRIGHTDATA_ZONE", "serp_api1")
    q = urllib.parse.quote_plus(keyword)
    r = requests.post("https://api.brightdata.com/request",
                      headers={"Authorization": f"Bearer {os.environ['BRIGHTDATA_KEY']}",
                               "Content-Type": "application/json"},
                      json={"zone": zone,
                            "url": f"https://www.google.com/search?q={q}&num=10&gl={GL}&brd_json=1",
                            "format": "raw"},
                      timeout=60)
    r.raise_for_status()
    return _find_position(r.json().get("organic", []))



def search_serpapi(keyword: str) -> int | None:
    r = requests.get("https://serpapi.com/search", params={
        "engine": "google", "q": keyword, "num": 10, "gl": GL,
        "api_key": os.environ["SERPAPI_KEY"],
    }, timeout=30)
    r.raise_for_status()
    return _find_position(r.json().get("organic_results", []))


def search_serper(keyword: str) -> int | None:
    r = requests.post("https://google.serper.dev/search",
                      headers={"X-API-KEY": os.environ["SERPER_API_KEY"],
                               "Content-Type": "application/json"},
                      json={"q": keyword, "num": 10, "gl": GL}, timeout=30)
    r.raise_for_status()
    return _find_position(r.json().get("organic", []))


def search_scraperapi(keyword: str) -> int | None:
    r = requests.get("https://api.scraperapi.com/structured/google/search", params={
        "api_key": os.environ["SCRAPERAPI_KEY"], "query": keyword, "num": 10,
        "country_code": GL,
    }, timeout=60)
    r.raise_for_status()
    return _find_position(r.json().get("organic_results", []))


def search_tavily(keyword: str) -> int | None:
    """WARNING: Tavily ranks by its own relevance, not Google position.
    Results from this provider are approximate."""
    r = requests.post("https://api.tavily.com/search",
                      headers={"Authorization": f"Bearer {os.environ['TAVILY_KEY']}",
                               "Content-Type": "application/json"},
                      json={"query": keyword, "max_results": 10}, timeout=30)
    r.raise_for_status()
    return _find_position(r.json().get("results", []), link_key="url")


# ---------- rotation config ----------
# quota = free Google searches per period. reset: "monthly" or "one_time".
# approximate=True marks results with ~ in the sheet.
# Order = priority. Monthly-reset first, one-time pool last.

PROVIDERS = [
    {"name": "brightdata", "env": "BRIGHTDATA_KEY", "fn": search_brightdata,
     "quota": 4800, "reset": "monthly",  "approximate": False},  # 5,000 real, 200 safety margin
    {"name": "serpapi",    "env": "SERPER_API_KEY",    "fn": search_serpapi,
     "quota": 250,  "reset": "monthly",  "approximate": False},
    {"name": "scraperapi", "env": "SCRAPERAPI_KEY", "fn": search_scraperapi,
     "quota": 40,   "reset": "monthly",  "approximate": False},
    {"name": "tavily",     "env": "TAVILY_KEY",     "fn": search_tavily,
     "quota": 1000, "reset": "monthly",  "approximate": True},
    {"name": "serper",     "env": "SERPER_KEY",     "fn": search_serper,
     "quota": 2500, "reset": "one_time", "approximate": False},
]
