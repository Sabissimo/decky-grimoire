"""Shared parsing helpers for provider modules.

Design principle: guide sites ship no public APIs and redesign freely, so we
never rely on exact JSON paths. Instead we extract whatever JSON the page
embeds and SCAN it for recognizable shapes (lists of dicts with name-like
keys under skill/gear/paragon-like keys). A redesign then degrades to fewer
sections instead of an exception.
"""
import html
import json
import re

# Keys that identify a dict as "a named thing" (skill, item, aspect...)
NAME_KEYS = ("name", "title", "label", "skillName", "itemName", "aspectName")

# Container keys we recognize, mapped to the section title shown in the panel.
# Order matters: first hit wins per title.
SECTION_KEYS = (
    ("skills", "Skills"),
    ("activeSkills", "Skills"),
    ("skillTree", "Skills"),
    ("paragonBoards", "Paragon Boards"),
    ("paragon", "Paragon Boards"),
    ("boards", "Paragon Boards"),
    ("aspects", "Aspects"),
    ("legendaryAspects", "Aspects"),
    ("uniques", "Uniques"),
    ("gear", "Gear"),
    ("items", "Gear"),
    ("equipmentPriorityList", "Gear"),
    ("enchantments", "Enchantments"),
    ("gems", "Gems"),
    ("vampiricPowers", "Vampiric Powers"),
    ("mercenaries", "Mercenaries"),
    ("runewords", "Runewords"),
)

MAX_ITEMS_PER_SECTION = 30


def extract_next_data(page: str):
    """The __NEXT_DATA__ blob Next.js sites embed in every page."""
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', page, re.S
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def extract_window_json(page: str) -> list:
    """JSON blobs assigned to window globals in inline scripts.

    SPAs that don't use __NEXT_DATA__ still embed their bootstrap state as
    `window.__PRELOADED_STATE__ = {...}` / `window.__remixContext = {...}`
    (verified live: Mobalytics uses the former, Maxroll the latter). The
    assignment is JS, not a JSON script tag, so raw_decode from the opening
    brace and let trailing `;</script>` fall off the end.
    """
    out = []
    dec = json.JSONDecoder()
    for m in re.finditer(r"window\.(\w+)\s*=\s*(?=[\[{])", page):
        try:
            blob, _ = dec.raw_decode(page, m.end())
        except json.JSONDecodeError:
            continue
        if isinstance(blob, (dict, list)) and blob:
            out.append(blob)
    return out


def extract_json_scripts(page: str) -> list:
    """Every embedded JSON blob on the page: application/json and ld+json
    script tags, __NEXT_DATA__, and window-global assignments."""
    out = []
    for m in re.finditer(
        r'<script[^>]*type=["\']application/(?:ld\+)?json["\'][^>]*>(.*?)</script>',
        page,
        re.S,
    ):
        try:
            out.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    nd = extract_next_data(page)
    if nd is not None:
        out.append(nd)
    out.extend(extract_window_json(page))
    return out


def firestore_to_plain(value):
    """Decode Firestore REST API typed values into plain JSON.

    Firestore wraps every value: {"stringValue": "x"}, {"arrayValue":
    {"values": [...]}}, {"mapValue": {"fields": {...}}}. A whole document is
    {"name": ..., "fields": {...}}. Unknown wrappers pass through unchanged
    so a new Firestore type degrades to noise, not an exception.
    """
    if isinstance(value, dict):
        if "fields" in value and isinstance(value["fields"], dict):
            return {k: firestore_to_plain(v) for k, v in value["fields"].items()}
        if len(value) == 1:
            (kind, inner), = value.items()
            if kind in ("stringValue", "timestampValue", "referenceValue"):
                return inner
            if kind == "integerValue":
                return int(inner)
            if kind == "doubleValue":
                return float(inner)
            if kind == "booleanValue":
                return bool(inner)
            if kind == "nullValue":
                return None
            if kind == "arrayValue":
                return [firestore_to_plain(v) for v in (inner or {}).get("values") or []]
            if kind == "mapValue":
                return {
                    k: firestore_to_plain(v)
                    for k, v in ((inner or {}).get("fields") or {}).items()
                }
    return value


