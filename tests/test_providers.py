import json
import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "py_modules")
)

from grimoire import parseutil
from grimoire.providers import _extract_title, detect_provider, fetch_metadata


def make_next_data_page(title: str, blob: dict) -> str:
    return (
        f'<html><head><meta property="og:title" content="{title}"/></head><body>'
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(blob)}'
        "</script></body></html>"
    )


BUILD_TREE = {
    "props": {
        "pageProps": {
            "build": {
                "name": "Bone Spear Necromancer",
                "skills": [
                    {"name": "Bone Splinters", "points": 1},
                    {"name": "Bone Spear", "points": 5},
                ],
                "paragonBoards": [
                    {"name": "Starter Board"},
                    {"name": "Bone Graft"},
                ],
                "gear": [
                    {"slot": "Helm", "name": "Heavy Handed Aspect"},
                    {"slot": "Chest", "name": "Aspect of Reanimation"},
                ],
            }
        }
    }
}


class ParseUtilTests(unittest.TestCase):
    def test_sections_from_tree_finds_containers_anywhere(self):
        sections = parseutil.sections_from_tree(BUILD_TREE)
        titles = {s["title"] for s in sections}
        self.assertEqual(titles, {"Skills", "Paragon Boards", "Gear"})
        skills = next(s for s in sections if s["title"] == "Skills")
        self.assertIn("Bone Spear (5)", skills["items"])

    def test_named_items_renders_slot_and_quantity(self):
        items = parseutil.named_items(
            [{"slot": "Helm", "name": "Godslayer Crown"}, {"name": "Ring", "rank": 3}, "plain"]
        )
        self.assertEqual(items, ["Helm: Godslayer Crown", "Ring (3)", "plain"])

    def test_named_items_skips_nameless_dicts(self):
        self.assertEqual(parseutil.named_items([{"id": 42}]), [])

    def test_heading_outline(self):
        page = "<h2>Skills</h2><p>x</p><h3>Rotation</h3><h2>Gear</h2>"
        self.assertEqual(
            parseutil.heading_outline(page), ["Skills", "  – Rotation", "Gear"]
        )

    def test_walk_is_cycle_safe(self):
        a = {}
        a["self"] = a
        self.assertTrue(any(n is a for n in parseutil.walk(a)))

    def test_extract_window_json(self):
        page = (
            "<script>window.__PRELOADED_STATE__ = "
            '{"a": [1, 2], "t": "x"};</script>'
            "<script>window.notJson = function(){};</script>"
        )
        blobs = parseutil.extract_window_json(page)
        self.assertEqual(blobs, [{"a": [1, 2], "t": "x"}])

    def test_named_items_unwraps_wrapper_dicts(self):
        # Mobalytics assigned skills: {position, skill: {name}}.
        items = parseutil.named_items(
            [{"position": 1, "skill": {"name": "Ice Armor"}}]
        )
        self.assertEqual(items, ["Ice Armor"])

    def test_named_items_slug_fallback_skips_ids(self):
        items = parseutil.named_items(
            [
                {"slug": "harlequin-crest", "type": "helm"},
                {"slug": "sorcerer-starting-board-x13-y14"},  # coordinate id
            ]
        )
        self.assertEqual(items, ["Helm: Harlequin Crest"])

    def test_section_key_priority_is_global(self):
        # A mercenary 'skillTree' list must not shadow the build's own
        # 'skills' list, whatever order walk() visits them in.
        tree = {
            "mercenary": {"skillTree": [{"name": "Wire Trap"}]},
            "build": {"skills": [{"name": "Whirlwind"}]},
        }
        sections = parseutil.sections_from_tree(tree)
        skills = next(s for s in sections if s["title"] == "Skills")
        self.assertEqual(skills["items"], ["Whirlwind"])

    def test_slot_map_dict_renders_filled_slots(self):
        sections = parseutil.sections_from_tree(
            {"gear": {"Helm": "Godslayer Crown", "Offhand": None, "deep": None}}
        )
        self.assertEqual(
            sections, [{"title": "Gear", "items": ["Helm: Godslayer Crown"]}]
        )

    def test_slot_map_rejects_nested_structures(self):
        sections = parseutil.sections_from_tree({"gear": {"Helm": {"id": 1}}})
        self.assertEqual(sections, [])

    def test_firestore_to_plain(self):
        doc = json.loads(
            make_firestore_doc(
                {"name": "X", "n": 3, "ok": True, "none": None,
                 "lst": ["a", 2], "map": {"k": "v"}}
            )
        )
        self.assertEqual(
            parseutil.firestore_to_plain(doc),
            {"name": "X", "n": 3, "ok": True, "none": None,
             "lst": ["a", 2], "map": {"k": "v"}},
        )

    def test_heading_outline_strips_chrome(self):
        page = "<h2>EquipmentCollapse</h2><h2>Advertisement</h2><h2>Paragon</h2>"
        self.assertEqual(
            parseutil.heading_outline(page), ["Equipment", "Paragon"]
        )


