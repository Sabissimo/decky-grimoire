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

    # The generic scan gets skills and gear; boards and per-slot stats carry
    # detail it can't see (glyphs, greater-affix/masterwork/temper markers),
    # so rebuild those sections by hand.
    for title, items in (
        ("Paragon Boards", _paragon_boards(doc)),
        ("Stat Priorities", _stat_priorities(doc)),
    ):
        if items:
            result["sections"] = [
                s for s in result["sections"] if s["title"] != title
            ] + [{"title": title, "items": items}]
    return result


def _paragon_boards(doc) -> list:
    boards = [
        b for b in (doc.get("paragon") or {}).get("boards") or []
        if isinstance(b, dict) and isinstance(b.get("name"), str) and b["name"].strip()
    ]
    boards.sort(
        key=lambda b: b.get("boardNumber")
        if isinstance(b.get("boardNumber"), (int, float))
        else 999
    )
    lines = []
    for i, board in enumerate(boards, 1):
        line = f"{i}. {board['name'].strip()}"
        glyph = board.get("glyph")
        if isinstance(glyph, str) and glyph.strip():
            level = board.get("glyphLevel")
            line += f" — {glyph.strip()}" + (
                f" ({int(level)})" if isinstance(level, (int, float)) and level else ""
            )
        rotation = board.get("rotation")
        if isinstance(rotation, (int, float)) and rotation % 360:
            line += f" · rotate {int(rotation % 360)}°"
        lines.append(line)
    return lines


def _first_live_map(doc, *keys):
    """The first of several slot->list maps that has any real value.
    d4builds keeps legacy twins around ('stats' full of None next to
    'newStats' with the data)."""
    for key in keys:
        m = doc.get(key)
        if isinstance(m, dict) and any(
            isinstance(v, list) and any(x is not None for x in v)
            for v in m.values()
        ):
            return m
    return {}


# Firestore maps come back in arbitrary key order; present slots the way a
# player reads a character sheet.
SLOT_ORDER = (
    "Helm", "Chest Armor", "Gloves", "Pants", "Boots",
    "Amulet", "Ring 1", "Ring 2",
    "Slashing Weapon", "Bludgeoning Weapon", "Dual-Wield Weapon 1",
    "Dual-Wield Weapon 2", "Ranged Weapon", "Weapon", "Offhand", "Shield",
)


def _slot_rank(slot: str) -> tuple:
    try:
        return (0, SLOT_ORDER.index(slot))
    except ValueError:
        return (1, slot)


def _stat_priorities(doc) -> list:
    """Slot header + indented stat rows. Parallel per-slot arrays mark what
    matters when hunting gear: greaterAffixes[i] flags the greater-affix
    (✱) pick for stats[i], masterworking[i] the masterwork-crit target;
    temperingStats and gems/runes get their own labeled rows."""
    stats = _first_live_map(doc, "newStats", "stats")
    if not stats:
        return []
    greater = doc.get("greaterAffixes") or {}
    master = doc.get("masterworking") or {}
    tempering = doc.get("temperingStats") or {}
    gems = _first_live_map(doc, "newGems", "gems")

    lines = []
    for slot in sorted(stats, key=_slot_rank):
        names = stats[slot]
        if not isinstance(names, list):
            continue
        g = greater.get(slot) if isinstance(greater.get(slot), list) else []
        m = master.get(slot) if isinstance(master.get(slot), list) else []
        rows = []
        for i, name in enumerate(names):
            if not isinstance(name, str) or not name.strip():
                continue
            row = "  – "
            if i < len(g) and g[i]:
                row += "✱ "
            row += name.strip()
            if i < len(m) and m[i]:
                row += " (masterwork)"
            rows.append(row)
        tempers = tempering.get(slot)
        for temper in tempers if isinstance(tempers, list) else []:
            if isinstance(temper, str) and temper.strip():
                rows.append(f"  – Temper ✱ {temper.strip()}")
        socket_list = gems.get(slot) if isinstance(gems.get(slot), list) else []
        sockets = {}
        for gem in socket_list:
            if isinstance(gem, str) and gem.strip():
                sockets[gem.strip()] = sockets.get(gem.strip(), 0) + 1
        if sockets:
            rows.append(
                "  – Sockets: "
                + ", ".join(s if n == 1 else f"{s} ×{n}" for s, n in sockets.items())
            )
        if rows:
            lines.append(slot)
            lines.extend(rows)
    return lines
