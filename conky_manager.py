
"""Conky mixin: process lifecycle, orphan sweep, verse file writes."""

import os
import shutil
import signal
import subprocess
import sys
import tempfile

from config_manager import config


class ConkyMixin:
    def _find_conky_executable(self):
        configured = config.get('conky', 'executable', '') or ''
        if configured and os.path.exists(configured):
            return configured
        return shutil.which('conky')

    def _start_conky(self):
        if self.conky_process and self.conky_process.poll() is None:
            return True
        self.conky_process = None
        if not self.conky_enabled:
            return False

        # Regenerate the runtime Lua from JSON before starting, so user edits
        # to conky_config.json always take effect on the next daemon start.
        try:
            from conky_config_manager import conky_config
            conky_config.render_lua()
        except Exception as e:
            self.log_action("ERROR", f"Failed to render conky config: {e}")
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

    def _find_conky_pids(self):
        try:
            result = subprocess.run(
                ['pgrep', '-x', 'conky'],
                capture_output=True, text=True, timeout=2,
            )
            pids = [int(p) for p in result.stdout.split() if p.isdigit()]
        except (subprocess.SubprocessError, FileNotFoundError, ValueError):
            return []

        needle_path = config.CONKY_CONFIG or ""
        needle_name = os.path.basename(needle_path) if needle_path else "conky_quran"

        matching = []
        for pid in pids:
            try:
                with open(f'/proc/{pid}/cmdline', 'rb') as f:
                    cmdline = f.read().replace(b'\x00', b' ').decode(errors='replace')
            except OSError:
                continue
            if (needle_path and needle_path in cmdline) or needle_name in cmdline:
                matching.append(pid)
        return matching

    def _kill_orphan_conky(self):
        killed = 0
        for pid in self._find_conky_pids():
            if self.conky_process and pid == self.conky_process.pid:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                self.log_action("WARNING", f"Sent SIGTERM to conky PID {pid}")
                killed += 1
            except ProcessLookupError:
                pass
            except PermissionError:
                self.log_action("WARNING", f"Cannot kill conky PID {pid}: permission denied")
        return killed

    def _stop_conky(self):
        tracked = self.conky_process
        self.conky_process = None

        if tracked is not None and tracked.poll() is None:
            try:
                tracked.terminate()
                try:
                    tracked.wait(timeout=2)
                    self.log_action("INFO", "Conky stopped")
                except subprocess.TimeoutExpired:
                    self.log_action("WARNING", "Conky didn't exit on SIGTERM, sending SIGKILL")
                    tracked.kill()
                    try:
                        tracked.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        self.log_action("ERROR", "Conky survived SIGKILL — giving up")
            except Exception as e:
                self.log_action("ERROR", f"Conky stop failed: {e}")

        killed = self._kill_orphan_conky()
        if killed:
            self.log_action("INFO", f"Cleaned up {killed} orphan conky process(es)")

    def _reshape_verse(self, text):
        if not text:
            return ""
        if not hasattr(self, "_reshape_func"):
            try:
                from importlib.util import spec_from_file_location, module_from_spec
                path = os.path.join(config.CONKY_DIR, "reshape_arabic.py")
                spec = spec_from_file_location("_quran_reshape_arabic", path)
                module = module_from_spec(spec)
                spec.loader.exec_module(module)
                self._reshape_func = module.reshape_and_wrap_arabic_text
            except Exception as e:
                self.log_action("WARNING", f"Failed to load reshape_arabic: {e}")
                self._reshape_func = None
        if self._reshape_func is None:
            return ""
        try:
            return self._reshape_func(text, 100)
        except Exception as e:
            self.log_action("WARNING", f"Arabic reshape failed: {e}")
            return ""

    def _write_verse_file(self, text):
        tmpdir = tempfile.gettempdir()
        raw_path = os.path.join(tmpdir, "quran_verse.txt")
        reshaped_path = os.path.join(tmpdir, "quran_verse_reshaped.txt")
        reshaped = self._reshape_verse(text)

        for path, content in ((raw_path, text), (reshaped_path, reshaped)):
            try:
                fd, temp_name = tempfile.mkstemp(dir=tmpdir, prefix=".quran_verse_")
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        f.write(content)
                    os.replace(temp_name, path)
                except Exception:
                    try:
                        os.unlink(temp_name)
                    except Exception:
                        pass
                    raise
            except Exception as e:
                self.log_action("ERROR", f"Failed to write {path}: {e}")

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

        remaining = self._find_conky_pids()
        if remaining:
            self.error_msg = (
                "conky still running after conky_off: PID(s) "
                + ", ".join(map(str, remaining))
            )
            self.log_action("ERROR", self.error_msg)
            return False
        return True

    def handle_conky_toggle(self):
        if self.conky_enabled:
            return self.handle_conky_off()
        return self.handle_conky_on()