class DispatchTests(unittest.TestCase):
    def test_detect_provider(self):
        self.assertEqual(detect_provider("https://mobalytics.gg/diablo-4/x"), "mobalytics")
        self.assertEqual(detect_provider("https://maxroll.gg/d4/planner/a"), "maxroll")
        self.assertEqual(detect_provider("https://d4builds.gg/builds/u"), "d4builds")
        self.assertEqual(detect_provider("https://example.com"), "web")

    def test_extract_title_variants(self):
        self.assertEqual(
            _extract_title('<meta property="og:title" content="A &amp; B">'), "A & B"
        )
        self.assertEqual(_extract_title("<title>Fallback</title>"), "Fallback")
        self.assertEqual(_extract_title("<p>nothing</p>"), "")

    def test_generic_url_gets_title_only(self):
        meta = fetch_metadata(
            "https://example.com/guide", get=lambda u: "<title>Some Guide</title>"
        )
        self.assertEqual(
            meta, {"title": "Some Guide", "sections": [], "variants": []}
        )

    def test_parser_exception_falls_back_to_generic(self):
        # A mobalytics URL whose page makes the structured path blow up
        # (get raises on any SECOND fetch a parser might attempt is not
        # enough - so hand it a page with a malformed JSON blob instead).
        page = (
            '<title>Safe Title</title>'
            '<script id="__NEXT_DATA__" type="application/json">{broken'
            "</script>"
        )
        meta = fetch_metadata("https://mobalytics.gg/diablo-4/b", get=lambda u: page)
        self.assertEqual(meta["title"], "Safe Title")
        self.assertEqual(meta["sections"], [])


