"""Maxroll parser.

Two flavours of Maxroll link:

- Planner (maxroll.gg/d4/planner/<id>): backed by a planner profile service
  that returns JSON (endpoint verified live 2026-07-15). The profile's inner
  data references game-data ids; the public game-data file
  (assets-ng.maxroll.gg/d4-tools/game/data.min.json, ~12 MB) maps every id
  to a display name, so planner links parse to the same full detail as the
  other providers: per-profile (= variant) skills, skill tree with ranks,
  gear, per-item stat priorities with greater-affix ✱ / temper / socket
  markers, and paragon boards with glyphs. The game data is fetched once
  per plugin process and kept in memory; if that fetch fails, the outer
  payload's search_metadata (plain skill/item name lists) still gives a
  useful summary, and the generic scan backstops both.

- Guide article (maxroll.gg/d4/build-guides/<slug> and similar): a rendered
  article page whose embedded JSON includes full planner payloads for the
  guide's builds - each with the same search_metadata. We anchor on that; a
  generic scan of the page's JSON would surface the article's table of
  contents instead (its nav lives under an 'items' key). The h2/h3 heading
  outline is appended so the panel also shows the guide's structure.
"""
import json
import re

from grimoire.parseutil import (
    extract_json_scripts,
    heading_outline,
    sections_from_tree,
    walk,
)

PLANNER_RE = re.compile(r"maxroll\.gg/(d4|d3|d2)/planner/([A-Za-z0-9_-]+)")

# Verified live 2026-07-15: returns the full profile JSON, no auth or
# special headers needed. A deleted/unknown id answers 404 with
# {"error": "Profile not found"}.
PLANNER_ENDPOINT = "https://planners.maxroll.gg/profiles/load/{game}/{pid}"
GAME_DATA_URL = "https://assets-ng.maxroll.gg/d4-tools/game/data.min.json"

MAX_ROWS = 100

# Game data survives for the plugin process's lifetime - it's ~12 MB on the
# wire but the extracted maps are small, and guides are added rarely.
_GAME_MAPS: dict = {}

# Attribute-name noise that isn't part of the player-facing stat name.
_ATTR_NOISE = ("Multiplicative", "Additive", "Gear", "Affix")


def _camel(s: str) -> str:
    """'DarkShroud' / 'Damage_Percent_All' -> 'Dark Shroud' / spaced words."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s.replace("_", " "))
    return re.sub(r"\s+", " ", s).strip()


def _strip_template(text: str) -> str:
    """'+[{value}||] Maximum Life' (attributeDescriptions) -> 'Maximum
    Life': drop the value placeholders, keep the player-facing words."""
    text = re.sub(r"\{[^}]*\}", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    return re.sub(r"\s+", " ", text).strip(" +~*x:%|-").strip()


def _affix_label(entry, attributes, descriptions) -> str:
    """Display text for an affix. The attributeDescriptions template is the
    same string the site renders ('+[{value}||] Maximum Life'); the cleaned
    attribute name is the fallback."""
    for attr in entry.get("attributes") or []:
        if not isinstance(attr, dict):
            continue
        name = (attributes.get(str(attr.get("id"))) or {}).get("name")
        if not isinstance(name, str) or not name:
            continue
        desc = descriptions.get(name)
        if isinstance(desc, str) and desc:
            label = _strip_template(desc)
            if label:
                return label
        words = [w for w in _camel(name).split(" ") if w not in _ATTR_NOISE]
        return " ".join("%" if w == "Percent" else w for w in words)
    return ""


def _build_game_maps(gd: dict) -> dict:
    attributes = gd.get("attributes") or {}
    descriptions = gd.get("attributeDescriptions") or {}
    affix, aspect = {}, {}
    for entry in (gd.get("affixes") or {}).values():
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), int):
            continue
        affix[entry["id"]] = _affix_label(entry, attributes, descriptions)
        # Legendary powers (magicType 1) ARE aspects; the 'prefix' is the
        # aspect's short name ('Lingering' -> 'Lingering Aspect').
        prefix = entry.get("prefix")
        if entry.get("magicType") == 1 and isinstance(prefix, str) and prefix:
            aspect[entry["id"]] = f"{prefix} Aspect"

    item = {}
    for key, entry in (gd.get("items") or {}).items():
        if isinstance(entry, dict):
            item[key] = (entry.get("name") or "", _camel(entry.get("type") or ""))

    skill_name = {
        key: entry.get("name") or ""
        for key, entry in (gd.get("skills") or {}).items()
        if isinstance(entry, dict)
    }

    tree = {}
    for cls, t in (gd.get("skillTrees") or {}).items():
        nodes = {}
        for node in (t or {}).get("nodes") or []:
            if not isinstance(node, dict):
                continue
            power = (node.get("reward") or {}).get("power")
            name = skill_name.get(power)
            if isinstance(node.get("id"), int) and name:
                nodes[node["id"]] = name
        tree[cls] = nodes

    # Profile 'class' is an index into the classes table.
    class_name = {
        key: (entry.get("nameMale") or entry.get("nameFemale") or "")
        for key, entry in (gd.get("classes") or {}).items()
        if isinstance(entry, dict)
    }

    glyph = {
        key: entry.get("name") or ""
        for key, entry in (gd.get("paragonGlyphs") or {}).items()
        if isinstance(entry, dict)
    }
    board = {
        key: entry.get("name") or ""
        for key, entry in (gd.get("paragonBoards") or {}).items()
        if isinstance(entry, dict)
    }
    return {
        "affix": affix, "aspect": aspect, "item": item,
        "skill_name": skill_name, "tree": tree, "class_name": class_name,
        "glyph": glyph, "board": board,
    }


