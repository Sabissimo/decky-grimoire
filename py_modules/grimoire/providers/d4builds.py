"""d4builds.gg parser.

d4builds.gg is a community planner: d4builds.gg/builds/<uuid> maps to a
structured build document, which makes it the most parser-friendly provider.
It's a JS single-page app, so the build data may not be in the initial HTML;
we try, in order:

1. JSON embedded in the page itself (covers server-rendered deploys)
2. Candidate JSON endpoints derived from the build id

The candidate endpoints are educated guesses and are validated by
scripts/validate_live.py on a real network (this repo is developed in an
environment that cannot reach the site). Anything that fails just falls
back to the generic title + open-in-browser behaviour.
"""
import json
import re

from grimoire.parseutil import extract_json_scripts, sections_from_tree

BUILD_ID_RE = re.compile(r"d4builds\.gg/builds/([0-9a-fA-F-]{8,})")

# Unverified until validate_live.py is run against a real build URL.
CANDIDATE_ENDPOINTS = (
    "https://d4builds.gg/api/builds/{bid}",
    "https://api.d4builds.gg/builds/{bid}",
)


def parse(url: str, page: str, http_get) -> dict:
    result = {"title": "", "sections": []}

    for blob in extract_json_scripts(page):
        sections = sections_from_tree(blob)
        if sections:
            result["sections"] = sections
            return result

    m = BUILD_ID_RE.search(url)
    if not m:
        return result
    bid = m.group(1)

    for endpoint in CANDIDATE_ENDPOINTS:
        try:
            body = http_get(endpoint.format(bid=bid))
            data = json.loads(body)
        except Exception:
            continue
        sections = sections_from_tree(data)
        if sections:
            if isinstance(data, dict):
                name = data.get("name") or data.get("title")
                if isinstance(name, str):
                    result["title"] = name.strip()
            result["sections"] = sections
            return result

    return result
