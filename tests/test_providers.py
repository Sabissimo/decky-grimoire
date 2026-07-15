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
        self.assertEqual(meta, {"title": "Some Guide", "sections": []})

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


class D4BuildsTests(unittest.TestCase):
    def test_spa_page_falls_through_to_api_endpoint(self):
        api_payload = {
            "name": "HotA Barb",
            "skills": [{"name": "Hammer of the Ancients", "points": 5}],
        }

        def fake_get(url):
            if url.startswith("https://d4builds.gg/api/builds/"):
                return json.dumps(api_payload)
            return "<html><title>D4Builds</title><div id=root></div></html>"

        meta = fetch_metadata(
            "https://d4builds.gg/builds/0f8b2c4d-1234-5678-9abc-def012345678",
            get=fake_get,
        )
        self.assertEqual(meta["title"], "HotA Barb")
        self.assertEqual(
            meta["sections"], [{"title": "Skills", "items": ["Hammer of the Ancients (5)"]}]
        )

    def test_embedded_json_wins_without_api_call(self):
        page = make_next_data_page("HotA Barb", BUILD_TREE)

        def fake_get(url):
            raise AssertionError(f"unexpected second fetch: {url}")

        from grimoire.providers import d4builds

        parsed = d4builds.parse("https://d4builds.gg/builds/abc", page, fake_get)
        self.assertTrue(parsed["sections"])

    def test_all_endpoints_down_falls_back(self):
        def fake_get(url):
            if "api" in url:
                raise OSError("blocked")
            return "<title>D4Builds</title>"

        meta = fetch_metadata("https://d4builds.gg/builds/abcdef12-3456", get=fake_get)
        self.assertEqual(meta["title"], "D4Builds")
        self.assertEqual(meta["sections"], [])


if __name__ == "__main__":
    unittest.main()
