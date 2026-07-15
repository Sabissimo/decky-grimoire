"""Mobalytics structured parser - NOT IMPLEMENTED YET.

Mobalytics has no public API; their site is a Next.js app backed by GraphQL.
The plan for structured parsing is to read the __NEXT_DATA__ JSON blob
embedded in the build page and map it into Grimoire's generic sections
format. This is inherently fragile (breaks when they ship a redesign), so
it must always degrade gracefully to the generic title + open-in-browser
behaviour in providers/__init__.py.

Expected output shape once implemented:
    {
        "title": "Bone Spear Necromancer",
        "sections": [
            {"title": "Skill Order", "items": ["1. Bone Splinters", ...]},
            {"title": "Gear Affixes", "items": ["Helm: +Ranks Bone Spear", ...]},
            {"title": "Paragon Steps", "items": ["Board 1: Starter ...", ...]},
        ],
    }
"""


def parse(url: str, page: str) -> dict:
    raise NotImplementedError("Mobalytics structured parsing not implemented yet")
