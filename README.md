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

## Features

- 📚 **Build library** — paste a guide link once, it's saved on your Deck
- ★ **Pin your current build** — it stays at the top of the list
- 🧩 **The whole build, right in the overlay** — skills, gear, stat
  priorities, paragon boards, charms and mercenaries, without leaving your
  game. ✱ marks the stats worth a Greater Affix, and tempering,
  masterworking and sockets are all spelled out per item.
- 🔀 **Build variants** — Starter, Endgame, Pushing... switch between a
  guide's variants with one dropdown.
- ↕️ **Your order** — mostly check gear? Move that section up once and it
  stays first, in every build.
- ✅ **Leveling checklist** — check off skills and steps as you take them;
  Grimoire remembers where you left off, per build and variant.
- 📝 **Notes** — jot down your own reminders on any build, right in the
  panel.
- 🌐 **Open full guide** — for the details only the full page has (like
  paragon pathing), jump to the guide in the built-in browser while your
  game keeps running.
- 📴 **Works offline** — your library lives on the Deck; a saved build is
  readable with no connection.

Supports **Mobalytics**, **Maxroll** (planners and build guides) and
**d4builds.gg** links. A guide site redesign can never break your library —
worst case a build temporarily shows fewer sections until Grimoire catches
up.

### Roadmap

- Testing on real Steam Deck hardware
- More games (Path of Exile 2, Last Epoch) and the Decky store

## Installation

Grimoire is not in the Decky store yet. The easiest way to try it: grab
`decky-grimoire.zip` from the latest [release](../../releases/latest) and
use Decky's *Developer → Install plugin from zip* (requires developer mode
in Decky settings). Fresh-from-main builds are also available as
[Actions](../../actions) artifacts.

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
- **Validating parsers** — guide sites redesign freely; when a provider
  stops yielding sections, re-check it from a normal network with
  `python3 scripts/validate_live.py <guide-url>`. Title but no sections =
  that provider needs work; open an issue with the output.

## License

[BSD-3-Clause](LICENSE)
