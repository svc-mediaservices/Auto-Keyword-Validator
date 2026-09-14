"""
LLM visibility clients (ChatGPT + Gemini): ask each AI the keyword as a
real user would, with web search/grounding on, and detect whether
TARGET_DOMAIN appears.

Each client returns (citation_position | None, cited_url | None, mentioned: bool)
  citation_position = 1-based order of your domain among cited sources
  mentioned = brand appears in the answer text without a citation
"""

import json
import os
import re
from urllib.parse import urlparse

import requests

TARGET_DOMAIN = (os.environ.get("TARGET_DOMAIN", "").lower().strip()
                 .replace("https://", "").replace("http://", "")
                 .replace("www.", "").rstrip("/"))

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

URL_RE = re.compile(r'https?://[^\s"\'<>\\)\]]+')


def _domain_of(u: str) -> str:
    return urlparse(u).netloc.lower().replace("www.", "")


def _matches_domain(d: str) -> bool:
    d = d.lower().replace("www.", "").strip()
    return d == TARGET_DOMAIN or d.endswith("." + TARGET_DOMAIN)


def _mentioned(answer_text: str) -> bool:
    brand = re.sub(r"[^a-z0-9]", "", TARGET_DOMAIN.split(".")[0])
    return brand in re.sub(r"[^a-z0-9]", "", answer_text.lower())


def check_chatgpt(keyword: str):
    r = requests.post("https://api.openai.com/v1/responses",
                      headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                      json={"model": OPENAI_MODEL,
                            "tools": [{"type": "web_search"}],
                            "input": keyword},
                      timeout=120)
    r.raise_for_status()
    data = r.json()
    text = " ".join(
        c.get("text", "")
        for item in data.get("output", []) if item.get("type") == "message"
        for c in item.get("content", [])
    )
    # collect every URL in the raw response, in order, deduped by domain
    urls, seen = [], set()
    for u in URL_RE.findall(json.dumps(data)):
        d = _domain_of(u)
        if d and d not in seen:
            seen.add(d)
            urls.append(u)
    pos, cited_url = None, None
    for i, u in enumerate(urls, start=1):
        if _matches_domain(_domain_of(u)):
            pos, cited_url = i, u
            break
    return pos, cited_url, _mentioned(text)


def check_gemini(keyword: str):
    """Gemini with Google Search grounding. Grounding chunk URIs are
    Google redirect links, but each chunk's title carries the source
    domain - match on both."""
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                 "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": keyword}]}],
              "tools": [{"google_search": {}}]},
        timeout=120)
    r.raise_for_status()
    data = r.json()

    cand = data.get("candidates", [{}])[0]
    text = " ".join(p.get("text", "")
                    for p in cand.get("content", {}).get("parts", []))

    chunks = cand.get("groundingMetadata", {}).get("groundingChunks", [])
    pos, cited_url = None, None
    for i, ch in enumerate(chunks, start=1):
        web = ch.get("web", {})
        title = web.get("title", "")     # usually the source domain
        uri = web.get("uri", "")
        if _matches_domain(title) or _matches_domain(_domain_of(uri)):
            pos = i
            cited_url = uri if "grounding-api-redirect" not in uri else \
                "https://" + TARGET_DOMAIN
            break
    return pos, cited_url, _mentioned(text)


# tab name in the Google Sheet -> (env key required, client fn)
LLM_PROVIDERS = {
    "llm_chatgpt": ("OPENAI_API_KEY", check_chatgpt),
    "llm_gemini":  ("GEMINI_API_KEY", check_gemini),
}
