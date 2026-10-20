
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

import warnings
warnings.filterwarnings("ignore", message=".*avx2 capable.*", category=RuntimeWarning)

import sys
import socket
import threading
import inspect
import time
from datetime import datetime
import pygame
import portalocker
import json
import tempfile
import shutil
import subprocess
import configparser
import signal
from collections import deque


import quran_search
from audio_player import AudioPlayer
from config_manager import config
from version import VERSION


LOG_LEVELS = {
    "CRITICAL": 50, "ERROR": 40, "WARNING": 30,
    "INFO": 20, "DEBUG": 10, "DISABLED": 0,
}

CRITICAL_FLAGS = {"CRITICAL", "ERROR"}


class Daemon:
    def __init__(self):
        self.running = False
        self.error_msg = ""
        self.log_lock = threading.Lock()
        self.state_lock = threading.Lock()

        self.valid_commands = [
            "play", "pause", "resume", "toggle", "stop", "load",
            "repeat", "repeat_off", "dir", "ns", "ps", "goto",
            "prev", "next", "status", "config", "log",
            "conky_on", "conky_off", "conky_toggle",
        ]

        self.surah_ayat = [
            0,
            7,   286, 200, 176, 120, 165, 206, 75,  129, 109,
            123, 111, 43,  52,  99,  128, 111, 110, 98,  135,
            112, 78,  118, 64,  77,  227, 93,  88,  69,  60,
            34,  30,  73,  54,  45,  83,  182, 88,  75,  85,
            54,  53,  89,  59,  37,  35,  38,  29,  18,  45,
            60,  49,  62,  55,  78,  96,  29,  22,  24,  13,
            14,  11,  11,  18,  12,  12,  30,  52,  52,  44,
            28,  28,  20,  56,  40,  31,  50,  40,  46,  42,
            29,  19,  36,  25,  22,  17,  19,  26,  30,  20,
            15,  21,  11,  8,   8,   19,  5,   8,   8,   11,
            11,  8,   3,   9,   5,   4,   7,   3,   6,   3,
            5,   4,   5,   6,
        ]
        assert len(self.surah_ayat) == 115, (
            f"surah_ayat must have 115 entries (index 0 unused), got {len(self.surah_ayat)}"
        )

        self.audio_base = config.get('daemon', 'FILES_DIRECTORY', config.SAMPLE_DIR)
        self.conky_enabled = config.getboolean('conky', 'enable', True)

        self.state_file = config.STATE_FILE
        self.audio_player = None
        self.current_verse = (1, 0)
        self.repeat_range = None
        self.conky_process = None
        self._lock_handle = None

        self.load_playback_state()

    # ------------------------------------------------------------------ dir
    def handle_dir(self, path):
        if not os.path.isdir(path):
            self.log_action("ERROR", f"Invalid directory: {path}")
            return False
        config.set('daemon', 'FILES_DIRECTORY', path)
        self.audio_base = path
        if self.audio_player.state in ("playing", "paused") and self.current_verse:
            self.log_action("INFO", f"Reloading audio from new directory: {path}")
            current_verse = self.current_verse
            self.audio_player.stop()
            return self.play_verse(current_verse)
        return True

    # ------------------------------------------------------------------ logs
    def log_action(self, flag, msg):
        log_level_str = config.get("daemon", "LOG_LEVEL", "INFO").upper()
        log_level = LOG_LEVELS.get(log_level_str, 20)
        message_priority = LOG_LEVELS.get(flag, 20)
        if message_priority < log_level and flag not in CRITICAL_FLAGS:
            return

        method = inspect.currentframe().f_back.f_code.co_name
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        pid = os.getpid()
        log_entry = f"{timestamp}|{pid}|{method}|{flag}|{msg}\n"

        log_path = config.CLIENT_LOG_FILE if method == "handle_client" and flag == "ERROR" else config.LOG_FILE
        self.rotate_log_if_needed(log_path)

        try:
            with open(log_path, "a") as log:
                log.write(log_entry)
        except IOError as e:
            print(f"Failed to write to log: {str(e)}", file=sys.stderr)

    def rotate_log_if_needed(self, logfile):
        max_size = config.getint('daemon', 'MAX_LOG_SIZE', 1000000)
        with self.log_lock:
            try:
                if os.path.exists(logfile) and os.path.getsize(logfile) >= max_size:
                    rotated_log = f"{logfile}.1"
                    if os.path.exists(rotated_log):
                        os.remove(rotated_log)
                    os.rename(logfile, rotated_log)
                    with open(logfile, "w") as new_log:
                        new_log.write(f"{datetime.now().isoformat()}|SYSTEM|LOG|Rotated log file\n")
            except Exception as e:
                print(f"Log rotation failed: {str(e)}", file=sys.stderr)

    # ------------------------------------------------------------------ conky
    def _find_conky_executable(self):
        configured = config.get('conky', 'executable', '') or ''
        if configured and os.path.exists(configured):
            return configured
        return shutil.which('conky')

    def _start_conky(self):
        if self.conky_process and self.conky_process.poll() is None:
            return True

        if not self.conky_enabled:
            return False

        if not os.path.exists(config.CONKY_CONFIG):
            self.log_action("WARNING", f"Conky config missing: {config.CONKY_CONFIG}")
            return False

        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            self.log_action("WARNING", "No display server — conky cannot start")
            return False

        conky_exe = self._find_conky_executable()
        if not conky_exe:
            self.log_action("WARNING", "conky not installed (sudo apt install conky-all)")
            return False

        # Kill any orphan conky from a crashed previous daemon using OUR config
        self._kill_orphan_conky()

        try:
            self.conky_process = subprocess.Popen(
                [conky_exe, '-c', config.CONKY_CONFIG],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.log_action("INFO", f"Conky started (PID {self.conky_process.pid})")
            return True
        except Exception as e:
            self.log_action("ERROR", f"Failed to start conky: {e}")
            return False

    def _kill_orphan_conky(self):
        """Kill any conky processes using our config, that we do not own."""
        try:
            result = subprocess.run(
                ['pgrep', '-f', config.CONKY_CONFIG],
                capture_output=True, text=True, timeout=2,
            )
            pids = [int(p) for p in result.stdout.split() if p.isdigit()]
        except (subprocess.SubprocessError, FileNotFoundError, ValueError):
            return

        for pid in pids:
            if self.conky_process and pid == self.conky_process.pid:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                self.log_action("WARNING", f"Killed orphan conky PID {pid}")
            except (ProcessLookupError, PermissionError):
                pass

    def _stop_conky(self):
        if not (self.conky_process and self.conky_process.poll() is None):
            self.conky_process = None
            return
        try:
            self.conky_process.terminate()
            try:
                self.conky_process.wait(timeout=2)
                self.log_action("INFO", "Conky stopped")
            except subprocess.TimeoutExpired:
                self.log_action("WARNING", "Conky didn't exit on SIGTERM, sending SIGKILL")
                self.conky_process.kill()
                try:
                    self.conky_process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.log_action("ERROR", "Conky survived SIGKILL — giving up")
        except Exception as e:
            self.log_action("ERROR", f"Conky stop failed: {e}")
        finally:
            self.conky_process = None

    def _write_verse_file(self, text):
        """Write current verse for conky to pick up (conky polls every 0.5s)."""
        verse_file = os.path.join(tempfile.gettempdir(), "quran_verse.txt")
        try:
            with open(verse_file, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            self.log_action("ERROR", f"Failed to write {verse_file}: {e}")

    def handle_conky_on(self):
        self.conky_enabled = True
        config.set('conky', 'enable', 'yes')
        if not self._start_conky():
            self.error_msg = "Conky could not start (check log — missing binary/config/display)"
            return False
        return True

    def handle_conky_off(self):
        self.conky_enabled = False
        config.set('conky', 'enable', 'no')
        self._stop_conky()
        return True

    def handle_conky_toggle(self):
        if self.conky_enabled:
            return self.handle_conky_off()
        return self.handle_conky_on()

    # ------------------------------------------------------------------ state
    def load_playback_state(self):
        state = configparser.ConfigParser()
        if os.path.exists(self.state_file):
            state.read(self.state_file)
            try:
                surah = state.getint('state', 'surah', fallback=1)
                ayah = state.getint('state', 'ayah', fallback=0)
                if self.is_valid_verse(surah, ayah):
                    self.current_verse = (surah, ayah)
                else:
                    self.current_verse = (1, 0)
            except (ValueError, TypeError) as e:
                self.log_action("ERROR", f"Corrupted state file: {e}. Using defaults")
                self.current_verse = (1, 0)

    def save_playback_state(self):
        surah, ayah = self.current_verse
        state = configparser.ConfigParser()
        state['state'] = {'surah': str(surah), 'ayah': str(ayah)}
        state_dir = os.path.dirname(self.state_file) or '.'
        with tempfile.NamedTemporaryFile('w', delete=False, dir=state_dir) as tf:
            state.write(tf)
            temp_name = tf.name
        try:
            os.replace(temp_name, self.state_file)
        except OSError as e:
            self.log_action("ERROR", f"State save failed: {str(e)}")
            try:
                os.unlink(temp_name)
            except Exception:
                pass

    def is_valid_verse(self, surah, ayah):
        if not (1 <= surah <= 114):
            return False
        if ayah < 0 or ayah > self.surah_ayat[surah]:
            return False
        return True

    def get_next_verse(self):
        surah, ayah = self.current_verse
        if self.repeat_range:
            start, end = self.repeat_range
            next_ayah = ayah + 1
            if next_ayah > end:
                next_ayah = start
                if start == 0 and not self.audio_player.get_audio_path(surah, 0):
                    next_ayah = 1
            return (surah, next_ayah)
        next_ayah = ayah + 1
        max_ayah = self.surah_ayat[surah]
        if next_ayah > max_ayah:
            next_surah = surah + 1
            if next_surah > 114:
                next_surah = 1
            return (next_surah, 0)
        return (surah, next_ayah)

    def get_prev_verse(self):
        surah, ayah = self.current_verse
        if ayah == 0:
            prev_surah = surah - 1
            if prev_surah < 1:
                prev_surah = 114
            prev_ayah = self.surah_ayat[prev_surah]
            return (prev_surah, prev_ayah)
        return (surah, ayah - 1)

    # ------------------------------------------------------------------ playback
    def handle_playback_end(self):
        if self.audio_player.state != "playing":
            return
        with self.state_lock:
            next_verse = self.get_next_verse()
            if next_verse:
                self.current_verse = next_verse
                self.save_playback_state()
        if next_verse:
            self.play_verse(next_verse)

    def handle_playback_events(self):
        if self.audio_player.state == "playing":
            try:
                if not pygame.mixer.music.get_busy():
                    self.handle_playback_end()
            except pygame.error:
                self.log_action("WARNING", "Audio system error, reinitializing")
                self.audio_player.init_audio()

    def play_verse(self, verse):
        surah, ayah = verse
        audio_path = self.audio_player.get_audio_path(surah, ayah)
        if not audio_path:
            self.log_action("ERROR", f"Audio file not found: {surah:03}{ayah:03}.mp3")
            return False

        if ayah:
            quran_text = quran_search.get_verse_text(surah, ayah)
        else:
            quran_text = "بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ"

        self._write_verse_file(quran_text)
        return self.audio_player.play(audio_path)

    # ------------------------------------------------------------------ command handlers
    def handle_play(self):
        if self.audio_player.state == "paused":
            return self.audio_player.play(self.audio_player.current_audio_path)
        return self.play_verse(self.current_verse)

    def handle_pause(self):
        return self.audio_player.pause()

    def handle_resume(self):
        return self.handle_play()

    def handle_toggle(self):
        if self.audio_player.state == "stopped":
            return self.play_verse(self.current_verse)
        return self.audio_player.toggle_pause()

    def handle_stop(self):
        """Stop the daemon gracefully — conky shut down synchronously."""
        try:
            self.audio_player.stop()
            self._stop_conky()
            self._kill_orphan_conky()          # catch any leftover from a crashed run
            self.running = False
            if hasattr(self, 'server_socket') and self.server_socket:
                try:
                    self.server_socket.close()
                except Exception:
                    pass
            return "OK: Daemon shutting down"
        except Exception as e:
            self.log_action("ERROR", f"Error during stop: {str(e)}")
            return f"ERROR: {str(e)}"

    def handle_next(self):
        next_verse = self.get_next_verse()
        if next_verse:
            self.current_verse = next_verse
            self.save_playback_state()
            return self.play_verse(next_verse)
        return False

    def handle_prev(self):
        prev_verse = self.get_prev_verse()
        if prev_verse:
            self.current_verse = prev_verse
            self.save_playback_state()
            return self.play_verse(prev_verse)
        return False

    def handle_goto(self, ayah_str):
        try:
            ayah = int(ayah_str)
        except ValueError:
            self.log_action("ERROR", "Invalid ayah number")
            self.error_msg = "ERROR: Invalid ayah number"
            return False

        current_surah, _ = self.current_verse
        max_ayat = self.surah_ayat[current_surah]
        if ayah < 0 or ayah > max_ayat:
            self.log_action("ERROR", f"Invalid ayah {ayah} for Surah {current_surah} (0-{max_ayat})")
            self.error_msg = f"Invalid ayah {ayah} for Surah {current_surah} (0-{max_ayat})"
            return False
        if ayah == 0 and not self.audio_player.get_audio_path(current_surah, 0):
            self.error_msg = f"Surah {current_surah} has no bismillah audio"
            return False
        if self.repeat_range:
            start, end = self.repeat_range
            if ayah < start or ayah > end:
                self.log_action("ERROR", f"Ayah {ayah} not in repeat range ({start}-{end})")
                self.error_msg = f"Ayah {ayah} not in repeat range ({start}-{end})"
                return False
        if not self.audio_player.get_audio_path(current_surah, ayah):
            self.log_action("ERROR", f"Audio file not found: {current_surah:03}{ayah:03}.mp3")
            self.error_msg = f"Audio file not found: {current_surah:03}{ayah:03}.mp3"
            return False

        self.current_verse = (current_surah, ayah)
        self.save_playback_state()
        if self.audio_player.state in ("playing", "paused"):
            self.audio_player.stop()
            return self.play_verse(self.current_verse)
        return True

    def handle_load(self, args):
        try:
            parts = args.split(':')
            if len(parts) == 1:
                surah = int(parts[0])
                if not (1 <= surah <= 114):
                    raise ValueError("Invalid surah number")
                ayah = 0 if surah != 9 else 1
                if ayah == 0 and not self.audio_player.get_audio_path(surah, 0):
                    ayah = 1
                self.current_verse = (surah, ayah)
            elif len(parts) == 2:
                surah, ayah = map(int, parts)
                if not self.is_valid_verse(surah, ayah):
                    raise ValueError("Invalid verse")
                self.current_verse = (surah, ayah)
            else:
                raise ValueError("Invalid format")
            self.repeat_range = None
            self.save_playback_state()
            return self.play_verse(self.current_verse)
        except ValueError as e:
            self.log_action("ERROR", f"Invalid load format: {str(e)}")
            return False

    def handle_ns(self):
        current_surah, _ = self.current_verse
        next_surah = (current_surah % 114) + 1
        starting_ayah = 0
        if next_surah == 9:
            starting_ayah = 1
        elif not self.audio_player.get_audio_path(next_surah, 0):
            starting_ayah = 1
        return self._load_surah(next_surah, starting_ayah)

    def handle_ps(self):
        current_surah, _ = self.current_verse
        prev_surah = current_surah - 1
        if prev_surah < 1:
            prev_surah = 114
        starting_ayah = 0
        if prev_surah == 9:
            starting_ayah = 1
        elif not self.audio_player.get_audio_path(prev_surah, 0):
            starting_ayah = 1
        return self._load_surah(prev_surah, starting_ayah)

    def _load_surah(self, surah, starting_ayah):
        last_ayah = self.surah_ayat[surah]
        if self.repeat_range:
            self.repeat_range = (starting_ayah, last_ayah)
        self.current_verse = (surah, starting_ayah)
        self.save_playback_state()
        return self.play_verse(self.current_verse)

    def handle_repeat_off(self):
        with self.state_lock:
            if self.repeat_range is not None:
                self.repeat_range = None
                self.log_action("INFO", "Repeat mode turned off")
                return True
            return False

    def handle_repeat(self, args):
        if args.lower() == "off":
            return self.handle_repeat_off()

        parts = args.split(':')
        try:
            if len(parts) == 1:
                surah = int(parts[0])
                if not (1 <= surah <= 114):
                    raise ValueError("Invalid surah number")
                if surah != 9:
                    start = 0 if self.audio_player.get_audio_path(surah, 0) else 1
                else:
                    start = 1
                end = self.surah_ayat[surah]
                current_surah = surah
            elif len(parts) == 2:
                current_surah, _ = self.current_verse
                start = int(parts[0])
                end = int(parts[1])
            elif len(parts) == 3:
                surah = int(parts[0])
                start = int(parts[1])
                end = int(parts[2])
                if not (1 <= surah <= 114):
                    raise ValueError("Invalid surah number")
                current_surah = surah
            else:
                raise ValueError("Invalid number of arguments")
        except ValueError as e:
            self.log_action("ERROR", f"Invalid repeat format: {str(e)}")
            self.error_msg = f"ERROR: {str(e)}"
            return False

        if self.audio_player.state in ("playing", "paused"):
            self.audio_player.stop()

        max_ayat = self.surah_ayat[current_surah]
        if start == 0:
            if current_surah == 9:
                self.log_action("ERROR", "Surah 9 has no bismillah")
                self.error_msg = "ERROR: Surah 9 has no bismillah"
                start = 1
            if end < 0:
                end = 0
        else:
            if start < 1 or end > max_ayat:
                self.log_action("ERROR", f"Invalid range {start}-{end} for Surah {current_surah} (1-{max_ayat})")
                self.error_msg = f"Invalid range {start}-{end} for Surah {current_surah} (1-{max_ayat})"
                return False

        if start > end:
            self.log_action("ERROR", f"Start verse {start} > end verse {end}")
            self.error_msg = f"Start verse {start} > end verse {end}"
            return False

        for ayah in range(start, end + 1):
            if not self.audio_player.get_audio_path(current_surah, ayah):
                self.log_action("ERROR", f"Missing audio file {current_surah}:{ayah}")
                self.error_msg = f"Missing audio file {current_surah}:{ayah}"
                return False

        self.repeat_range = (start, end)
        self.current_verse = (current_surah, start)
        self.save_playback_state()
        return self.play_verse(self.current_verse)

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
        info_lines.append("\n[🖼️  Conky Display]")
        info_lines.append(f"  ├─ Enabled       : {'Yes' if self.conky_enabled else 'No'}")
        info_lines.append(f"  ├─ Running       : {'Yes ✅' if conky_running else 'No'}")
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

    def verify_audio_config(self):
        if shutil.which("pactl") is None:
            self.log_action("WARNING", "pactl not found — skipping audio server check")
            return True
        try:
            result = subprocess.run(['pactl', 'info'], capture_output=True, text=True, timeout=2)
            if result.returncode != 0:
                self.log_action("ERROR", "PulseAudio/PipeWire not running!")
                return False
            for line in result.stdout.splitlines():
                if line.lower().startswith("server name:"):
                    self.log_action("INFO", f"Audio server: {line.split(':', 1)[1].strip()}")
                    break
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            self.log_action("WARNING", "Could not verify audio server — continuing")
            return True

    # ------------------------------------------------------------------ client
    def handle_client(self, conn):
        try:
            conn.settimeout(5.0)
            data = conn.recv(1024).decode().strip()
            if not data:
                conn.sendall(b"ERROR: Empty command\n")
                return

            parts = data.split(maxsplit=1)
            command = parts[0]
            args = parts[1] if len(parts) > 1 else ''

            if command == "status":
                try:
                    conn.sendall(self.handle_status().encode() + b"\n")
                except BrokenPipeError:
                    self.log_action("WARNING", "Client disconnected before receiving status")
                return

            if command == "stop":
                response = self.handle_stop()
                try:
                    conn.sendall(response.encode() + b"\n")
                except BrokenPipeError:
                    self.log_action("WARNING", "Client disconnected during stop")
                return

            if command == "log":
                if not args:
                    conn.sendall(b"ERROR: Missing numlines\n")
                    return
                log_response = self.handle_log(args)
                try:
                    conn.sendall(log_response.encode() + b"\n")
                except BrokenPipeError:
                    self.log_action("WARNING", "Client disconnected before receiving log")
                return

            if command == "info":
                try:
                    conn.sendall(self.handle_info().encode() + b"\n")
                except BrokenPipeError:
                    self.log_action("WARNING", "Client disconnected before receiving info")
                return

            if command in ("about", "help"):
                import io
                from contextlib import redirect_stdout
                buf = io.StringIO()
                with redirect_stdout(buf):
                    about()
                try:
                    conn.sendall(buf.getvalue().encode() + b"\n")
                except BrokenPipeError:
                    self.log_action("WARNING", "Client disconnected before receiving about")
                return

            if command == "load":
                if not args:
                    conn.sendall(b"ERROR: Missing surah:ayah\n")
                    return
                success = self.handle_load(args)
            elif command == "goto":
                if not args:
                    conn.sendall(b"ERROR: Missing ayah number\n")
                    return
                success = self.handle_goto(args)
            elif command == "repeat":
                if not args:
                    success = self.handle_repeat_off()
                else:
                    success = self.handle_repeat(args)
            elif command == "repeat_off":
                success = self.handle_repeat_off()
            elif command == "dir":
                if not args:
                    conn.sendall(b"ERROR: Missing directory path\n")
                    return
                success = self.handle_dir(args)
            elif command in self.valid_commands:
                success = getattr(self, f"handle_{command}")()
            else:
                conn.sendall(b"ERROR: Unknown command\n")
                return

            try:
                response = b"OK\n" if success else f"ERROR: Command failed: {self.error_msg}\n".encode()
                conn.sendall(response)
            except (BrokenPipeError, ConnectionResetError):
                self.log_action("WARNING", "Client disconnected before receiving response")

        except Exception as e:
            self.log_action("ERROR", f"Client error: {str(e)}")
        finally:
            try:
                conn.close()
                self.error_msg = ""
            except Exception:
                pass

    # ------------------------------------------------------------------ lifecycle
    def handle_start(self):
        if not self.verify_audio_config():
            sys.exit(1)

        if not quran_search.ensure_data_loaded():
            self.log_action("ERROR", "Failed to load Quran text data — check quran-text/*.txt")
            sys.exit(1)

        if not self.audio_player:
            self.audio_player = AudioPlayer(config, self.log_action)

        if not self.audio_player.initialized:
            self.log_action("CRITICAL", "Audio player failed to initialize")
            print("", file=sys.stderr)
            print("=" * 68, file=sys.stderr)
            print("  ERROR: Audio subsystem failed to initialize", file=sys.stderr)
            print("=" * 68, file=sys.stderr)
            print("", file=sys.stderr)
            print(f"  Python version : {sys.version.split()[0]}", file=sys.stderr)
            print(f"  Virtualenv     : {sys.prefix}", file=sys.stderr)
            print(f"  Log            : {config.LOG_FILE}", file=sys.stderr)
            print("", file=sys.stderr)
            print("  Common cause: classic `pygame` (not `pygame-ce`) installed.", file=sys.stderr)
            print("", file=sys.stderr)
            print("  Fix:", file=sys.stderr)
            print("    " + sys.executable + " -m pip uninstall -y pygame", file=sys.stderr)
            print("    " + sys.executable + " -m pip install --force-reinstall pygame-ce", file=sys.stderr)
            print("=" * 68, file=sys.stderr)
            sys.exit(1)

        # Acquire lock
        try:
            self._lock_handle = open(config.LOCK_FILE, 'w')
            portalocker.lock(self._lock_handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except (IOError, OSError, portalocker.LockException):
            self.log_action("ERROR", "Daemon already running (locked)")
            sys.exit(1)

        # Clean stale state
        for f in [config.PID_FILE, config.SOCKET_FILE]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception as e:
                    self.log_action("ERROR", f"Cleanup failed: {str(e)}")
                    sys.exit(1)

        with open(config.PID_FILE, "w") as pid_file:
            pid_file.write(str(os.getpid()))

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(config.SOCKET_FILE)
        os.chmod(config.SOCKET_FILE, 0o600)  # only owner can control the daemon
        server.listen(5)
        server.settimeout(1)

        self.server_socket = server
        self.log_action("INFO", "Daemon started. Listening for commands.")
        self.running = True

        # Start conky display if enabled
        if self.conky_enabled:
            self._start_conky()

        print("OK")

        def shutdown_handler(signum, frame):
            self.log_action("INFO", f"Received signal {signum}, shutting down")
            self.running = False

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

        try:
            while self.running:
                try:
                    conn, _ = server.accept()
                    threading.Thread(target=self.handle_client, args=(conn,)).start()
                except socket.timeout:
                    pass
                except OSError:
                    if not self.running:
                        break
                    raise
                self.handle_playback_events()
                time.sleep(0.05)
        except KeyboardInterrupt:
            self.log_action("INFO", "Daemon shutting down.")
        finally:
            self.cleanup(server)

    def cleanup(self, server):
        original_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
        original_term = signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            self.running = False
            if self.audio_player:
                self.audio_player.cleanup()

            self._stop_conky()

            try:
                server.shutdown(socket.SHUT_RDWR)
                server.close()
            except Exception:
                pass

            for f in [config.PID_FILE, config.SOCKET_FILE]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

            if self._lock_handle:
                try:
                    portalocker.unlock(self._lock_handle)
                    self._lock_handle.close()
                except Exception:
                    pass
                self._lock_handle = None

            self.log_action("INFO", "Cleanup completed.")
        finally:
            signal.signal(signal.SIGINT, original_int)
            signal.signal(signal.SIGTERM, original_term)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------
def is_daemon_running():
    if not os.path.exists(config.LOCK_FILE):
        return False
    try:
        with open(config.LOCK_FILE, 'a') as f:
            try:
                portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
                portalocker.unlock(f)
                return False
            except (IOError, OSError, portalocker.LockException):
                return True
    except Exception:
        return False


def cleanup_orphaned_files():
    if not is_daemon_running():
        for f in [config.PID_FILE, config.SOCKET_FILE]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception as e:
                    print(f"Cleanup warning: {str(e)}")


def about():
    # `VERSION` comes from VERSION file via version.py — no hardcoding.
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
        ("repeat <range>", "<surah>, <start:end>, or <surah:start:end>"),
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

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Quran Player Daemon — Linux-native with Conky display',
        epilog='© 2026 Quran Player Project - GPLv3 License',
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    subparsers.add_parser('start', help='Start the daemon')
    subparsers.add_parser('stop', help='Stop the daemon')
    subparsers.add_parser('play', help='Resume audio')
    subparsers.add_parser('pause', help='Pause audio')
    subparsers.add_parser('toggle', help='Toggle play/pause')
    subparsers.add_parser('prev', help='Previous verse')
    subparsers.add_parser('next', help='Next verse')
    subparsers.add_parser('ns', help='Next surah')
    subparsers.add_parser('ps', help='Previous surah')
    subparsers.add_parser('repeat_off', help='Exit repeat mode')
    subparsers.add_parser('conky_on', help='Enable Conky display')
    subparsers.add_parser('conky_off', help='Disable Conky display')
    subparsers.add_parser('conky_toggle', help='Toggle Conky display')

    goto_parser = subparsers.add_parser('goto', help='Jump to ayah in current surah')
    goto_parser.add_argument('ayah', type=int)

    load_parser = subparsers.add_parser('load', help='Load surah or verse')
    load_parser.add_argument('verse', nargs='?', default='1:0')

    repeat_parser = subparsers.add_parser('repeat', help='Repeat range')
    repeat_parser.add_argument('range', nargs='?', default='off')

    dir_parser = subparsers.add_parser('dir', help='Change audio directory')
    dir_parser.add_argument('path')

    subparsers.add_parser('status', help='Playback status')
    subparsers.add_parser('cleanup', help='Remove stale runtime files')
    subparsers.add_parser('info', help='Diagnostic dump')
    subparsers.add_parser('about', help='About')
    subparsers.add_parser('help', help='Help')
    subparsers.add_parser('config', help='Regenerate config')

    args = parser.parse_args()
    daemon = Daemon()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "start":
        if is_daemon_running():
            print("Error: Daemon already running")
            sys.exit(1)
        daemon.handle_start()

    elif args.command == "stop":
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(5)
            client.connect(config.SOCKET_FILE)
            client.sendall(b"stop\n")
            print(client.recv(65536).decode().strip())
        except (ConnectionRefusedError, FileNotFoundError):
            print("Error: Daemon unavailable")
            sys.exit(1)

    elif args.command == "info":
        if not is_daemon_running():
            print(daemon.handle_info())
        else:
            try:
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(5)
                client.connect(config.SOCKET_FILE)
                client.sendall(b"info\n")
                print(client.recv(65536).decode().strip())
            except (ConnectionRefusedError, FileNotFoundError):
                print(daemon.handle_info())
    elif args.command == "cleanup":
        cleanup_orphaned_files()
        print("Orphaned files cleaned up")
    elif args.command in ("about", "help"):
        about()
    elif args.command == "config":
        daemon.handle_config()
        print(f"Generated config at {config.USER_CONFIG_FILE}")
    else:
        if not is_daemon_running():
            print("Error: Daemon not running. Start it first with: quran-daemon start")
            sys.exit(1)
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(5)
            client.connect(config.SOCKET_FILE)

            if args.command == "load":
                cmd_str = f"load {args.verse}"
            elif args.command == "repeat":
                cmd_str = f"repeat {args.range}"
            elif args.command == "goto":
                cmd_str = f"goto {args.ayah}"
            elif args.command == "dir":
                cmd_str = f"dir {args.path}"
            else:
                cmd_str = args.command

            client.sendall(cmd_str.encode() + b"\n")
            print(client.recv(65536).decode().strip())
        except (ConnectionRefusedError, FileNotFoundError):
            print("Error: Daemon unavailable")
            sys.exit(1)
