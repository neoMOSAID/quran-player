
# Quran Player

A Linux-native Quran player daemon with **Conky** desktop verse display.

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-green)](https://python.org)

**Version:** v2.0.3 · **License:** GPLv3
**Website:** <https://mosaid.xyz/quran-player> · **GitHub:** <https://github.com/neoMOSAID/quran-player>

---

## What it does

A background daemon plays Quran recitations verse-by-verse while **Conky** renders the current verse as a live overlay on your desktop. The daemon and Conky stay in sync — when the verse advances, the display updates within half a second.

| Component | Purpose |
|---|---|
| `daemon.py` | Audio playback + Conky lifecycle + command socket |
| `quran_daemon_conky/` | Conky widget (installed to `~/.quran-player/conky/`) |
| `quran_gui.py` | PyQt5 tray controller |
| `quran_search.py` | Search tool (CLI + interactive RTL dialog) |
| `install.py` | Installer (no root required) |

---

## Features

- Verse-by-verse playback with auto-advance and persistent state
- Conky overlay updates in real time (0.5 s poll)
- Repeat ranges, `goto`, next/previous surah
- `conky_on` / `conky_off` — hide the verse display without stopping the daemon
- Dark-themed GUI with tray integration and keyboard shortcuts
- Arabic search with hamza/diacritic normalization
- **Zero runtime dependencies beyond `python3`, `conky`, `pactl`**

---

## Install

Requires **Python 3.9+** and **conky**. **No sudo required.**

```bash
# 1. Install conky (skip if already installed)
sudo apt install conky-all     # Debian/Ubuntu
# sudo pacman -S conky         # Arch
# sudo dnf install conky       # Fedora

# 2. Install quran-player
git clone https://github.com/neoMOSAID/quran-player.git
cd quran-player
python install.py
```

The installer places everything under `~/.quran-player/` and CLI wrappers under `~/.local/bin/`. Add `~/.local/bin` to `PATH` if it isn't already.

### Installer flags

```bash
python install.py                   # install / update
python install.py --clean           # wipe install (keep config), reinstall
python install.py --dry-run         # preview changes
python install.py --no-conky        # skip Conky widget
python install.py --uninstall       # remove install, keep config
python install.py --uninstall --purge
```

---

## Usage

### Daemon

```bash
quran-daemon start                     # daemon starts; conky launches automatically
quran-daemon play | pause | toggle
quran-daemon next | prev
quran-daemon load 2:255                # surah:ayah
quran-daemon load 36                   # whole surah
quran-daemon repeat 10:15              # ayahs 10–15 of current surah
quran-daemon repeat 2:1:20             # surah 2, ayahs 1–20
quran-daemon repeat_off
quran-daemon goto 42
quran-daemon ns | ps                   # next/prev surah
quran-daemon conky_off                 # hide desktop verse (daemon keeps playing)
quran-daemon conky_on                  # show it again
quran-daemon conky_toggle
quran-daemon status                    # JSON (includes conky state)
quran-daemon info                      # full diagnostic dump
quran-daemon stop                      # daemon stops; conky terminates
```

### GUI

```bash
quran-gui
```

Keyboard: **Space** play/pause · **←** prev · **→** next · **Esc** hide. Has a **Conky** toggle button.

### Search

```bash
quran-search                           # interactive RTL dialog
quran-search 2 255                     # print ayah
quran-search 2 1 20                    # print range
```

---

## Audio files

Place files named `SSSAAA.mp3` in `~/.config/quran-player/sample/` (or the directory set by `files_directory` in `config.ini`):

- `SSS` = 3-digit surah (`002` for Al-Baqarah)
- `AAA` = 3-digit ayah (`001` for the first ayah)

Download from [everyayah.com](https://everyayah.com/recitations_ayat.html).

---

## Configuration

`~/.config/quran-player/config.ini`:

```ini
[daemon]
max_log_size = 1000000
log_level    = INFO
files_directory =

[conky]
enable     = yes
executable =
```

Change `[conky] enable` to `no` to keep the daemon silent. Toggle at runtime with `conky_on` / `conky_off`.

---

## Troubleshooting

### Conky doesn't show the verse

1. `qd info` — check "Conky Display → Running: Yes". If "No", check the log.
2. Verify `conky` is installed: `which conky`
3. Check `$DISPLAY` / `$WAYLAND_DISPLAY` are set (needed for conky to launch)
4. Check `/tmp/quran_verse.txt` exists and has content (updated when playback starts)
5. Run conky manually to see errors:
   ```bash
   conky -c ~/.quran-player/conky/conky_quran
   ```

### Arabic renders as disconnected letters

Your conky doesn't have an Arabic-capable font. Make sure **Amiri** (or another Arabic font) is installed:

```bash
sudo apt install fonts-hosny-amiri
```

Or edit `~/.quran-player/conky/conky_quran` and change `font = 'Amiri:size=38'` to another Arabic font.

### `quran-daemon` is shadowed by an old install

If `type quran-daemon` shows something other than `~/.local/bin/quran-daemon`, remove the stale alias and ensure `~/.local/bin` is early in `PATH`.

---

## Project layout

```
quran-player/
├── daemon.py
├── quran_gui.py
├── quran_search.py
├── audio_player.py
├── config_manager.py
├── install.py
├── load.py
├── default_config.ini
├── requirements.txt
├── quran-text/            # chapters.txt, uthmani.txt, simplified.txt
├── audio/                 # bundled sample ayahs
├── quran_daemon_conky/    # → installed as ~/.quran-player/conky/
│   ├── conky_quran
│   ├── reshape_arabic.py
│   ├── reshape_arabic.sh
│   └── config.ini
└── move_dead_files.sh     # repo utility
```

---

## License

[GPLv3](https://www.gnu.org/licenses/gpl-3.0.en.html).

