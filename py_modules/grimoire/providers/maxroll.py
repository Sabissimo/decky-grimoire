"""Maxroll parser.

Two flavours of Maxroll link:

- Planner (maxroll.gg/d4/planner/<id>): backed by a planner profile service
  that returns JSON. The profile's inner data references numeric game-data
  IDs, so full skill/affix names need a mapping table (future work) - but we
  can already surface profile/variant names and anything name-like the
  structure scan finds.
- Guide article (maxroll.gg/d4/build-guides/<slug> and similar): a rendered
  article page. We extract embedded JSON if present, plus the h2/h3 heading
  outline so the panel shows the guide's structure at a glance.
"""
import json
import re

from grimoire.parseutil import (
    extract_json_scripts,
    heading_outline,
    sections_from_tree,
)

PLANNER_RE = re.compile(r"maxroll\.gg/(d4|d3|d2)/planner/([A-Za-z0-9_-]+)")

# Unverified until validate_live.py is run against a real planner URL.
CANDIDATE_PLANNER_ENDPOINTS = (
    "https://planners.maxroll.gg/profiles/load/{game}/{pid}",
    "https://planners.maxroll.gg/profiles/{game}/{pid}",
)


def _parse_planner(game: str, pid: str, http_get) -> dict:
    for endpoint in CANDIDATE_PLANNER_ENDPOINTS:
        try:
            body = http_get(endpoint.format(game=game, pid=pid))
            outer = json.loads(body)
        except Exception:
            continue
        if not isinstance(outer, dict):
            continue

        result = {"title": "", "sections": []}
        name = outer.get("name")
        if isinstance(name, str):
            result["title"] = name.strip()

        # The profile payload is typically a JSON string inside "data".
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

        result["sections"].extend(sections_from_tree(inner))
        if result["title"] or result["sections"]:
            return result
    return {"title": "", "sections": []}


def parse(url: str, page: str, http_get) -> dict:
    m = PLANNER_RE.search(url)
    if m:
        return _parse_planner(m.group(1), m.group(2), http_get)

    result = {"title": "", "sections": []}
    for blob in extract_json_scripts(page):
        result["sections"].extend(sections_from_tree(blob))
        if result["sections"]:
            break

    outline = heading_outline(page)
    if outline:
        result["sections"].append({"title": "Guide outline", "items": outline})
    return result