class MobalyticsTests(unittest.TestCase):
    def test_next_data_build_page(self):
        page = make_next_data_page("Bone Spear Necro Build", BUILD_TREE)
        meta = fetch_metadata("https://mobalytics.gg/diablo-4/builds/necromancer/bone-spear", get=lambda u: page)
        self.assertEqual(meta["title"], "Bone Spear Necro Build")
        self.assertEqual(
            {s["title"] for s in meta["sections"]}, {"Skills", "Paragon Boards", "Gear"}
        )

    def test_plain_article_falls_back_to_outline(self):
        page = "<title>Guide</title><h2>Leveling</h2><h2>Endgame</h2>"
        meta = fetch_metadata("https://mobalytics.gg/diablo-4/guides/x", get=lambda u: page)
        self.assertEqual(
            meta["sections"], [{"title": "Guide outline", "items": ["Leveling", "Endgame"]}]
        )

    def test_preloaded_state_page_document_beats_sidebar_blobs(self):
        # Live shape (2026-07): build data in window.__PRELOADED_STATE__
        # under userGeneratedDocumentBySlug; other embeds carry OTHER
        # builds' data and must lose to the page's own document.
        variant = {
            "assignedSkills": {
                "skills": [
                    {"position": 2, "skill": {"name": "Ball Lightning"}},
                    {"position": 1, "skill": {"name": "Ice Armor"}},
                ],
                "enchantments": [{"name": "Chain Lightning"}],
                "spiritGuardians": {"primaryId": "eagle"},
            },
            "skillTree": {
                "skills": [
                    {"actionType": "ACTIVATE", "skill": {"slug": "ball-lightning"}},
                    {"actionType": "ACTIVATE", "skill": {"slug": "ball-lightning"}},
                    {"actionType": "ACTIVATE", "skill": {"slug": "ball-lightning-static"}},
                ]
            },
            "genericBuilder": {
                "slots": [
                    {
                        "gameSlotSlug": "helm",
                        "gameEntity": {
                            "title": "Harlequin Crest",
                            "type": "uniqueItems",
                            "modifiers": {
                                "gearStats": [
                                    {"id": "maximum-life", "isGreater": False,
                                     "isMasterwork": False},
                                    {"id": "cooldown-reduction", "isGreater": True,
                                     "isMasterwork": True},
                                ],
                                "socketStats": [
                                    {"slug": "emerald", "type": "gems"},
                                    {"slug": "emerald", "type": "gems"},
                                ],
                                "temperingStats": [
                                    {"id": "worldly-endurance-maximum-life",
                                     "isGreater": False, "isMasterwork": False},
                                ],
                            },
                        },
                    },
                    {
                        "gameSlotSlug": "season-12-charm-1",
                        "gameEntity": {"title": "Some Charm", "type": "charms"},
                    },
                ]
            },
            "paragon": {
                "boards": [
                    {
                        "board": {"slug": "sorcerer-starter-board"},
                        "glyph": {"slug": "sorcerer-elementalist"},
                        "glyphLevel": 100,
                        "rotation": 990,
                    }
                ],
                "nodes": [
                    {"slug": "sorcerer-starter-board-x1-y1"},
                    {"slug": "sorcerer-starter-board-x1-y2"},
                ],
                "priorityList": [
                    {"slug": "sorcerer-elementalist"},
                    {"slug": "sorcerer-destruction"},
                ],
            },
            "mercenary": {
                "primaryMercenary": {"slug": "raheir-the-shieldbearer"},
                # A mercenary skillTree list must never shadow build skills.
                "skillTree": [{"actionType": "ACTIVATE", "skill": {"slug": "wire-trap"}}],
            },
            "talismansPriorityList": [
                {"slug": "beru-of-the-multitude"},
                {"slug": "new-seal"},  # empty-slot placeholder, dropped
            ],
        }
        variant["id"] = "5"
        pushing = {
            "id": "2",
            "assignedSkills": {
                "skills": [{"position": 1, "skill": {"name": "Frozen Orb"}}]
            },
        }
        state = {
            "diablo4State": {
                "queries": [
                    {
                        "game": {
                            "documents": {
                                "userGeneratedDocumentBySlug": {
                                    "data": {
                                        "buildVariants": {"values": [variant, pushing]},
                                        "content": [
                                            {
                                                "data": {
                                                    "childrenVariants": [
                                                        {"id": "5", "title": "Starter"},
                                                        {"id": "2", "title": "Pushing"},
                                                    ]
                                                }
                                            }
                                        ],
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        }
        page = (
            '<meta property="og:title" content="Ball Lightning Sorc"/>'
            '<script type="application/json">'
            + json.dumps({"sidebar": {"skills": [{"name": "Wrong Build Skill"}]}})
            + "</script>"
            "<script>window.__PRELOADED_STATE__ = " + json.dumps(state) + ";</script>"
        )
        meta = fetch_metadata("https://mobalytics.gg/diablo-4/builds/x", get=lambda u: page)
        by_title = {s["title"]: s["items"] for s in meta["sections"]}
        # Bar skills in slot order, never the sidebar's or mercenary's lists.
        self.assertEqual(by_title["Skills"], ["1 · Ice Armor", "2 · Ball Lightning"])
        self.assertEqual(by_title["Spirit Hall"], ["Primary: Eagle"])
        self.assertEqual(by_title["Enchantments"], ["Chain Lightning"])
        # Ranks from repeated ACTIVATEs; upgrades indent under their skill.
        self.assertEqual(
            by_title["Skill Tree"], ["Ball Lightning (2)", "  – Static"]
        )
        # Charm slots stay out of gear; uniques are flagged.
        self.assertEqual(by_title["Gear"], ["Helm: Harlequin Crest (Unique)"])
        # Slot-first headers; ✱ marks the greater-affix pick (the site's
        # asterisk), masterwork target labeled, sockets aggregate, tempers
        # get a plain label - a temper is a crafting step, not a pick.
        self.assertEqual(
            by_title["Stat Priorities"],
            [
                "Helm · Harlequin Crest",
                "  – Maximum Life",
                "  – ✱ Cooldown Reduction (masterwork)",
                "  – Sockets: Emerald ×2",
                "  – Temper: Worldly Endurance Maximum Life",
            ],
        )
        self.assertEqual(
            by_title["Paragon Boards"],
            [
                "1. Starter Board — Elementalist (100) · 2 nodes · rotate 270°",
                "Glyph order: Elementalist → Destruction",
            ],
        )
        self.assertEqual(by_title["Charms"], ["Beru Of The Multitude"])
        self.assertEqual(by_title["Mercenaries"], ["Primary: Raheir The Shieldbearer"])
        # Every guide variant is offered, named from childrenVariants; the
        # default sections are the first variant's.
        self.assertEqual([v["name"] for v in meta["variants"]], ["Starter", "Pushing"])
        pushing_skills = next(
            s for s in meta["variants"][1]["sections"] if s["title"] == "Skills"
        )
        self.assertEqual(pushing_skills["items"], ["1 · Frozen Orb"])
        self.assertEqual(meta["sections"], meta["variants"][0]["sections"])


class MaxrollTests(unittest.TestCase):
    def test_planner_url_hits_profile_endpoint(self):
        planner_payload = {
            "name": "S14 Blood Surge",
            "data": json.dumps(
                {
                    "profiles": [{"name": "Leveling"}, {"name": "Endgame"}],
                    "skills": [{"name": "Blood Surge", "points": 5}],
                }
            ),
        }

        def fake_get(url):
            if "planners.maxroll.gg" in url and url.endswith("/abc123"):
                return json.dumps(planner_payload)
            return "<title>Maxroll Planner</title>"

        meta = fetch_metadata("https://maxroll.gg/d4/planner/abc123", get=fake_get)
        self.assertEqual(meta["title"], "S14 Blood Surge")
        variants = next(s for s in meta["sections"] if s["title"] == "Variants")
        self.assertEqual(variants["items"], ["Leveling", "Endgame"])
        skills = next(s for s in meta["sections"] if s["title"] == "Skills")
        self.assertEqual(skills["items"], ["Blood Surge (5)"])

    def test_planner_endpoint_down_falls_back_to_title(self):
        def fake_get(url):
            if "planners.maxroll.gg" in url:
                raise OSError("blocked")
            return "<title>Maxroll Planner</title>"

        meta = fetch_metadata("https://maxroll.gg/d4/planner/abc123", get=fake_get)
        self.assertEqual(meta["title"], "Maxroll Planner")
        self.assertEqual(meta["sections"], [])

    def test_guide_article_outline(self):
        page = (
            "<title>Blood Surge Guide - Maxroll</title>"
            "<h2>Skill Tree</h2><h3>Priority</h3><h2>Paragon</h2>"
        )
        meta = fetch_metadata("https://maxroll.gg/d4/build-guides/blood-surge", get=lambda u: page)
        outline = next(s for s in meta["sections"] if s["title"] == "Guide outline")
        self.assertEqual(outline["items"], ["Skill Tree", "  – Priority", "Paragon"])

    def test_planner_search_metadata_beats_inner_ids(self):
        # Live shape (2026-07): outer payload carries plain names in
        # search_metadata; the inner data's skills are numeric ids.
        payload = {
            "name": "Ball Lightning Sorc",
            "data": json.dumps(
                {"profiles": [{"name": "Endgame"}], "skills": ["517417:49"]}
            ),
            "search_metadata": {
                "skills": ["Ball Lightning", "Teleport"],
                "items": ["Godslayer Crown"],
            },
        }

        def fake_get(url):
            if "planners.maxroll.gg/profiles/load/d4/xyz789" in url:
                return json.dumps(payload)
            return "<title>Maxroll Planner</title>"

        meta = fetch_metadata("https://maxroll.gg/d4/planner/xyz789", get=fake_get)
        self.assertEqual(meta["title"], "Ball Lightning Sorc")
        skills = next(s for s in meta["sections"] if s["title"] == "Skills")
        self.assertEqual(skills["items"], ["Ball Lightning", "Teleport"])
        gear = next(s for s in meta["sections"] if s["title"] == "Gear")
        self.assertEqual(gear["items"], ["Godslayer Crown"])

    def test_planner_profile_not_found_falls_back(self):
        def fake_get(url):
            if "planners.maxroll.gg" in url:
                return json.dumps({"error": "Profile not found"})
            return "<title>Maxroll Planner</title>"

        meta = fetch_metadata("https://maxroll.gg/d4/planner/gone", get=fake_get)
        self.assertEqual(meta["title"], "Maxroll Planner")
        self.assertEqual(meta["sections"], [])

    def test_article_embedded_search_metadata_beats_toc(self):
        blob = {
            "toc": {"items": ["Introduction", "Equipment", "FAQ"]},
            "embed": {
                "search_metadata": {"skills": ["Blood Surge"], "items": ["Kessime's Legacy"]}
            },
        }
        page = (
            "<title>Blood Surge Guide</title>"
            '<script type="application/json">' + json.dumps(blob) + "</script>"
            "<h2>Paragon</h2>"
        )
        meta = fetch_metadata("https://maxroll.gg/d4/build-guides/blood-surge", get=lambda u: page)
        titles = [s["title"] for s in meta["sections"]]
        self.assertEqual(titles, ["Skills", "Gear", "Guide outline"])
        gear = next(s for s in meta["sections"] if s["title"] == "Gear")
        self.assertEqual(gear["items"], ["Kessime's Legacy"])

    def test_page_fetch_failure_still_parses_planner(self):
        # maxroll.gg has been seen tarpitting page fetches while the
        # planner API keeps answering - the page GET must be best-effort.
        payload = {"name": "Resilient Build", "data": json.dumps({"profiles": []})}

        def fake_get(url):
            if "planners.maxroll.gg" in url:
                return json.dumps(payload)
            raise TimeoutError("tarpitted")

        meta = fetch_metadata("https://maxroll.gg/d4/planner/abc123", get=fake_get)
        self.assertEqual(meta["title"], "Resilient Build")


def make_firestore_doc(fields: dict) -> str:
    """A Firestore REST document, typed-value format, from plain values."""

    def enc(v):
        if v is None:
            return {"nullValue": None}
        if isinstance(v, bool):
            return {"booleanValue": v}
        if isinstance(v, int):
            return {"integerValue": str(v)}
        if isinstance(v, float):
            return {"doubleValue": v}
        if isinstance(v, str):
            return {"stringValue": v}
        if isinstance(v, list):
            return {"arrayValue": {"values": [enc(e) for e in v]}}
        if isinstance(v, dict):
            return {"mapValue": {"fields": {k: enc(x) for k, x in v.items()}}}
        raise TypeError(v)

    return json.dumps(
        {
            "name": "projects/d4builds-a3254/databases/(default)/documents/builds/x",
            "fields": {k: enc(v) for k, v in fields.items()},
        }
    )


D4B_UUID = "fb2a2a80-6907-4be4-a7eb-a98785f128b0"
D4B_DOC_FIELDS = {
    "name": "HotA Barb",
    "class": "Barbarian",
    "skills": ["Hammer of the Ancients", "War Cry"],
    "gear": {"Helm": "Tuskhelm of Joritz the Mighty", "Offhand": None},
    "paragon": {
        "boards": [{"name": "Starting Board", "glyph": "Exploit", "glyphLevel": 100}]
    },
    # Legacy 'stats' is all-None next to 'newStats' with the data; the
    # parallel arrays flag greater-affix picks and masterwork targets.
    "stats": {"Helm": [None, None]},
    "newStats": {"Helm": ["Strength", "Cooldown Reduction", "Maximum Life"]},
    "greaterAffixes": {"Helm": [None, 1, None]},
    "masterworking": {"Helm": [0, 0, 1]},
    "temperingStats": {"Helm": ["Total Armor (Worldly Fortune - Defensive)"]},
    "newGems": {"Helm": ["Ruby", "Ruby"]},
    "variantName": "Starter (P200)",
    "variants": [
        {
            "name": "Pushing (P290)",
            "skills": ["Hammer of the Ancients"],
            "gear": {"Helm": "Harlequin Crest"},
        }
    ],
}


class D4BuildsTests(unittest.TestCase):
    def test_uuid_build_loads_from_firestore(self):
        def fake_get(url):
            if url.startswith("https://firestore.googleapis.com/") and D4B_UUID in url:
                return make_firestore_doc(D4B_DOC_FIELDS)
            return "<html><title>D4Builds</title><div id=root></div></html>"

        meta = fetch_metadata(f"https://d4builds.gg/builds/{D4B_UUID}/", get=fake_get)
        self.assertEqual(meta["title"], "HotA Barb (Barbarian)")
        by_title = {s["title"]: s["items"] for s in meta["sections"]}
        self.assertEqual(
            set(by_title),
            {"Skills", "Gear", "Paragon Boards", "Stat Priorities"},
        )
        # Slot-map gear renders filled slots and drops empty ones.
        self.assertEqual(by_title["Gear"], ["Helm: Tuskhelm of Joritz the Mighty"])
        self.assertEqual(
            by_title["Paragon Boards"], ["1. Starting Board — Exploit (100)"]
        )
        # Greater-affix pick marked ✱, masterwork target labeled, tempers
        # and sockets on their own rows.
        self.assertEqual(
            by_title["Stat Priorities"],
            [
                "Helm · Tuskhelm of Joritz the Mighty",
                "  – Strength",
                "  – ✱ Cooldown Reduction",
                "  – Maximum Life (masterwork)",
                "  – Temper: Total Armor (Worldly Fortune - Defensive)",
                "  – Sockets: Ruby ×2",
            ],
        )
        # The base doc is the first variant (named by variantName); the
        # alternates follow with their own sections, and the base sections
        # never leak an alternate's data.
        self.assertEqual(
            [v["name"] for v in meta["variants"]],
            ["Starter (P200)", "Pushing (P290)"],
        )
        alt_gear = next(
            s for s in meta["variants"][1]["sections"] if s["title"] == "Gear"
        )
        self.assertEqual(alt_gear["items"], ["Helm: Harlequin Crest"])
        self.assertEqual(by_title["Gear"], ["Helm: Tuskhelm of Joritz the Mighty"])

    def test_named_build_slug_resolves_via_page_data(self):
        page_data = {
            "result": {
                "pageContext": {"seoId": D4B_UUID, "seoName": "Whirlwind Barbarian Guide"}
            }
        }

        def fake_get(url):
            if url == "https://d4builds.gg/page-data/builds/whirlwind-barb/page-data.json":
                return json.dumps(page_data)
            if url.startswith("https://firestore.googleapis.com/") and D4B_UUID in url:
                return make_firestore_doc(D4B_DOC_FIELDS)
            return "<title>D4Builds</title>"

        meta = fetch_metadata("https://d4builds.gg/builds/whirlwind-barb/", get=fake_get)
        # The Firestore doc's own name wins over the page-data seoName.
        self.assertEqual(meta["title"], "HotA Barb (Barbarian)")
        self.assertTrue(meta["sections"])

    def test_embedded_json_wins_without_api_call(self):
        page = make_next_data_page("HotA Barb", BUILD_TREE)

        def fake_get(url):
            raise AssertionError(f"unexpected second fetch: {url}")

        from grimoire.providers import d4builds

        parsed = d4builds.parse("https://d4builds.gg/builds/abc", page, fake_get)
        self.assertTrue(parsed["sections"])

    def test_all_endpoints_down_falls_back(self):
        def fake_get(url):
            if "firestore" in url or "page-data" in url:
                raise OSError("blocked")
            return "<title>D4Builds</title>"

        meta = fetch_metadata(f"https://d4builds.gg/builds/{D4B_UUID}", get=fake_get)
        self.assertEqual(meta["title"], "D4Builds")
        self.assertEqual(meta["sections"], [])


if __name__ == "__main__":
    unittest.main()
