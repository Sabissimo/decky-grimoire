"""PoE2's Mobalytics buildVariants schema, verified 2026-10-01.

Unlike D4, equipment uses commonItem records and two weapon sets. Linked
gems often carry only gemSlug; priorityGems supplies their display names.
Passive priorityList contains named notables, not the full tree path.
Never prettify internal ids into invented gem/item/passive names.

Featured guides also expose this data via the same unauthenticated GraphQL
query used by the website. It can answer while the HTML page is challenged.
Only request the pasted guide, and only fall back when its document is absent.
"""
import json
import re
from urllib.parse import unquote, urlencode, urlsplit

from grimoire.parseutil import first_str, strip_tags


def fetch_document(url, http_get):
    match = re.fullmatch(r"/poe-2/builds/([^/]+)/?", urlsplit(url).path)
    if not match:
        return None
    # These selections mirror the page's public Poe2UgFeaturedDocumentQuery,
    # restricted to the fields rendered in Grimoire. No account is required.
    slots = " ".join(
        slot + " { commonItem { ...Item } }"
        for slot in ("amulet", "belt", "body", "boots", "flask1", "flask2",
                     "charm1", "charm2", "charm3", "gloves", "helmet",
                     "leftRing", "rightRing", "extraRing")
    )
    weapons = " ".join(
        slot + " { set1 { commonItem { ...Item } } set2 { commonItem { ...Item } } }"
        for slot in ("mainHand", "offHand")
    )
    query = """
      query GrimoirePoe2Guide($input: Poe2UserGeneratedDocumentInputBySlug!) {
        game: poe2 { documents { userGeneratedDocumentBySlug(input: $input) {
          error data {
            data {
              name
              questRewards { quests { quest { name act area } reward { bakedDescription } } }
              buildVariants { values {
                id equipment { SLOTS WEAPONS }
                skillGems {
                  gemRequirements { str dex int }
                  gems { activeSkill { name gemSlug level } weaponSet subSkills { gemSlug } }
                  priorityGems { gemSlug name }
                }
                passiveTree {
                  mainTree { priorityList { name } }
                  ascendancyTree { priorityList { name } }
                }
              } }
            }
            content: contentV2 {
              ... on NgfDocumentCmWidgetContentVariantsV1 {
                data { childrenVariants { id title } }
              }
            }
          }
        } } }
      }
      fragment Item on Poe2DocumentUgWidgetEquipmentCommonV1 {
        name isUnique explicitDescriptions { description mustHave }
      }
    """.replace("SLOTS", slots).replace("WEAPONS", weapons)
    endpoint = "https://mobalytics.gg/api/poe-2/v1/graphql/query?" + urlencode({
        "query": " ".join(query.split()),
        "variables": json.dumps({"input": {"slug": unquote(match[1]), "type": "builds"}}),
    })
    payload = json.loads(http_get(endpoint, headers={"Apollo-Require-Preflight": "true"}))
    if not isinstance(payload, dict) or payload.get("errors"):
        raise ValueError("Mobalytics could not return this guide's data")
    documents = _dict(_dict(_dict(payload.get("data")).get("game")).get("documents"))
    document = _dict(documents.get("userGeneratedDocumentBySlug"))
    if document.get("error") or not document.get("data"):
        raise ValueError("Mobalytics could not return this guide's data")
    return document


def _dict(value):
    return value if isinstance(value, dict) else {}


def _records(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _label(slot):
    return re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", slot).title()


def _gems(data):
    names = {
        gem["gemSlug"]: gem["name"]
        for gem in _records(data.get("priorityGems"))
        if first_str(gem, "gemSlug") and first_str(gem, "name")
    }
    rows = []
    for gem in _records(data.get("gems")):
        active = _dict(gem.get("activeSkill"))
        name = first_str(active, "name") or names.get(active.get("gemSlug"))
        if not name:
            continue
        level = active.get("level")
        if isinstance(level, (int, float)) and level > 0:
            name += f" (Level {level})"
        if gem.get("weaponSet") in ("set1", "set2"):
            name += f" ({_label(gem['weaponSet'])})"
        rows.append(name)
        for support in _records(gem.get("subSkills")):
            label = first_str(support, "name") or names.get(support.get("gemSlug"))
            # Preserve the presence of an unresolved link without exposing ids.
            rows.append(f"  – {label or 'Gem name unavailable; see full guide'}")
    return rows


def _equipment(equipment):
    """Yield slot labels and item wrappers, including both weapon sets."""
    for slot, item in equipment.items():
        if not isinstance(item, dict):
            continue
        if slot in ("mainHand", "offHand"):
            for weapon_set in ("set1", "set2"):
                wrapper = item.get(weapon_set)
                if isinstance(wrapper, dict):
                    yield f"{_label(slot)} ({_label(weapon_set)})", wrapper, "Gear"
        else:
            section = "Flasks" if slot.startswith("flask") else (
                "Charms" if slot.startswith("charm") else "Gear"
            )
            yield _label(slot), item, section


def _item_stats(item):
    rows = []
    for stat in _records(item.get("explicitDescriptions")):
        description = first_str(stat, "description")
        if description:
            suffix = " (required)" if stat.get("mustHave") else ""
            rows.append(f"  – {strip_tags(description)}{suffix}")
    return rows


def _tree(tree):
    return [first_str(node, "name") for node in _records(tree.get("priorityList"))
            if first_str(node, "name")]


def quest_rewards(data):
    rows = []
    for entry in _records(_dict(data).get("quests")):
        quest = _dict(entry.get("quest"))
        name = first_str(quest, "name")
        if not name:
            continue
        location = " · ".join(filter(None, (first_str(quest, "act"),
                                             first_str(quest, "area"))))
        rows.append(f"{location}: {name}" if location else name)
        reward = _dict(entry.get("reward"))
        description = first_str(reward, "bakedDescription")
        if description:
            rows.append(f"  – {strip_tags(description)}")
    return rows


def variant_sections(variant, quests):
    sections = []

    def add(title, rows):
        if rows:
            sections.append({"title": title, "items": rows})

    gems = _dict(variant.get("skillGems"))
    add("Skill Gems", _gems(gems))
    requirements = _dict(gems.get("gemRequirements"))
    add("Gem Requirements", [
        f"{label}: {requirements[key]}"
        for key, label in (("str", "Strength"), ("dex", "Dexterity"), ("int", "Intelligence"))
        if isinstance(requirements.get(key), (int, float)) and requirements[key] > 0
    ])
    gear = {"Gear": [], "Flasks": [], "Charms": []}
    stats = []
    for slot, wrapper, section in _equipment(_dict(variant.get("equipment"))):
        item = _dict(wrapper.get("commonItem"))
        name = first_str(item, "name")
        if not name:
            continue
        suffix = " (Unique)" if item.get("isUnique") else ""
        gear[section].append(f"{slot}: {name}{suffix}")
        rows = _item_stats(item)
        if rows:
            stats.extend([f"{slot} · {name}", *rows])
    for title, rows in gear.items():
        add(title, rows)
    add("Stat Priorities", stats)
    passive = _dict(variant.get("passiveTree"))
    for key, title in (("mainTree", "Passive Tree"),
                       ("set1Tree", "Passive Tree (Set 1)"),
                       ("set2Tree", "Passive Tree (Set 2)"),
                       ("ascendancyTree", "Ascendancy")):
        add(title, _tree(_dict(passive.get(key))))
    add("Quest Rewards", quests)
    return sections
