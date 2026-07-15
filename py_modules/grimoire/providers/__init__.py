"""Build-guide providers.

Every URL gets the generic treatment: fetch the page, extract og:title /
<title> so the library entry is readable. On top of that, provider-specific
parsers extract structured sections (skills, gear, paragon...) when they can.
Parsers are best-effort by contract: any exception or empty result falls
back to the generic behaviour, so a site redesign can never break the
library itself.
"""
import html
import re
import urllib.request

from grimoire.parseutil import strip_tags  # noqa: F401  (re-exported for tests)

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


def _get_parser(provider: str):
    if provider == "mobalytics":
        from grimoire.providers import mobalytics as mod
    elif provider == "maxroll":
        from grimoire.providers import maxroll as mod
    elif provider == "d4builds":
        from grimoire.providers import d4builds as mod
    else:
        return None
    return mod


def http_get(url: str, max_bytes: int = 2_000_000, timeout: int = 10) -> str:
    """Blocking GET returning decoded text. Callers run in an executor."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(max_bytes).decode("utf-8", errors="replace")


def _extract_title(page: str) -> str:
    m = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', page
    ) or re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', page
    ) or re.search(r"<title[^>]*>([^<]+)</title>", page)
    return html.unescape(m.group(1)).strip() if m else ""


def fetch_metadata(url: str, get=http_get) -> dict:
    """Fetch a guide page and return {title, sections}. Blocking - callers
    run this in an executor. `get` is injectable for tests."""
    page = get(url)
    title = _extract_title(page)
    sections: list = []

    parser = _get_parser(detect_provider(url))
    if parser is not None:
        try:
            parsed = parser.parse(url, page, get) or {}
            if parsed.get("title"):
                title = parsed["title"]
            sections = parsed.get("sections") or []
        except Exception:
            # Best-effort by contract: structured parsing must never break
            # the generic save-the-link flow.
            sections = []

    return {"title": title, "sections": sections}
