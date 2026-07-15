"""Maxroll parser.

Two flavours of Maxroll link:

- Planner (maxroll.gg/d4/planner/<id>): backed by a planner profile service
  that returns JSON (endpoint verified live 2026-07-15). The profile's inner
  data references numeric game-data IDs, but the outer payload's
  search_metadata already carries plain-language skill/item names, plus
  profile/variant names - no id mapping table needed for a useful summary.
- Guide article (maxroll.gg/d4/build-guides/<slug> and similar): a rendered
  article page whose embedded JSON includes full planner payloads for the
  guide's builds - each with the same search_metadata (plain skill/item
  names) the planner API returns. We anchor on that; a generic scan of the
  page's JSON would surface the article's table of contents instead (its
  nav lives under an 'items' key). The h2/h3 heading outline is appended so
  the panel also shows the guide's structure at a glance.
"""
import json
import re

from grimoire.parseutil import (
    extract_json_scripts,
    heading_outline,
    sections_from_tree,
    walk,
)

PLANNER_RE = re.compile(r"maxroll\.gg/(d4|d3|d2)/planner/([A-Za-z0-9_-]+)")

# Verified live 2026-07-15: returns the full profile JSON, no auth or
# special headers needed. A deleted/unknown id answers 404 with
# {"error": "Profile not found"}.
PLANNER_ENDPOINT = "https://planners.maxroll.gg/profiles/load/{game}/{pid}"


def _parse_planner(game: str, pid: str, http_get) -> dict:
    empty = {"title": "", "sections": []}
    try:
        body = http_get(PLANNER_ENDPOINT.format(game=game, pid=pid))
        outer = json.loads(body)
    except Exception:
        return empty
    if not isinstance(outer, dict) or outer.get("error"):
        return empty

    result = {"title": "", "sections": []}
    name = outer.get("name")
    if isinstance(name, str):
        result["title"] = name.strip()

    # The profile payload is a JSON string inside "data".
    inner = outer.get("data")
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except json.JSONDecodeError:
            inner = None
    if inner is None:
        inner = outer

    profiles = inner.get("profiles") if isinstance(inner, dict) else None
    if isinstance(profiles, list):
        names = [
            p.get("name").strip()
            for p in profiles
            if isinstance(p, dict) and isinstance(p.get("name"), str)
        ]
        if names:
            result["sections"].append({"title": "Variants", "items": names})

    # The outer payload's search_metadata carries plain-language skill and
    # item names ({"skills": ["Ball Lightning", ...], "items": [...]}), which
    # the inner planner data only has as numeric game-data ids - so prefer
    # scanning it, falling back to the inner data.
    scanned = sections_from_tree(outer.get("search_metadata")) or sections_from_tree(inner)
    result["sections"].extend(scanned)
    return result


def parse(url: str, page: str, http_get) -> dict:
    m = PLANNER_RE.search(url)
    if m:
        return _parse_planner(m.group(1), m.group(2), http_get)

    result = {"title": "", "sections": []}
    blobs = extract_json_scripts(page)
    for blob in blobs:
        for node in walk(blob):
            if isinstance(node, dict) and isinstance(node.get("search_metadata"), dict):
                result["sections"] = sections_from_tree(node["search_metadata"])
                break
        if result["sections"]:
            break
    if not result["sections"]:
        for blob in blobs:
            result["sections"] = sections_from_tree(blob)
            if result["sections"]:
                break

    outline = heading_outline(page)
    if outline:
        result["sections"].append({"title": "Guide outline", "items": outline})
    return result
