"""Build-guide providers.

v0.1 ships a generic provider that works for ANY guide URL: it fetches the
page and extracts the og:title / <title> so the library entry is readable.
Provider-specific structured parsers (skills, gear affixes, paragon steps)
plug in here later - see mobalytics.py / maxroll.py / d4builds.py stubs.
"""
import html
import re
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) decky-grimoire/0.1 "
    "(+https://github.com/sabissimo/decky-grimoire)"
)

PROVIDERS = {
    "mobalytics.gg": "mobalytics",
    "maxroll.gg": "maxroll",
    "d4builds.gg": "d4builds",
}


def detect_provider(url: str) -> str:
    for domain, name in PROVIDERS.items():
        if domain in url:
            return name
    return "web"


def _extract_title(page: str) -> str:
    m = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', page
    ) or re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', page
    ) or re.search(r"<title[^>]*>([^<]+)</title>", page)
    return html.unescape(m.group(1)).strip() if m else ""


def fetch_metadata(url: str) -> dict:
    """Fetch a guide page and return {title, sections}. Blocking - callers
    run this in an executor. Structured sections come from provider parsers;
    until those land, sections is empty and the frontend falls back to the
    user's own notes plus an 'open in browser' button."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        page = resp.read(1_000_000).decode("utf-8", errors="replace")

    title = _extract_title(page)
    sections: list = []

    # TODO(provider parsers): dispatch on detect_provider(url) and extract
    # structured build data (skills, gear affixes, paragon steps) into
    # sections = [{"title": str, "items": [str, ...]}, ...]

    return {"title": title, "sections": sections}
