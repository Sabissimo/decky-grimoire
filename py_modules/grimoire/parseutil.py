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


def extract_json_scripts(page: str) -> list:
    """Every application/json and ld+json script blob on the page."""
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
    return out


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
            return v.strip()
    return ""


def named_items(lst: list) -> list:
    """Render a list of strings/dicts as human-readable item lines."""
    items = []
    for el in lst:
        if isinstance(el, str) and el.strip():
            items.append(el.strip())
        elif isinstance(el, dict):
            name = first_str(el, *NAME_KEYS)
            if not name:
                continue
            qty = el.get("points") or el.get("rank") or el.get("quantity")
            slot = first_str(el, "slot", "slotName", "type")
            line = f"{slot}: {name}" if slot else name
            if isinstance(qty, (int, float)) and qty:
                line = f"{line} ({int(qty)})"
            items.append(line)
    return items


def sections_from_tree(data) -> list:
    """Scan any JSON tree for recognizable build containers -> sections."""
    found = {}
    for node in walk(data):
        if not isinstance(node, dict):
            continue
        for key, title in SECTION_KEYS:
            if title in found:
                continue
            v = node.get(key)
            if isinstance(v, list) and v:
                items = named_items(v)
                if items:
                    found[title] = items[:MAX_ITEMS_PER_SECTION]
    return [{"title": t, "items": i} for t, i in found.items()]


def strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def heading_outline(page: str, max_items: int = 40) -> list:
    """h2/h3 headings of an article-style guide as a navigable outline."""
    items = []
    for m in re.finditer(r"<h([23])[^>]*>(.*?)</h\1>", page, re.S | re.I):
        text = strip_tags(m.group(2))
        if not text or len(text) > 120:
            continue
        items.append(text if m.group(1) == "2" else f"  – {text}")
    return items[:max_items]
