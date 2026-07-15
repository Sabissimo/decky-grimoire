# Grimoire 📖

**Your ARPG build guides, one button press away.**

Grimoire is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader)
plugin for the Steam Deck that keeps your build guides in the Quick Access
overlay. Stuck on which affix to keep, what skill to take at level 32, or how
to path your paragon board? Press <kbd>...</kbd> instead of reaching for your
phone.

Built for **Diablo 4** first (Mobalytics, Maxroll, d4builds.gg links), with a
provider system designed to grow into other ARPGs (Path of Exile 2, Last
Epoch, ...).

## Features (v0.1)

- 📚 **Build library** — paste any guide link once, it's saved on-device
- ★ **Pin your current build** — it sorts to the top of the panel
- 🌐 **Open full guide** — jumps straight to the guide in the built-in browser
  while your game keeps running
- 🔌 **Provider detection** — recognizes Mobalytics, Maxroll and d4builds.gg
  links and fetches a readable title for each entry
- 🧩 **Full build detail, natively in the panel** — skill bar, skill tree
  with ranks, gear per slot, per-item stat priorities, paragon boards with
  glyphs/levels/rotations, charms, mercenaries and class mechanics (spirit
  hall, enchantments). Stat rows carry the markers that matter when gear
  hunting: ✱ for the greater-affix pick, `(masterwork)` for the
  masterwork-crit target, labeled temper and socket rows.
- 🔀 **Build variants** — guides ship several builds (Starter / Endgame /
  Pushing...); a dropdown switches between them, each with its own full
  section set.
- ↕️ **Reorderable sections** — mostly check gear? Move it up once and the
  order sticks, across every build and variant (controller-friendly
  move-up rows, not drag-and-drop).
- 🛡️ **Resilient parsing** — all three providers validated against live
  pages (2026-07): Mobalytics build guides, Maxroll planners & build-guide
  articles, d4builds.gg builds (named metas and shared custom-build uuids).
  Parsers scan embedded JSON / provider APIs for recognizable build
  structures rather than exact paths, so site redesigns degrade to fewer
  sections instead of errors — saving a link always works.
- 📴 **Offline-friendly** — your library is stored locally; adding a link
  while offline still works (title fills in on refresh)

### Validating parsers against real pages

Guide sites redesign freely, so when a provider stops yielding sections,
re-check it from a normal network:

```bash
python3 scripts/validate_live.py https://maxroll.gg/d4/planner/<id>
```

It prints the provider, title and every parsed section. Title but no
sections = that provider's structured parsing needs work; open an issue
with the output.

### Roadmap

- Smoke test on real Steam Deck hardware (virtual keyboard, focus
  navigation, in-game browser hand-off)
- Maxroll game-data ID mapping — bring its planner detail (per-variant
  stats, tempers, greater affixes) up to Mobalytics/d4builds parity
- Leveling checklist mode that remembers which step you're on
- Per-build notes editing in the panel
- More games via the same provider system (PoE2, Last Epoch)
- Decky store submission

## Installation

Grimoire is not in the Decky store yet. The easiest way to try it: grab
`decky-grimoire.zip` from the latest [Actions run](../../actions) and use
Decky's *Developer → Install plugin from zip* (requires developer mode in
Decky settings).

To build from source instead:

```bash
npm install
npm run build
```

Then copy the plugin to your Deck (or develop with
[decky-cli](https://github.com/SteamDeckHomebrew/cli) / VS Code deploy tasks
from the plugin template). The zip layout Decky expects is:

```
decky-grimoire/
├── dist/index.js      # built frontend
├── main.py            # backend entry point
├── py_modules/        # backend modules
├── plugin.json
└── package.json
```

## Development

- **Frontend** — `src/index.tsx`, React via
  [@decky/ui](https://github.com/SteamDeckHomebrew/decky-frontend-lib) +
  [@decky/api](https://github.com/SteamDeckHomebrew/decky-api).
  `npm run watch` rebuilds on change.
- **Backend** — `main.py` + `py_modules/grimoire/`. Pure stdlib Python
  (no vendored dependencies needed). Builds and preferences are stored as
  JSON in the plugin settings directory.
- **Providers** — `py_modules/grimoire/providers/` contains one module per
  guide site. The generic fallback (og:title scrape + open-in-browser)
  always works; structured parsers must degrade to it gracefully.

## License

[BSD-3-Clause](LICENSE)