def _game_maps(game: str, http_get):
    if game in _GAME_MAPS:
        return _GAME_MAPS[game]
    if game != "d4":
        return None
    try:
        # The injected test double may not accept kwargs.
        try:
            body = http_get(GAME_DATA_URL, max_bytes=40_000_000, timeout=60)
        except TypeError:
            body = http_get(GAME_DATA_URL)
        maps = _build_game_maps(json.loads(body))
    except Exception:
        return None
    if not maps["affix"] or not maps["item"]:
        return None
    _GAME_MAPS[game] = maps
    return maps


def _skill_key_name(key: str, maps) -> str:
    """'Sorcerer_BallLightning' -> 'Ball Lightning' even without game data."""
    name = maps["skill_name"].get(key) if maps else None
    if name:
        return name
    return _camel(key.split("_", 1)[-1]) if isinstance(key, str) else ""


def _last_step(container) -> object:
    steps = (container or {}).get("steps") or []
    for step in reversed(steps):
        data = step.get("data") if isinstance(step, dict) else None
        if data:
            return data
    return None


def _tree_for_class(maps, cls) -> dict:
    """Profile 'class' is an index into the classes table (or occasionally
    already a name); skillTrees keys drift ('Paladin_NEW') - match by
    prefix when exact lookup misses. NEVER merge trees: node ids collide
    across classes and produce another class's skill names."""
    if isinstance(cls, (int, float)):
        cls = maps["class_name"].get(str(int(cls)), "")
    trees = maps["tree"]
    if isinstance(cls, str) and cls:
        if cls in trees:
            return trees[cls]
        for key, nodes in trees.items():
            if key.startswith(cls):
                return nodes
    return {}


def _stat_rows_for_item(entry, maps) -> list:
    rows = []
    for e in entry.get("explicits") or []:
        if not isinstance(e, dict):
            continue
        label = maps["affix"].get(e.get("nid"))
        if not label:
            continue
        greater = e.get("greater") or e.get("ga")
        rows.append(f"  – {'✱ ' if greater else ''}{label}")
    for e in entry.get("tempered") or []:
        if isinstance(e, dict):
            label = maps["affix"].get(e.get("nid"))
            if label:
                rows.append(f"  – Temper: {label}")
    sockets = {}
    for rune in entry.get("sockets") or []:
        if isinstance(rune, str) and rune:
            # Runes/gems are items themselves ('Rune_Condition_...' -> 'Cir').
            label = maps["item"].get(rune, ("", ""))[0] or _camel(rune.split("_")[-1])
            sockets[label] = sockets.get(label, 0) + 1
    if sockets:
        rows.append(
            "  – Sockets: "
            + ", ".join(s if n == 1 else f"{s} ×{n}" for s, n in sockets.items())
        )
    return rows


