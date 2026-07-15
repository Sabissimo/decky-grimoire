"""d4builds.gg parser.

d4builds.gg is a Gatsby SPA whose build documents live in a public Firestore
database (verified live 2026-07-15):

    https://firestore.googleapis.com/v1/projects/d4builds-a3254/databases/
        (default)/documents/builds/<uuid>

Two flavours of build URL:

- d4builds.gg/builds/<uuid> - the uuid IS the Firestore document id.
- d4builds.gg/builds/<slug> (named meta builds, e.g. whirlwind-barbarian-
  endgame) - the slug resolves to a uuid via the Gatsby page-data JSON's
  pageContext.seoId, which also carries the guide's display name (seoName).

The Firestore response uses typed fields ({"stringValue": ...}); parseutil's
firestore_to_plain() flattens it, then the generic structure scan extracts
sections. Everything here stays best-effort: any failure falls back to the
generic title + open-in-browser behaviour via the dispatcher.
"""
import json
import re

from grimoire.parseutil import (
    extract_json_scripts,
    firestore_to_plain,
    sections_from_tree,
)

BUILD_URL_RE = re.compile(r"d4builds\.gg/builds/([A-Za-z0-9-]+)")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")

PAGE_DATA_ENDPOINT = "https://d4builds.gg/page-data/builds/{slug}/page-data.json"
FIRESTORE_ENDPOINT = (
    "https://firestore.googleapis.com/v1/projects/d4builds-a3254/"
    "databases/(default)/documents/builds/{bid}"
)


def _resolve_slug(slug: str, http_get):
    """Named build slug -> (uuid, display name) via Gatsby page-data."""
    body = http_get(PAGE_DATA_ENDPOINT.format(slug=slug))
    ctx = json.loads(body).get("result", {}).get("pageContext", {})
    bid = ctx.get("seoId")
    name = ctx.get("seoName")
    return (
        bid if isinstance(bid, str) and UUID_RE.match(bid) else None,
        name.strip() if isinstance(name, str) else "",
    )


def parse(url: str, page: str, http_get) -> dict:
    result = {"title": "", "sections": []}

    # Embedded JSON first: free if a future deploy server-renders builds.
    for blob in extract_json_scripts(page):
        sections = sections_from_tree(blob)
        if sections:
            result["sections"] = sections
            return result

    m = BUILD_URL_RE.search(url)
    if not m:
        return result
    bid = m.group(1)

    if not UUID_RE.match(bid):
        try:
            bid, result["title"] = _resolve_slug(bid, http_get)
        except Exception:
            return result
        if not bid:
            return result

    try:
        doc = firestore_to_plain(json.loads(http_get(FIRESTORE_ENDPOINT.format(bid=bid))))
    except Exception:
        return result
    if not isinstance(doc, dict):
        return result

    name = doc.get("name")
    if isinstance(name, str) and name.strip():
        cls = doc.get("class")
        result["title"] = name.strip() + (
            f" ({cls.strip()})" if isinstance(cls, str) and cls.strip() else ""
        )
    result["sections"] = sections_from_tree(doc)
    return result
