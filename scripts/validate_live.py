#!/usr/bin/env python3
"""Validate Grimoire's parsers against a REAL guide URL.

The repo is developed in an environment that cannot reach the guide sites,
so provider endpoint guesses (see providers/*.py CANDIDATE_* constants) need
this script run from a normal network - your desktop or the Deck itself:

    python3 scripts/validate_live.py https://mobalytics.gg/diablo-4/builds/...
    python3 scripts/validate_live.py https://maxroll.gg/d4/planner/...
    python3 scripts/validate_live.py https://d4builds.gg/builds/...

It prints the provider, the extracted title and every parsed section. If a
provider only yields a title (no sections), its structured parsing needs
work - paste the output into a GitHub issue.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "py_modules")
)

from grimoire.providers import detect_provider, fetch_metadata


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    url = sys.argv[1]
    print(f"provider: {detect_provider(url)}")
    meta = fetch_metadata(url)
    print(f"title:    {meta['title'] or '(none)'}")
    if not meta["sections"]:
        print("sections: (none - structured parsing found nothing on this page)")
    for section in meta["sections"]:
        print(f"\n## {section['title']}")
        for item in section["items"]:
            print(f"  {item}")
    print("\nfull JSON:")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
