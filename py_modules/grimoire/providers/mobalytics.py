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


def _add(sections, title, items):
    if items:
        sections.append({"title": title, "items": items[:MAX_ITEMS_PER_SECTION]})


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
    """Per-item affix priority: 'Rod Of Kepeleke: Dexterity, Emerald ×2, ...'
    Consecutive duplicate modifiers (gem sockets) compress to ×n."""
    lines = []
    for item in variant.get("equipmentPriorityList") or []:
        if not isinstance(item, dict):
            continue
        name = _pretty(item.get("slug"))
        if not name:
            continue
        mods = []
        for mod in item.get("modifiers") or []:
            label = _pretty(mod.get("slug")) if isinstance(mod, dict) else ""
            if not label:
                continue
            if mods and mods[-1][0] == label:
                mods[-1][1] += 1
            else:
                mods.append([label, 1])
        if mods:
            rendered = ", ".join(l if n == 1 else f"{l} ×{n}" for l, n in mods)
            lines.append(f"{name}: {rendered}")
    return lines


def _paragon(variant) -> list:
    lines = []
    for board in (variant.get("paragon") or {}).get("boards") or []:
        if not isinstance(board, dict):
            continue
        name = _pretty(_strip_class((board.get("board") or {}).get("slug") or ""))
        if not name:
            continue
        glyph = _pretty(_strip_class((board.get("glyph") or {}).get("slug") or ""))
        if glyph:
            level = board.get("glyphLevel")
            name += f" — {glyph}" + (
                f" ({level})" if isinstance(level, (int, float)) and level else ""
            )
        lines.append(name)
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
    _add(sections, "Skill Tree", _skill_tree(variant))
    gear, gifts = _gear_and_gifts(variant)
    _add(sections, "Gear", gear)
    _add(sections, "Divine Gifts", gifts)
    _add(sections, "Stat Priorities", _stat_priorities(variant))
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
