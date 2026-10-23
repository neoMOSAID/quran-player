
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

    def handle_log(self, args):
        try:
            numlines = int(args)
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


def about():
    ver_line = f"Version {VERSION}".center(54)
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

    \033]8;;https://mosaid.xyz/quran-player\a🌐 Website\033]8;;\a
    \033]8;;https://github.com/neoMOSAID/quran-player\a🐙 GitHub Repository\033]8;;\a

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
        ("status", "JSON status snapshot"),
        ("info", "Full diagnostic dump"),
        ("config", "Regenerate config.ini"),
        ("cleanup", "Remove stale runtime files"),
        ("about / help", "Show this info"),
    ]

    cmd_list = "\n".join([f"  {cmd[0]:<38} {cmd[1]}" for cmd in commands])
    print(f"{about_info}\n{cmd_list}\n\n    © 2026 Quran Player Project - GPLv3 License")
    return True


