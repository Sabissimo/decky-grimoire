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
uploads a sideload-ready `decky-grimoire.zip` artifact. Pushing a `v*` tag
additionally attaches the zip to a GitHub release with generated notes
(same flow as the user's other decky-* repos). Release = tag `vX.Y.Z`
matching package.json's version, then `git push origin vX.Y.Z`.

## Architecture

- `src/index.tsx` — entire frontend (React via `@decky/ui` + `@decky/api`).
  Views: library list / add-from-URL / build detail. Renders backend
  `sections` generically, plus: a variant dropdown when `variants` has >1
  entry, hierarchy styling for "  – " sub-rows (leading spaces collapse in
  HTML, so headers get weight 600 and sub-rows indentation), and a
  reorder mode (move-up rows — controller-friendly, deliberately not
  drag-and-drop) persisting a global section-title order.
- `main.py` — Decky backend entry point. Thin: build CRUD over
  `builds.json` and preferences over `settings.json` (both in
  `decky.DECKY_PLUGIN_SETTINGS_DIR`), network calls in an executor with a
  15s cap. `decky` module exists only at runtime on the Deck.
- `py_modules/grimoire/parseutil.py` — structure-scanning core. Extracts
  embedded JSON (`__NEXT_DATA__`, ld+json, `window.*=` assignments) and
  SCANS it for recognizable containers (see `SECTION_KEYS`) instead of
  exact JSON paths. Also `firestore_to_plain` for Firestore REST docs.
- `py_modules/grimoire/providers/` — one module per guide site, each
  `parse(url, page, http_get) -> {title, sections, variants}`. Dispatcher
  in `__init__.py`.

## Invariants — do not break

1. **Parsers are best-effort by contract.** Any parser exception or empty
   result must fall back to generic title + open-in-browser. A site
   redesign may never break saving a link. The dispatcher's try/except
   enforces this; keep it.
2. **Backend stays stdlib-only.** Decky plugins must vendor Python deps;
   we avoid the problem entirely (urllib, json, re). The one system
   dependency is the curl fallback in `http_get` — `/usr/bin/curl` ships
   with SteamOS and is only used when Cloudflare bot-blocks the embedded
   Python (see Deck-runtime facts below).
3. **Sections format is the frontend contract**: `[{title: str, items:
   [str]}]`, optionally wrapped in `variants: [{name, sections}]` with
   `sections` = the default variant's (so older entries keep working).
   Item-string conventions the frontend styles: `"  – "` prefix = sub-row
   of the header above; `✱` = greater-affix pick; `(masterwork)` =
   masterwork-crit target; `Temper:` / `Sockets:` labeled rows. Extend by
   adding sections, not by changing the shape.
4. **Tests must run anywhere** — stdlib unittest, no network, fixtures only.

## Current state / next steps

- **All three providers live-validated 2026-07-15** (real URLs, open
  network). Mobalytics and d4builds parse FULL builds (skill bar, ranked
  skill tree, gear, stat priorities with greater-affix ✱ / masterwork /
  temper / socket markers, paragon boards with glyphs+rotations, charms,
  mercenaries) across every guide variant. Hard-won site facts:
  - Mobalytics: build data is in `window.__PRELOADED_STATE__` (not
    __NEXT_DATA__) under `userGeneratedDocumentBySlug`. Sidebar embeds
    carry OTHER builds' data — parsers must anchor to the page's own
    document, never trust a whole-blob scan alone. Per-stat
    isGreater/isMasterwork flags live ONLY in genericBuilder's
    `gameEntity.modifiers` (the equipmentPriorityList modifiers lack
    them). Variant names come from `childrenVariants` descriptors.
  - Maxroll planner: `https://planners.maxroll.gg/profiles/load/{game}/{pid}`
    (no auth, no special headers; 404 + `{"error": "Profile not found"}`
    for dead ids). Full detail comes from the public game-data file
    (`assets-ng.maxroll.gg/d4-tools/game/data.min.json`, ~12 MB, fetched
    once per plugin process): affix labels are attributeDescriptions
    templates stripped of placeholders; aspects are magicType-1 affixes
    whose `prefix` is the aspect short name; profile `class` is an index
    into `classes`; skill-tree node ids collide ACROSS classes — never
    merge trees; runes/gems resolve through `items`. Each planner profile
    is a variant. If the game-data fetch fails, `search_metadata` (plain
    name lists) is the fallback. Guide articles embed the same planner
    payloads; anchor on `search_metadata` there. main.py's fetch timeout
    is 45s because of that first 12 MB download.
  - d4builds: build docs live in public Firestore (project `d4builds-a3254`,
    collection `builds`, REST API, no key). Named-build slugs resolve to
    uuids via Gatsby `page-data/builds/<slug>/page-data.json` →
    `pageContext.seoId`. Parallel per-slot arrays: `newStats` +
    `greaterAffixes` + `masterworking` (legacy `stats`/`gems` twins are
    all-None — skip them). The base doc is itself a variant (name =
    `variantName`); alternates in `variants`.
  - maxroll.gg tarpits repeat page fetches (read stalls) while the planner
    API keeps answering — that's why `fetch_metadata` treats the page GET
    itself as best-effort. Don't "fix" that back.
  - Re-deriving a broken provider's shapes: fetch the page and inspect
    embedded JSON first; if the data loads client-side, use a browser with
    a fetch/XHR monkeypatch to capture requests — plain network listings
    miss Firestore WebChannel traffic.
- **Live-debugged on real hardware 2026-07-15** (SSH into the user's
  Deck, log tail + scp iterate). Verified end-to-end: add a Mobalytics
  link → full parse (all sections, all variants). Deck-runtime facts —
  do not regress:
  - Cloudflare TLS-fingerprints Decky's embedded Python → 403 on guide
    pages regardless of headers. `http_get` falls back to system curl on
    403/429/503, with the loader's pyinstaller `LD_LIBRARY_PATH`
    scrubbed (it poisons curl with an incompatible libssl → exit 1,
    "OPENSSL_x_not found") and the absolute `/usr/bin/curl` path (the
    plugin env has NO PATH; `which` finds nothing).
  - Decky's embedded Python also can't verify HTTPS at all without the
    explicit CA-bundle context (`_SSL_CONTEXT`); keep `context=` on
    every urlopen.
  - Closing a dropdown's full-screen menu REMOUNTS the QAM content and
    wipes useState — the open build and per-build variant picks live at
    module scope (`rememberedBuildId`, `rememberedVariants`). Any new
    selection state must do the same.
  - The virtual keyboard can commit text without firing onChange — never
    gate a button on text state (the Save button stays enabled and an
    empty field explains itself in a toast).
  - `fetch_metadata` returns an `error` field that add/refresh log —
    silent degradation made every real-Deck failure invisible; keep it.
- Roadmap: more games (PoE2 / Last Epoch providers — SHELVED until
  asked) → Decky store submission (repo is BSD-3-Clause, store requires
  OSI license — done). Done and shipped: Maxroll planner detail
  parity, per-build notes editing, leveling checklist, section reordering,
  build variants.

## Conventions

- Frontend: TypeScript, 2-space indent; JSX factory is `window.SP_REACT`
  (configured in tsconfig — don't import React directly).
- Backend: PEP 8, double quotes, no type-checking dependency on `decky`
  (`# type: ignore` at the import).
- Keep provider quirks documented in each provider module's docstring.
