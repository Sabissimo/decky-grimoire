"""Mobalytics parser.

Mobalytics has no public API; the site is a React SPA backed by GraphQL.
Build pages embed their data in a `window.__PRELOADED_STATE__ = {...}`
bootstrap blob (verified live 2026-07-15; extract_json_scripts picks it up
via extract_window_json), which we scan for recognizable build structures.
The build lives under buildVariants: assigned skills carry full names in
nested {skill: {name}} wrappers, gear priorities carry slugs only - both
handled generically by parseutil.named_items. This is inherently fragile
(breaks when they ship a redesign), so it must always degrade gracefully to
the generic title + open-in-browser behaviour - the dispatcher guarantees
that.

Note: scraping is tolerated for personal use but Mobalytics' ToS doesn't
invite it. Grimoire only ever fetches pages the user explicitly pasted,
once per add/refresh - no crawling, no background polling.
"""
from grimoire.parseutil import (
    extract_json_scripts,
    heading_outline,
    sections_from_tree,
    walk,
)

# The GraphQL result holding THE page's own build. The preloaded state also
# caches sidebar queries (featured builds and the like), so scanning the
# whole blob can win the wrong 'skills' list - anchor to this subtree first.
DOCUMENT_KEY = "userGeneratedDocumentBySlug"


def _page_document(blob):
    for node in walk(blob):
        if isinstance(node, dict) and DOCUMENT_KEY in node:
            return node[DOCUMENT_KEY]
    return None


def parse(url: str, page: str, http_get) -> dict:
    result = {"title": "", "sections": []}

    # Two passes: a blob containing the page's own document always beats a
    # whole-blob scan of some other embed (nav/search caches also embed
    # build-shaped JSON, and a generic scan of those wins the wrong build).
    blobs = extract_json_scripts(page)
    for blob in blobs:
        doc = _page_document(blob)
        if doc:
            sections = sections_from_tree(doc)
            if sections:
                result["sections"] = sections
                break
    if not result["sections"]:
        for blob in blobs:
            sections = sections_from_tree(blob)
            if sections:
                result["sections"] = sections
                break

    if not result["sections"]:
        outline = heading_outline(page)
        if outline:
            result["sections"] = [{"title": "Guide outline", "items": outline}]

    return result
