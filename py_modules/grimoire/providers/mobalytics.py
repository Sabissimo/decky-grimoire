"""Mobalytics parser.

Mobalytics has no public API; the site is a React SPA backed by GraphQL.
Build pages embed their data in a `window.__PRELOADED_STATE__ = {...}`
bootstrap blob (verified live 2026-07-15; extract_json_scripts picks it up
via extract_window_json), which we scan for recognizable build structures.
The build lives under buildVariants and is rich: the action bar with slot
positions, the full skill tree as ACTIVATE events (occurrences = ranks),
gear as slot -> aspect/unique titles (genericBuilder), per-item stat
priorities (equipmentPriorityList modifiers), paragon boards with glyphs
and levels, charms, mercenaries, and class mechanics (spirit hall,
enchantments). _variant_sections renders all of it; if the shape ever
shifts, parse() falls back to the generic structure scan and then the
heading outline - the dispatcher guarantees a save never breaks.

Note: scraping is tolerated for personal use but Mobalytics' ToS doesn't
invite it. Grimoire only ever fetches pages the user explicitly pasted,
once per add/refresh - no crawling, no background polling.
"""
from grimoire.parseutil import (
    MAX_ITEMS_PER_SECTION,
    extract_json_scripts,
    heading_outline,
    sections_from_tree,
    walk,
)

# The GraphQL result holding THE page's own build. The preloaded state also
# caches sidebar queries (featured builds and the like), so scanning the
# whole blob can win the wrong 'skills' list - anchor to this subtree first.
DOCUMENT_KEY = "userGeneratedDocumentBySlug"

CLASS_PREFIXES = frozenset(
    ("barbarian", "sorcerer", "druid", "rogue", "necromancer",
     "spiritborn", "paladin", "warlock")
)


def _page_document(blob):
    for node in walk(blob):
        if isinstance(node, dict) and DOCUMENT_KEY in node:
            return node[DOCUMENT_KEY]
    return None


def _pretty(slug) -> str:
    if not isinstance(slug, str) or not slug.strip():
        return ""
    return slug.replace("-", " ").replace("_", " ").strip().title()


def _strip_class(slug: str) -> str:
    """'spiritborn-starter-board' -> 'starter-board' (boards and glyphs are
    always class-prefixed; the class is noise in a build for that class)."""
    head, _, tail = slug.partition("-")
    return tail if head in CLASS_PREFIXES and tail else slug


# Manually-built detail sections (stat priorities, skill tree) legitimately
# run past the generic-scan cap: an item header plus its indented stat rows.
DETAIL_CAP = 100


def _add(sections, title, items, cap=MAX_ITEMS_PER_SECTION):
    if items:
        sections.append({"title": title, "items": items[:cap]})


def _skill_bar(assigned) -> list:
    rows = []
    for entry in assigned.get("skills") or []:
        if not isinstance(entry, dict):
            continue
        skill = entry.get("skill") or {}
        name = skill.get("name")
        if isinstance(name, str) and name.strip():
            pos = entry.get("position")
            rows.append((pos if isinstance(pos, int) else 99, name.strip()))
    rows.sort()
    return [f"{p} · {n}" if p != 99 else n for p, n in rows]


def _skill_tree(variant) -> list:
    """ACTIVATE events, one per point spent - occurrences ARE the rank.

    Upgrade slugs extend their skill's slug ('stinger-potent-sting'), so
    render them as indented children of the longest matching base skill.
    """
    ranks = {}  # slug -> count, insertion-ordered = point-spend order
    for entry in (variant.get("skillTree") or {}).get("skills") or []:
        if not isinstance(entry, dict) or entry.get("actionType") != "ACTIVATE":
            continue
        slug = (entry.get("skill") or {}).get("slug")
        if isinstance(slug, str) and slug:
            ranks[slug] = ranks.get(slug, 0) + 1
    lines = []
    slugs = list(ranks)
    for slug, count in ranks.items():
        base = max(
            (b for b in slugs if b != slug and slug.startswith(b + "-")),
            key=len,
            default="",
        )
        label = _pretty(slug[len(base) + 1:] if base else slug)
        if base:
            label = f"  – {label}"
        lines.append(f"{label} ({count})" if count > 1 else label)
    return lines