def walk(obj):
    """Yield every node in a JSON tree, depth-first, cycle-safe by id."""
    stack = [obj]
    seen = set()
    while stack:
        node = stack.pop()
        if isinstance(node, (dict, list)):
            if id(node) in seen:
                continue
            seen.add(id(node))
        yield node
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def first_str(d: dict, *keys) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.replace("\xa0", " ").strip()
    return ""


# Wrapper keys whose nested dict carries the name when the entry itself
# doesn't - e.g. Mobalytics assigned skills are {position, skill: {name}}.
WRAPPER_KEYS = ("skill", "item", "node", "aspect")


def _slug_name(el: dict) -> str:
    """Prettify a slug ('harlequin-crest' -> 'Harlequin Crest') as a
    last-resort name. Slugs with digits are ids/coordinates
    ('sorcerer-starting-board-x13-y14'), not names - skip those."""
    slug = el.get("slug")
    if not isinstance(slug, str) or not slug or any(c.isdigit() for c in slug):
        return ""
    return slug.replace("-", " ").replace("_", " ").title()


def named_items(lst: list) -> list:
    """Render a list of strings/dicts as human-readable item lines."""
    items = []
    for el in lst:
        if isinstance(el, str) and el.strip():
            items.append(el.replace("\xa0", " ").strip())
        elif isinstance(el, dict):
            name = first_str(el, *NAME_KEYS)
            if not name:
                for wk in WRAPPER_KEYS:
                    inner = el.get(wk)
                    if isinstance(inner, dict):
                        name = first_str(inner, *NAME_KEYS) or _slug_name(inner)
                        if name:
                            break
            if not name:
                name = _slug_name(el)
            if not name:
                continue
            qty = el.get("points") or el.get("rank") or el.get("quantity")
            slot = first_str(el, "slot", "slotName", "type")
            if slot and slot == slot.lower():
                # slug-style slot ('chest-armor') -> display form
                slot = slot.replace("-", " ").replace("_", " ").title()
            line = f"{slot}: {name}" if slot else name
            if isinstance(qty, (int, float)) and qty:
                line = f"{line} ({int(qty)})"
            items.append(line)
    return items


def _slot_map_items(d: dict) -> list:
    """A {slot: name} mapping (d4builds gear) as 'slot: name' lines. Only
    fires when every value is a string or None - anything nested is a
    structure for walk(), not a slot map."""
    if not all(v is None or isinstance(v, str) for v in d.values()):
        return []
    return [f"{k}: {v}" for k, v in d.items() if isinstance(v, str) and v.strip()]


def sections_from_tree(data) -> list:
    """Scan any JSON tree for recognizable build containers -> sections.

    Key priority is global, not per-node: 'skills' anywhere in the tree
    beats 'skillTree' anywhere else. Node order in a walk is arbitrary, and
    real pages punish relying on it - e.g. Mobalytics attaches a mercenary
    'skillTree' list that would otherwise shadow the build's own skills.
    """
    nodes = [n for n in walk(data) if isinstance(n, dict)]
    found = {}
    for key, title in SECTION_KEYS:
        if title in found:
            continue
        for node in nodes:
            v = node.get(key)
            items = []
            if isinstance(v, list) and v:
                items = named_items(v)
            elif isinstance(v, dict) and v:
                items = _slot_map_items(v)
            if items:
                found[title] = items[:MAX_ITEMS_PER_SECTION]
                break
    return [{"title": t, "items": i} for t, i in found.items()]


def strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def heading_outline(page: str, max_items: int = 40) -> list:
    """h2/h3 headings of an article-style guide as a navigable outline."""
    items = []
    for m in re.finditer(r"<h([23])[^>]*>(.*?)</h\1>", page, re.S | re.I):
        text = strip_tags(m.group(2))
        # Collapse/expand toggles render inside the heading tag on some
        # sites (Maxroll), and ad slots get their own headings - both are
        # chrome, not guide structure.
        text = re.sub(r"(?:Collapse|Expand)$", "", text).strip()
        if not text or len(text) > 120 or text.lower() == "advertisement":
            continue
        items.append(text if m.group(1) == "2" else f"  – {text}")
    return items[:max_items]
