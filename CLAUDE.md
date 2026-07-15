# Grimoire — Decky Loader plugin

ARPG build guides in the Steam Deck Quick Access overlay. Diablo 4 first
(Mobalytics / Maxroll / d4builds.gg), designed to grow to PoE2 / Last Epoch.

## Commands

```bash
npm install && npm run build        # build frontend -> dist/index.js
npm run watch                       # rebuild on change
python3 -m unittest discover -s tests -v    # backend tests (stdlib only, no deps)
python3 scripts/validate_live.py <guide-url> # parse a REAL guide page (needs open network)
```

CI (`.github/workflows/build.yml`) runs tests + build on every push and
uploads a sideload-ready `decky-grimoire.zip` artifact.

## Architecture

- `src/index.tsx` — entire frontend (React via `@decky/ui` + `@decky/api`).
  Views: library list / add-from-URL / build detail. Renders whatever
  `sections` the backend returns, generically: `[{title, items: [str]}]`.
  New parser capabilities need NO frontend changes.
- `main.py` — Decky backend entry point. Thin: build CRUD over a JSON file
  in `decky.DECKY_PLUGIN_SETTINGS_DIR`, network calls in an executor with a
  15s cap. `decky` module exists only at runtime on the Deck.
- `py_modules/grimoire/parseutil.py` — structure-scanning core. Extracts
  embedded JSON (`__NEXT_DATA__`, ld+json) and SCANS it for recognizable
  containers (see `SECTION_KEYS`) instead of exact JSON paths.
- `py_modules/grimoire/providers/` — one module per guide site, each
  `parse(url, page, http_get) -> {title, sections}`. Dispatcher in
  `__init__.py`.

## Invariants — do not break

1. **Parsers are best-effort by contract.** Any parser exception or empty
   result must fall back to generic title + open-in-browser. A site
   redesign may never break saving a link. The dispatcher's try/except
   enforces this; keep it.
2. **Backend stays stdlib-only.** Decky plugins must vendor Python deps;
   we avoid the problem entirely (urllib, json, re).
3. **Sections format is the frontend contract**: `[{title: str, items:
   [str]}]`. Extend by adding sections, not by changing the shape.
4. **Tests must run anywhere** — stdlib unittest, no network, fixtures only.

## Current state / next steps

- **All three providers live-validated 2026-07-15** (real URLs, open
  network) and parsing structured sections:
  - Mobalytics: build data is in `window.__PRELOADED_STATE__` (not
    __NEXT_DATA__) under `userGeneratedDocumentBySlug`. Sidebar embeds
    carry OTHER builds' data — parsers must anchor to the page's own
    document, never trust a whole-blob scan alone.
  - Maxroll planner: `https://planners.maxroll.gg/profiles/load/{game}/{pid}`
    (no auth, no special headers; 404 + `{"error": "Profile not found"}`
    for dead ids). The outer payload's `search_metadata` has plain-language
    skill/item names — no game-data ID mapping needed. Guide articles embed
    the same planner payloads; anchor on `search_metadata` there too.
  - d4builds: build docs live in public Firestore (project `d4builds-a3254`,
    collection `builds`, REST API, no key). Named-build slugs resolve to
    uuids via Gatsby `page-data/builds/<slug>/page-data.json` →
    `pageContext.seoId`. `parseutil.firestore_to_plain` decodes typed fields.
  - maxroll.gg tarpits repeat page fetches (read stalls) while the planner
    API keeps answering — that's why `fetch_metadata` treats the page GET
    itself as best-effort. Don't "fix" that back.
- Not yet tested on real hardware. Install path: Decky settings →
  developer mode → Install plugin from zip (CI artifact), or deploy via
  decky-cli. Frontend concerns to verify on the Deck: virtual keyboard
  with `TextField`, focus navigation, `Navigation.NavigateToExternalWeb`
  behaviour from Quick Access while a game runs.
- Roadmap (in rough order): on-Deck smoke test → per-build notes editing
  in the panel → leveling checklist mode (remember current step) → more
  games (PoE2 / Last Epoch providers) → Decky store submission (repo is
  BSD-3-Clause, store requires OSI license — done).

## Conventions

- Frontend: TypeScript, 2-space indent; JSX factory is `window.SP_REACT`
  (configured in tsconfig — don't import React directly).
- Backend: PEP 8, double quotes, no type-checking dependency on `decky`
  (`# type: ignore` at the import).
- Keep provider quirks documented in each provider module's docstring.