def _spirit_hall(assigned) -> list:
    hall = assigned.get("spiritGuardians") or {}
    items = []
    for key, label in (("primaryId", "Primary"), ("secondaryId", "Secondary")):
        v = hall.get(key)
        if isinstance(v, str) and v.strip():
            items.append(f"{label}: {_pretty(v)}")
    return items


def _enchantments(assigned) -> list:
    return [
        e["name"].strip()
        for e in assigned.get("enchantments") or []
        if isinstance(e, dict) and isinstance(e.get("name"), str) and e["name"].strip()
    ]


def _gear_and_gifts(variant):
    gear, gifts = [], []
    for slot in (variant.get("genericBuilder") or {}).get("slots") or []:
        if not isinstance(slot, dict):
            continue
        slot_slug = slot.get("gameSlotSlug")
        # Seasonal charm/seal slots duplicate the Charms section.
        if isinstance(slot_slug, str) and slot_slug.startswith("season-"):
            continue
        entity = slot.get("gameEntity") or {}
        title = entity.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        kind = entity.get("type")
        if kind == "divineGifts":
            gifts.append(title.strip())
            continue
        name = title.strip() + (" (Unique)" if kind == "uniqueItems" else "")
        slot_name = _pretty(slot.get("gameSlotSlug"))
        gear.append(f"{slot_name}: {name}" if slot_name else name)
    return gear, gifts


def _stat_priorities(variant) -> list:
    """Per-item affix priority as an item header + indented stat rows.

    Mobalytics types every modifier: 'gear' is a regular affix, 'socket' a
    gem/rune, 'tempering' a tempered stat (its slug is prefixed with the
    temper manual, e.g. worldly-destruction-attack-speed) - the panel must
    say which is which, so sockets aggregate into one row and tempers get a
    'Temper ✱' label. Mobalytics doesn't publish greater-affix picks; only
    d4builds carries those.

    Headers lead with the SLOT ('Ring 1 · Aspect of the Moonrise') - a
    build has four aspect-named rings and pants, and without the slot the
    reader can't tell which item a stat block belongs to. The clean item
    title comes from genericBuilder (the priority-list slug drags the
    class name along, 'aspect-of-debilitating-toxins-spiritborn').
    """
    titles = {}  # slot slug -> clean item title
    for slot in (variant.get("genericBuilder") or {}).get("slots") or []:
        if isinstance(slot, dict):
            title = (slot.get("gameEntity") or {}).get("title")
            if isinstance(title, str) and title.strip():
                titles[slot.get("gameSlotSlug")] = title.strip()

    lines = []
    for item in variant.get("equipmentPriorityList") or []:
        if not isinstance(item, dict):
            continue
        slot = item.get("type")
        name = titles.get(slot) or _pretty(item.get("slug"))
        if not name:
            continue
        slot_name = _pretty(slot)
        if slot_name:
            name = f"{slot_name} · {name}"
        rows, sockets = [], {}
        socket_row_at = None
        for mod in item.get("modifiers") or []:
            if not isinstance(mod, dict):
                continue
            label = _pretty(mod.get("slug"))
            if not label:
                continue
            kind = mod.get("type")
            if kind == "socket":
                if socket_row_at is None:
                    socket_row_at = len(rows)
                    rows.append(None)  # placeholder, filled after the loop
                sockets[label] = sockets.get(label, 0) + 1
            elif kind == "tempering":
                rows.append(f"  – Temper ✱ {label}")
            else:
                rows.append(f"  – {label}")
        if socket_row_at is not None:
            rendered = ", ".join(
                g if n == 1 else f"{g} ×{n}" for g, n in sockets.items()
            )
            rows[socket_row_at] = f"  – Sockets: {rendered}"
        if rows:
            lines.append(name)
            lines.extend(rows)
    return lines


