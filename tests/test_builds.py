import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "py_modules"))
spec = importlib.util.spec_from_file_location("grimoire_backend", ROOT / "main.py")
backend = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, decky=SimpleNamespace(
    DECKY_PLUGIN_SETTINGS_DIR="/unused", logger=Mock()
)):
    spec.loader.exec_module(backend)


class BuildRefreshTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(backend, "STORE_PATH", Path(self.tmp.name) / "builds.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.build = {
            "id": "saved", "name": "Working guide", "source_url": "https://example.com/guide",
            "sections": [{"title": "Skill Gems", "items": ["Contagion"]}],
            "variants": [{"name": "Starter", "sections": []}],
            "notes": "Keep this", "progress": {"step": True}, "pinned": True,
        }
        backend._save_builds([self.build])

    async def test_failed_refresh_preserves_saved_content_and_reports_error(self):
        meta = {"title": "", "sections": [], "variants": [], "error": "Browser verification required"}
        with patch.object(backend, "fetch_metadata", return_value=meta):
            result, = await backend.Plugin().refresh_build("saved")
        for key, value in self.build.items():
            self.assertEqual(result[key], value)
        self.assertEqual(result["fetch_error"], meta["error"])

    async def test_successful_refresh_repairs_old_challenge_entry(self):
        self.build.update(name="Just a moment...", sections=[], variants=[], fetch_error="Old failure")
        backend._save_builds([self.build])
        meta = {"title": "Real PoE2 guide", "sections": [{"title": "Skill Gems", "items": ["Contagion"]}],
                "variants": [], "error": ""}
        with patch.object(backend, "fetch_metadata", return_value=meta):
            result, = await backend.Plugin().refresh_build("saved")
        self.assertEqual(result["name"], meta["title"])
        self.assertEqual(result["sections"], meta["sections"])
        self.assertEqual(result.get("fetch_error", ""), "")
        self.assertEqual(result["notes"], "Keep this")

    async def test_empty_refresh_preserves_saved_sections(self):
        with patch.object(backend, "fetch_metadata", return_value={"title": "Guide", "sections": []}):
            result, = await backend.Plugin().refresh_build("saved")
        self.assertEqual(result["sections"], self.build["sections"])
        self.assertTrue(result["fetch_error"])

    async def test_add_still_saves_link_when_fetch_is_blocked(self):
        with patch.object(backend, "fetch_metadata", return_value={
            "title": "", "sections": [], "variants": [], "error": "Browser verification required"
        }):
            result = await backend.Plugin().add_build("https://example.com/new", notes="Reminder")
        self.assertEqual(result["name"], "https://example.com/new")
        self.assertEqual(result["notes"], "Reminder")
        self.assertTrue(result["fetch_error"])
        self.assertEqual(len(backend._load_builds()), 2)
