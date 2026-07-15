import asyncio
import json
import time
import uuid
from pathlib import Path

import decky  # type: ignore # provided by Decky Loader at runtime

from grimoire.providers import detect_provider, fetch_metadata

STORE_PATH = Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "builds.json"
SETTINGS_PATH = Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json"


def _load_builds() -> list:
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_builds(builds: list) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(builds, f, indent=2)
    tmp.replace(STORE_PATH)


def _load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    tmp.replace(SETTINGS_PATH)


class Plugin:
    async def add_build(self, url: str, notes: str = "") -> dict:
        """Save a build from a guide URL. Fetches the page title so the
        library entry has a readable name even before provider parsing."""
        url = url.strip()
        provider = detect_provider(url)
        try:
            meta = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, fetch_metadata, url),
                timeout=15,
            )
        except Exception as e:  # offline, bad URL, site down - still save the link
            decky.logger.warning("metadata fetch failed for %s: %s", url, e)
            meta = {"title": url, "sections": []}

        build = {
            "id": uuid.uuid4().hex,
            "name": meta.get("title") or url,
            "provider": provider,
            "source_url": url,
            "notes": notes,
            "sections": meta.get("sections", []),
            "variants": meta.get("variants", []),
            "pinned": False,
            "added_at": int(time.time()),
        }
        builds = _load_builds()
        builds.append(build)
        _save_builds(builds)
        decky.logger.info("added build %s (%s)", build["name"], provider)
        return build

    async def get_builds(self) -> list:
        builds = _load_builds()
        builds.sort(key=lambda b: (not b.get("pinned"), -b.get("added_at", 0)))
        return builds

    async def get_section_order(self) -> list:
        """Preferred section-title order (global: 'Gear first' should hold
        for every build, not be re-set per build)."""
        order = _load_settings().get("section_order", [])
        return order if isinstance(order, list) else []

    async def set_section_order(self, order: list) -> list:
        settings = _load_settings()
        settings["section_order"] = [str(t) for t in order]
        _save_settings(settings)
        return settings["section_order"]

    async def remove_build(self, build_id: str) -> list:
        builds = [b for b in _load_builds() if b["id"] != build_id]
        _save_builds(builds)
        return builds

    async def toggle_pin(self, build_id: str) -> list:
        builds = _load_builds()
        for b in builds:
            if b["id"] == build_id:
                b["pinned"] = not b.get("pinned", False)
            else:
                b["pinned"] = False  # only one pinned build at a time
        _save_builds(builds)
        return builds

    async def set_notes(self, build_id: str, notes: str) -> list:
        builds = _load_builds()
        for b in builds:
            if b["id"] == build_id:
                b["notes"] = notes
        _save_builds(builds)
        return builds

    async def toggle_step(self, build_id: str, key: str) -> list:
        """Check/uncheck one checklist row. Keys are opaque to the backend
        (the frontend encodes variant|section|row); progress is per build."""
        builds = _load_builds()
        for b in builds:
            if b["id"] == build_id:
                progress = b.setdefault("progress", {})
                if key in progress:
                    del progress[key]
                else:
                    progress[key] = True
        _save_builds(builds)
        return builds

    async def clear_progress(self, build_id: str, prefix: str = "") -> list:
        """Reset checklist progress; with a prefix, only that variant's."""
        builds = _load_builds()
        for b in builds:
            if b["id"] == build_id:
                if prefix:
                    b["progress"] = {
                        k: v
                        for k, v in b.get("progress", {}).items()
                        if not k.startswith(prefix)
                    }
                else:
                    b["progress"] = {}
        _save_builds(builds)
        return builds

    async def refresh_build(self, build_id: str) -> list:
        """Re-fetch metadata/sections for a saved build."""
        builds = _load_builds()
        for b in builds:
            if b["id"] == build_id:
                try:
                    meta = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, fetch_metadata, b["source_url"]
                        ),
                        timeout=15,
                    )
                    b["name"] = meta.get("title") or b["name"]
                    b["sections"] = meta.get("sections", b.get("sections", []))
                    b["variants"] = meta.get("variants", b.get("variants", []))
                except Exception as e:
                    decky.logger.warning("refresh failed for %s: %s", b["source_url"], e)
        _save_builds(builds)
        return builds

    async def _main(self):
        decky.logger.info("Grimoire loaded")

    async def _unload(self):
        decky.logger.info("Grimoire unloaded")

    async def _uninstall(self):
        pass