def _paragon(variant) -> list:
    """Boards in attach order with glyph, level, node investment and the
    rotation needed to walk them; closes with the glyph levelling order.
    Node PICKS are only coordinates in this data (no names), so the path
    itself stays with 'Open full guide'."""
    paragon = variant.get("paragon") or {}
    # Node slugs are '<board>-x11-y14' - count investment per board.
    node_counts = {}
    for node in paragon.get("nodes") or []:
        slug = node.get("slug") if isinstance(node, dict) else None
        if isinstance(slug, str) and "-x" in slug:
            board = slug.rsplit("-x", 1)[0]
            node_counts[board] = node_counts.get(board, 0) + 1

    lines = []
    for i, board in enumerate(paragon.get("boards") or [], 1):
        if not isinstance(board, dict):
            continue
        slug = (board.get("board") or {}).get("slug") or ""
        name = _pretty(_strip_class(slug))
        if not name:
            continue
        line = f"{i}. {name}"
        glyph = _pretty(_strip_class((board.get("glyph") or {}).get("slug") or ""))
        if glyph:
            level = board.get("glyphLevel")
            line += f" — {glyph}" + (
                f" ({level})" if isinstance(level, (int, float)) and level else ""
            )
        # The board slugs in `boards` and `nodes` drift slightly
        # ('starter-board' vs 'starting-board') - match on either.
        count = node_counts.get(slug) or node_counts.get(
            slug.replace("starter", "starting")
        )
        if count:
            line += f" · {count} nodes"
        rotation = board.get("rotation")
        if isinstance(rotation, (int, float)) and rotation % 360:
            line += f" · rotate {int(rotation % 360)}°"
        lines.append(line)

    glyph_order = [
        _pretty(_strip_class(g.get("slug")))
        for g in paragon.get("priorityList") or []
        if isinstance(g, dict) and isinstance(g.get("slug"), str)
    ]
    if len(glyph_order) > 1:
        lines.append("Glyph order: " + " → ".join(glyph_order))
    return lines


def _charms(variant) -> list:
    return [
        _pretty(t.get("slug"))
        for t in variant.get("talismansPriorityList") or []
        if isinstance(t, dict) and isinstance(t.get("slug"), str)
        and t["slug"] and t["slug"] != "new-seal"  # empty-slot placeholder
    ]


def _mercenaries(variant) -> list:
    merc = variant.get("mercenary") or {}
    items = []
    for key, label in (
        ("primaryMercenary", "Primary"),
        ("reinforcementMercenary", "Reinforcement"),
    ):
        name = _pretty((merc.get(key) or {}).get("slug"))
        if name:
            items.append(f"{label}: {name}")
    return items


def _variant_sections(variant) -> list:
    sections = []
    assigned = variant.get("assignedSkills") or {}
    _add(sections, "Skills", _skill_bar(assigned))
    _add(sections, "Spirit Hall", _spirit_hall(assigned))
    _add(sections, "Enchantments", _enchantments(assigned))
    _add(sections, "Skill Tree", _skill_tree(variant), cap=DETAIL_CAP)
    gear, gifts = _gear_and_gifts(variant)
    _add(sections, "Gear", gear)
    _add(sections, "Divine Gifts", gifts)
    _add(sections, "Stat Priorities", _stat_priorities(variant), cap=DETAIL_CAP)
    _add(sections, "Paragon Boards", _paragon(variant))
    _add(sections, "Charms", _charms(variant))
    _add(sections, "Mercenaries", _mercenaries(variant))
    return sections


def _detailed_sections(doc) -> list:
    for node in walk(doc):
        if isinstance(node, dict) and isinstance(node.get("buildVariants"), dict):
            variants = node["buildVariants"].get("values") or []
            if variants and isinstance(variants[0], dict):
                return _variant_sections(variants[0])
    return []


def parse(url: str, page: str, http_get) -> dict:
    result = {"title": "", "sections": []}

    # Two passes: a blob containing the page's own document always beats a
    # whole-blob scan of some other embed (nav/search caches also embed
    # build-shaped JSON, and a generic scan of those wins the wrong build).
    blobs = extract_json_scripts(page)
    for blob in blobs:
        doc = _page_document(blob)
        if not doc:
            continue
        try:
            result["sections"] = _detailed_sections(doc)
        except Exception:
            result["sections"] = []
        if not result["sections"]:
            result["sections"] = sections_from_tree(doc)
        if result["sections"]:
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
