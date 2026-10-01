"""Reduced live payload from chaos-dot-lich-starter-deadrabbit, 2026-10-01."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py_modules"))
from grimoire.providers import fetch_metadata, http_get

URL = "https://mobalytics.gg/poe-2/builds/chaos-dot-lich-starter-deadrabbit"
CHALLENGE = '<html><title>Just a moment...</title><script src="/cdn-cgi/challenge-platform/x"></script></html>'


class Poe2Tests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(
            (Path(__file__).parent / "fixtures/mobalytics_poe2.json").read_text()
        )

    def parse(self):
        # A sidebar's D4 skills must never leak into this PoE2 guide.
        blob = {"sidebar": {"skills": ["Wrong build"]}, **self.document}
        page = "<script>window.__PRELOADED_STATE__ = " + json.dumps(blob) + ";</script>"
        return fetch_metadata(URL, get=lambda _: page)

    def test_real_poe2_variants(self):
        meta = self.parse()
        self.assertIn("ED Contagion Lich", meta["title"])
        self.assertEqual([v["name"] for v in meta["variants"]],
                         ["ACT 1", "ENDGAME (LOW LIFE)"])
        self.assertEqual(meta["sections"], meta["variants"][0]["sections"])
        sections = {s["title"]: s["items"] for s in meta["sections"]}
        self.assertIn("Contagion", sections["Skill Gems"])
        self.assertIn("  – Magnified Area I", sections["Skill Gems"])
        self.assertIn("Helmet: Beaded Circlet", sections["Gear"])
        self.assertIn("Main Hand (Set 1): Withered Wand", sections["Gear"])
        self.assertIn("  – +60 to maximum Life", sections["Stat Priorities"])
        self.assertIn("Entropy", sections["Passive Tree"])
        self.assertIn("Flask 1: Greater Life Flask", sections["Flasks"])
        self.assertIn("Charm 1: Thawing Charm", sections["Charms"])
        self.assertIn("30% increased Charm Charges gained", str(sections["Quest Rewards"]))
        endgame = {s["title"]: s["items"] for s in meta["variants"][1]["sections"]}
        self.assertIn("Helmet: Atziri's Disdain (Unique)", endgame["Gear"])
        self.assertIn("Soulless Form", endgame["Ascendancy"])
        self.assertNotIn("Wrong build", str(meta))

    def test_empty_document_does_not_use_sidebar_build(self):
        self.document["userGeneratedDocumentBySlug"]["data"]["data"]["buildVariants"]["values"] = []
        self.assertEqual(self.parse()["sections"], [])

    def test_missing_gem_names_do_not_erase_other_sections(self):
        variants = self.document["userGeneratedDocumentBySlug"]["data"]["data"]["buildVariants"]["values"]
        variants[0]["skillGems"]["priorityGems"] = None
        meta = self.parse()
        sections = {s["title"]: s["items"] for s in meta["sections"]}
        self.assertIn("  – Gem name unavailable; see full guide", sections["Skill Gems"])
        self.assertIn("Helmet: Beaded Circlet", sections["Gear"])

    def test_profile_document_uses_its_own_variants(self):
        self.document["userGeneratedDocumentBySlugifiedName"] = self.document.pop("userGeneratedDocumentBySlug")
        self.assertEqual(len(self.parse()["variants"]), 2)

    def test_blocked_page_recovers_from_public_guide_endpoint(self):
        def get(url, **kwargs):
            if url == URL:
                return CHALLENGE
            parts = urlsplit(url)
            self.assertEqual(parts.path, "/api/poe-2/v1/graphql/query")
            params = parse_qs(parts.query)
            self.assertEqual(json.loads(params["variables"][0])["input"],
                             {"slug": "chaos-dot-lich-starter-deadrabbit", "type": "builds"})
            self.assertEqual(kwargs["headers"]["Apollo-Require-Preflight"], "true")
            return json.dumps({"data": {"game": {"documents": self.document}}})

        meta = fetch_metadata(URL, get=get)
        self.assertIn("ED Contagion Lich", meta["title"])
        self.assertEqual(len(meta["variants"]), 2)
        self.assertEqual(meta["error"], "")

    def test_public_endpoint_failure_keeps_fetch_error(self):
        def get(url, **kwargs):
            return CHALLENGE if url == URL else json.dumps({"errors": [{"message": "Unavailable"}]})
        meta = fetch_metadata(URL, get=get)
        self.assertEqual(meta["sections"], [])
        self.assertIn("verification", meta["error"])


class ChallengeTests(unittest.TestCase):
    def test_challenge_is_not_a_guide(self):
        meta = fetch_metadata(URL, get=lambda _: CHALLENGE)
        self.assertEqual(meta["title"], "")
        self.assertEqual(meta["sections"], [])
        self.assertIn("verification", meta["error"].lower())

    @patch("grimoire.providers._curl_get", return_value="<title>Real guide</title>")
    @patch("grimoire.providers.urllib.request.urlopen")
    def test_http_200_challenge_retries_with_curl(self, urlopen, curl):
        urlopen.return_value.__enter__.return_value.read.return_value = CHALLENGE.encode()
        self.assertEqual(http_get(URL), "<title>Real guide</title>")
        curl.assert_called_once()

    @patch("grimoire.providers._curl_get", return_value=CHALLENGE)
    @patch("grimoire.providers.urllib.request.urlopen")
    def test_curl_challenge_after_403_is_reported(self, urlopen, curl):
        error = urllib.error.HTTPError(URL, 403, "Forbidden", {}, None)
        self.addCleanup(error.close)
        urlopen.side_effect = error
        with self.assertRaisesRegex(OSError, "verification"):
            http_get(URL)