def _profile_sections(profile, item_pool, maps) -> list:
    sections = []

    bar = [
        _skill_key_name(k, maps)
        for k in profile.get("skillBar") or []
        if isinstance(k, str) and k
    ]
    if bar:
        sections.append({"title": "Skills", "items": bar[:MAX_ROWS]})

    enchants = [
        re.sub(r"^Enchantment ", "", _skill_key_name(k, maps))
        for k in profile.get("enchants") or []
        if isinstance(k, str) and k
    ]
    if enchants:
        sections.append({"title": "Enchantments", "items": enchants[:MAX_ROWS]})

    tree_data = _last_step(profile.get("skillTree"))
    if isinstance(tree_data, dict) and maps:
        nodes = _tree_for_class(maps, profile.get("class"))
        # Upgrade nodes carry the same power name as their skill - fold
        # them in: max rank + how many extra nodes were taken.
        taken = {}  # name -> [max_rank, node_count], insertion-ordered
        for node_id, rank in tree_data.items():
            if not rank:
                continue
            try:
                name = nodes.get(int(node_id))
            except (TypeError, ValueError):
                name = None
            if not name:
                continue
            if name in taken:
                taken[name][0] = max(taken[name][0], rank)
                taken[name][1] += 1
            else:
                taken[name] = [rank, 1]
        rows = []
        for name, (rank, count) in taken.items():
            line = f"{name} ({rank})" if rank > 1 else name
            if count > 1:
                line += f" +{count - 1} upgrades" if count > 2 else " +1 upgrade"
            rows.append(line)
        if rows:
            sections.append({"title": "Skill Tree", "items": rows[:MAX_ROWS]})

    gear_rows, stat_rows = [], []
    for slot_idx in (profile.get("items") or {}).values():
        entry = (item_pool or {}).get(str(slot_idx))
        if not isinstance(entry, dict):
            continue
        base_name, slot_type = maps["item"].get(entry.get("id"), ("", "")) if maps else ("", "")
        display = base_name or entry.get("name") or ""
        if not display:
            continue
        aspect_labels = [
            maps["aspect"].get(a.get("nid"))
            for a in entry.get("aspects") or []
            if isinstance(a, dict) and maps["aspect"].get(a.get("nid"))
        ]
        # 'Charm: Charm' says nothing twice.
        slotted = display if display == slot_type else (
            f"{slot_type}: {display}" if slot_type else display
        )
        line = slotted
        if aspect_labels:
            line += f" — {aspect_labels[0]}"
        gear_rows.append(line)

        rows = _stat_rows_for_item(entry, maps)
        if rows:
            stat_rows.append(slotted.replace(": ", " · ", 1))
            stat_rows.extend(rows)
    if gear_rows:
        sections.append({"title": "Gear", "items": gear_rows[:MAX_ROWS]})
    if stat_rows:
        # An item header plus ~8 stat rows for 16 slots overruns the
        # default cap - this section legitimately runs long.
        sections.append({"title": "Stat Priorities", "items": stat_rows[:MAX_ROWS * 2]})

    boards = _last_step(profile.get("paragon"))
    if isinstance(boards, list):
        rows = []
        for i, b in enumerate(boards, 1):
            if not isinstance(b, dict):
                continue
            name = maps["board"].get(b.get("id")) or _camel(str(b.get("id") or ""))
            if not name:
                continue
            line = f"{i}. {name}"
            glyph = maps["glyph"].get(b.get("glyph"))
            if glyph:
                level = b.get("glyphLevel")
                line += f" — {glyph}" + (
                    f" ({level})" if isinstance(level, (int, float)) and level > 1 else ""
                )
            rotation = b.get("rotation")
            if isinstance(rotation, (int, float)) and rotation:
                degrees = int(rotation) * 90 if rotation < 4 else int(rotation) % 360
                if degrees:
                    line += f" · rotate {degrees}°"
            rows.append(line)
        if rows:
            sections.append({"title": "Paragon Boards", "items": rows[:MAX_ROWS]})

    return sections


def _parse_planner(game: str, pid: str, http_get) -> dict:
    empty = {"title": "", "sections": [], "variants": []}
    try:
        body = http_get(PLANNER_ENDPOINT.format(game=game, pid=pid))
        outer = json.loads(body)
    except Exception:
        return empty
    if not isinstance(outer, dict) or outer.get("error"):
        return empty

    result = {"title": "", "sections": [], "variants": []}
    name = outer.get("name")
    if isinstance(name, str):
        result["title"] = name.strip()

    # The profile payload is a JSON string inside "data".
    inner = outer.get("data")
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except json.JSONDecodeError:
            inner = None
    if not isinstance(inner, dict):
        inner = {}

    # Full detail: every profile is a variant, ids resolved via game data.
    maps = _game_maps(game, http_get)
    if maps:
        profiles = inner.get("profiles") or []
        item_pool = inner.get("items") or {}
        for i, profile in enumerate(profiles, 1):
            if not isinstance(profile, dict):
                continue
            try:
                sections = _profile_sections(profile, item_pool, maps)
            except Exception:
                continue
            if sections:
                pname = profile.get("name")
                result["variants"].append({
                    "name": pname.strip()
                    if isinstance(pname, str) and pname.strip()
                    else f"Variant {i}",
                    "sections": sections,
                })
        if result["variants"]:
            result["sections"] = result["variants"][0]["sections"]
            return result

    # Fallback: names-only summary. Variant name list from profiles, then
    # search_metadata's plain-language skills/items, then the inner scan.
    profiles = inner.get("profiles") if isinstance(inner, dict) else None
    if isinstance(profiles, list):
        names = [
            p.get("name").strip()
            for p in profiles
            if isinstance(p, dict) and isinstance(p.get("name"), str)
        ]
        if names:
            result["sections"].append({"title": "Variants", "items": names})
    scanned = sections_from_tree(outer.get("search_metadata")) or sections_from_tree(inner)
    result["sections"].extend(scanned)
    return result


def parse(url: str, page: str, http_get) -> dict:
    m = PLANNER_RE.search(url)
    if m:
        return _parse_planner(m.group(1), m.group(2), http_get)

    result = {"title": "", "sections": []}
    blobs = extract_json_scripts(page)
    for blob in blobs:
        for node in walk(blob):
            if isinstance(node, dict) and isinstance(node.get("search_metadata"), dict):
                result["sections"] = sections_from_tree(node["search_metadata"])
                break
        if result["sections"]:
            break
    if not result["sections"]:
        for blob in blobs:
            result["sections"] = sections_from_tree(blob)
            if result["sections"]:
                break

    outline = heading_outline(page)
    if outline:
        result["sections"].append({"title": "Guide outline", "items": outline})
    return result
