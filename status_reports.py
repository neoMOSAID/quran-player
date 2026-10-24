
"""Status mixin: status/log/config/info commands, plus the about() function."""

import json
import os
import sys
import tempfile
from collections import deque
from datetime import datetime

from config_manager import config
from daemon_utils import is_daemon_running
from version import VERSION


class StatusMixin:
    def handle_status(self):
        surah, ayah = self.current_verse
        repeat_info = {
            "repeat": self.repeat_range is not None,
            "repeat_start": 0,
            "repeat_end": 0,
            "repeat_surah": surah,
        }
        if self.repeat_range:
            repeat_info["repeat_start"] = self.repeat_range[0]
            repeat_info["repeat_end"] = self.repeat_range[1]
        conky_running = self.conky_process is not None and self.conky_process.poll() is None
        return json.dumps({
            "playing": self.audio_player.state == "playing",
            "paused": self.audio_player.state == "paused",
            "surah": surah,
            "ayah": ayah,
            **repeat_info,
            "conky_enabled": self.conky_enabled,
            "conky_running": conky_running,
            "daemon_running": True,
        })

    def handle_config(self):
        config.generate_default_config()
        self.log_action("INFO", f"Default config generated at {config.USER_CONFIG_FILE}")
        return True

    def handle_config_get(self):
        """Return config.ini rendered with schema comments + effective values."""
        return config.render_template()

    def handle_config_defaults(self):
        """Return config.ini rendered with all defaults active (for Restore Defaults)."""
        return config.render_defaults()

    def handle_config_set(self, args):
        """Validate text, write config.ini, reload state, apply conky changes."""
        ok, err = config.validate_ini(args)
        if not ok:
            self.error_msg = f"Validation failed: {err}"
            self.log_action("ERROR", self.error_msg)
            return False
        try:
            with open(config.USER_CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(args)
        except OSError as e:
            self.error_msg = f"Write failed: {e}"
            self.log_action("ERROR", self.error_msg)
            return False

        was_conky_enabled = self.conky_enabled
        config.reload()
        self.audio_base = config.get('daemon', 'FILES_DIRECTORY', config.SAMPLE_DIR)
        self.conky_enabled = config.getboolean('conky', 'enable', True)

        if self.conky_enabled and not was_conky_enabled:
            self._start_conky()
        elif not self.conky_enabled and was_conky_enabled:
            self._stop_conky()

        self.log_action("INFO", "Configuration updated via config_set")
        return True

    def handle_reload_config(self):
        """Re-read config.ini from disk and refresh config-derived state."""
        if not config.reload():
            self.error_msg = "Failed to reload config"
            return False
        # Refresh the instance state that was seeded from config at startup.
        self.audio_base = config.get('daemon', 'FILES_DIRECTORY', config.SAMPLE_DIR)
        self.conky_enabled = config.getboolean('conky', 'enable', True)
        self.log_action("INFO", "Configuration reloaded from disk")
        return True

    def handle_log(self, args):
        try:
            numlines = min(int(args), 10_000)
            with open(config.LOG_FILE, "r") as file:
                last_n_lines = deque(file, maxlen=numlines)
                return '\n'.join(last_n_lines)
        except Exception as e:
            self.log_action("ERROR", f"Log retrieval failed: {str(e)}")
            return f"ERROR: {str(e)}"

    def handle_info(self):
        info_lines = []
        info_lines.append("╔════════════════════════════════════════════════════╗")
        info_lines.append("║         📖 Quran Player Daemon Information         ║")
        info_lines.append("╚════════════════════════════════════════════════════╝")

        daemon_running = is_daemon_running()
        info_lines.append("\n[🟢 Daemon Status]")
        info_lines.append(f"  ├─ Status        : {'Running ✅' if daemon_running else 'Not Running ❌'}")
        info_lines.append(f"  └─ Current PID   : {os.getpid()}")

        with self.state_lock:
            current_surah, current_ayah = self.current_verse
            repeat_enabled = self.repeat_range is not None
            repeat_start, repeat_end = self.repeat_range if self.repeat_range else (0, 0)

        info_lines.append("\n[🎧 Playback Info]")
        info_lines.append(f"  ├─ Current Verse : Surah {current_surah}, Ayah {current_ayah}")
        if repeat_enabled:
            info_lines.append(f"  └─ Repeat Mode   : Enabled (Ayahs {repeat_start} → {repeat_end})")
        else:
            info_lines.append(f"  └─ Repeat Mode   : Disabled")

        conky_running = self.conky_process is not None and self.conky_process.poll() is None
        conky_pids = self._find_conky_pids()
        info_lines.append("\n[🖼️  Conky Display]")
        info_lines.append(f"  ├─ Enabled       : {'Yes' if self.conky_enabled else 'No'}")
        info_lines.append(f"  ├─ Running       : {'Yes ✅' if conky_running else 'No'}")
        if conky_pids:
            single = len(conky_pids) == 1
            marker = "✅" if single else "⚠️ "
            info_lines.append(f"  ├─ PIDs          : {', '.join(map(str, conky_pids))} ({len(conky_pids)} instance{'s' if not single else ''}) {marker}")
            info_lines.append(f"  ├─ Single inst.  : {'Yes ✅' if single else 'No ❌ — run conky_off then conky_on'}")
        else:
            info_lines.append(f"  ├─ PIDs          : — (no conky running)")
            info_lines.append(f"  ├─ Single inst.  : —")
        info_lines.append(f"  ├─ Config        : {config.CONKY_CONFIG}")
        verse_file = os.path.join(tempfile.gettempdir(), "quran_verse.txt")
        if os.path.exists(verse_file):
            size = os.path.getsize(verse_file)
            mtime = datetime.fromtimestamp(os.path.getmtime(verse_file))
            info_lines.append(f"  └─ Verse file    : {verse_file} ({size} bytes, {mtime})")
        else:
            info_lines.append(f"  └─ Verse file    : {verse_file} (❌ Missing)")

        info_lines.append("\n[📁 Audio Files]")
        info_lines.append(f"  └─ Directory     : {self.audio_base}")

        missing_audio = [f for f in config.REQUIRED_FILES
                         if not os.path.exists(os.path.join(self.audio_base, f))]
        if missing_audio:
            info_lines.append("  ⚠️  Missing Required Files:")
            for f in missing_audio:
                info_lines.append(f"    - {f}")
        else:
            info_lines.append("  ✅ All required files are present.")

        info_lines.append("\n[📂 Core Directories]")
        core_dirs = {
            "User Config": config.USER_CONFIG_DIR,
            "Control Dir": config.CONTROL_DIR,
            "Sample Dir": config.SAMPLE_DIR,
            "Script Dir": config.SCRIPT_DIR,
            "Conky Dir": config.CONKY_DIR,
        }
        for name, path in core_dirs.items():
            exists = "✅ Exists" if os.path.exists(path) else "❌ Missing"
            info_lines.append(f"  ├─ {name:13}: {path} ({exists})")

        info_lines.append("\n[📜 Log File]")
        if os.path.exists(config.LOG_FILE):
            size = os.path.getsize(config.LOG_FILE)
            mtime = datetime.fromtimestamp(os.path.getmtime(config.LOG_FILE))
            info_lines.append(f"  ├─ File          : {config.LOG_FILE}")
            info_lines.append(f"  ├─ Size          : {size} bytes")
            info_lines.append(f"  └─ Last Modified : {mtime}")
        else:
            info_lines.append(f"  └─ File          : {config.LOG_FILE} (❌ Missing)")

        log_level_str = config.get("daemon", "LOG_LEVEL", "INFO").upper()
        info_lines.append(f"  🔧 Log Level     : {log_level_str}")

        info_lines.append("\n[💻 System Info]")
        info_lines.append(f"  ├─ Platform      : {sys.platform}")
        info_lines.append(f"  ├─ Python        : {sys.version.split()[0]}")
        info_lines.append(f"  ├─ DISPLAY       : {os.environ.get('DISPLAY', 'Not Set')}")
        info_lines.append(f"  └─ SDL_AUDIODRIVER: {os.environ.get('SDL_AUDIODRIVER', 'Not Set')}")

        if 1 <= current_surah < len(self.surah_ayat):
            total_ayah = self.surah_ayat[current_surah]
            info_lines.append(f"\n[🔢 Surah Info]")
            info_lines.append(f"  └─ Total Ayahs in Surah {current_surah}: {total_ayah}")

        return "\n".join(info_lines)

    def handle_conky_config(self):
        """Return current conky config as JSON (client reads it as data)."""
        from conky_config_manager import conky_config
        return conky_config.render_json()

    def handle_conky_config_defaults(self):
        """Return default conky config as JSON (for 'Restore Defaults')."""
        from conky_config_manager import conky_config
        return conky_config.render_defaults_json()

    def handle_conky_config_set(self, args):
        """Save new conky config from a JSON string (validated daemon-side)."""
        from conky_config_manager import conky_config, ConkyConfigError
        try:
            new_config = json.loads(args)
        except json.JSONDecodeError as e:
            self.error_msg = f"Invalid JSON: {e}"
            self.log_action("ERROR", self.error_msg)
            return False
        try:
            conky_config.save(new_config)
        except ConkyConfigError as e:
            self.error_msg = f"Validation failed: {e}"
            self.log_action("ERROR", self.error_msg)
            return False
        # If conky was running, restart so new config takes effect.
        if self.conky_process and self.conky_process.poll() is None:
            self._stop_conky()
            self._start_conky()
        self.log_action("INFO", "Conky config updated")
        return True

    def handle_conky_config_reset(self):
        """Restore conky config to defaults and restart conky if running."""
        from conky_config_manager import conky_config
        try:
            conky_config.reset()
        except Exception as e:
            self.error_msg = f"Reset failed: {e}"
            self.log_action("ERROR", self.error_msg)
            return False
        if self.conky_process and self.conky_process.poll() is None:
            self._stop_conky()
            self._start_conky()
        self.log_action("INFO", "Conky config reset to defaults")
        return True


def _link(url, label):
    """OSC-8 hyperlink where supported, plain 'label: url' otherwise."""
    if not sys.stdout.isatty():
        return f"{label}: {url}"
    term = os.environ.get("TERM", "").lower()
    if term in ("", "dumb"):
        return f"{label}: {url}"
    if os.environ.get("TMUX") and term.startswith("screen"):
        return f"{label}: {url}"
    return f"\033]8;;{url}\a{label}\033]8;;\a"


def about():
    ver_line = f"Version {VERSION}".center(54)
    website_line = _link("https://mosaid.xyz/quran-player", "🌐 Website")
    github_line = _link("https://github.com/neoMOSAID/quran-player", "🐙 GitHub Repository")

    about_info = f"""
    ┌──────────────────────────────────────────────────────┐
    │                  Quran Player Daemon                 │
    │{ver_line}│
    │              (Linux + Conky, native)                 │
    └──────────────────────────────────────────────────────┘

    A Linux-native daemon for Quran audio playback with
    synchronized desktop verse display via Conky.

    ┌──────────────────────────────────────────────────────┐
    │                     Project Links                    │
    └──────────────────────────────────────────────────────┘

    {website_line}
    {github_line}

    ┌──────────────────────────────────────────────────────┐
    │                 Supported Commands                   │
    └──────────────────────────────────────────────────────┘
    """

    commands = [
        ("start", "Initialize the daemon process"),
        ("stop", "Terminate the daemon"),
        ("play", "Resume audio playback"),
        ("pause", "Pause current playback"),
        ("toggle", "Toggle play/pause"),
        ("prev / next", "Previous / next verse"),
        ("goto <ayah>", "Jump to specific ayah (keeps repeat mode)"),
        ("load <surah>[:ayah]", "Load surah or verse"),
        ("repeat <range>", "<surah>, <start:end>, or <surah>:start:end"),
        ("repeat_off", "Exit repeat mode"),
        ("ns / ps", "Next / previous surah"),
        ("dir <path>", "Change audio directory"),
        ("conky_on / conky_off / conky_toggle", "Control desktop verse display"),
        ("conky_config*", "Inspect / edit Conky display config"),
        ("config_get / config_defaults / config_set", "Inspect / edit config.ini"),
        ("reload_config", "Reload config.ini from disk"),
        ("status", "JSON status snapshot"),
        ("info", "Full diagnostic dump"),
        ("config", "Regenerate config.ini"),
        ("cleanup", "Remove stale runtime files"),
        ("about / help", "Show this info"),
    ]

    cmd_list = "\n".join([f"  {cmd[0]:<42} {cmd[1]}" for cmd in commands])
    print(f"{about_info}\n{cmd_list}\n\n    © 2026 Quran Player Project - GPLv3 License")
    return True
    

