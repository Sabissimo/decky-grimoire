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
- 📴 **Offline-friendly** — your library is stored locally; adding a link
  while offline still works (title fills in on refresh)

### Roadmap

- Structured build parsing per provider: skill order, gear affix cheat-sheet
  and paragon steps rendered natively in the panel (see
  `py_modules/grimoire/providers/*.py` stubs)
- Leveling checklist mode that remembers which step you're on
- Per-build notes editing in the panel
- More games via the same provider system

## Installation

Grimoire is not in the Decky store yet. To try it from source:

```bash
pnpm install
pnpm run build
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
  `pnpm run watch` rebuilds on change.
- **Backend** — `main.py` + `py_modules/grimoire/`. Pure stdlib Python
  (no vendored dependencies needed). Builds are stored as JSON in the
  plugin settings directory.
- **Providers** — `py_modules/grimoire/providers/` contains one module per
  guide site. The generic fallback (og:title scrape + open-in-browser)
  always works; structured parsers must degrade to it gracefully.

## License

[BSD-3-Clause](LICENSE)
