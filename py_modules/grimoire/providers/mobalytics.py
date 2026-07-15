"""Mobalytics parser.

Mobalytics has no public API; the site is a Next.js app backed by GraphQL.
Build pages embed their data in the __NEXT_DATA__ blob, which we scan for
recognizable build structures. This is inherently fragile (breaks when they
ship a redesign), so it must always degrade gracefully to the generic
title + open-in-browser behaviour - the dispatcher guarantees that.

Note: scraping is tolerated for personal use but Mobalytics' ToS doesn't
invite it. Grimoire only ever fetches pages the user explicitly pasted,
once per add/refresh - no crawling, no background polling.
"""
from grimoire.parseutil import (
    extract_json_scripts,
    heading_outline,
    sections_from_tree,
)


def parse(url: str, page: str, http_get) -> dict:
    result = {"title": "", "sections": []}

    for blob in extract_json_scripts(page):
        sections = sections_from_tree(blob)
        if sections:
            result["sections"] = sections
            break

    if not result["sections"]:
        outline = heading_outline(page)
        if outline:
            result["sections"] = [{"title": "Guide outline", "items": outline}]

    return result
