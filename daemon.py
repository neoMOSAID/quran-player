
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

import warnings
warnings.filterwarnings("ignore", message=".*avx2 capable.*", category=RuntimeWarning)

import sys
import socket
import threading
import time
import signal

import pygame
import portalocker

import quran_search
from audio_player import AudioPlayer
from config_manager import config
from version import VERSION

from quran_data import SURAH_AYAT
from daemon_utils import is_daemon_running, cleanup_orphaned_files
from logging_utils import LoggingMixin
from state_manager import StateMixin
from conky_manager import ConkyMixin
from playback_controller import PlaybackMixin
from status_reports import StatusMixin, about


class Daemon(LoggingMixin, StateMixin, ConkyMixin, PlaybackMixin, StatusMixin):
    surah_ayat = SURAH_AYAT

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

        self.audio_base = config.get('daemon', 'FILES_DIRECTORY', config.SAMPLE_DIR)
        self.conky_enabled = config.getboolean('conky', 'enable', True)

        self.state_file = config.STATE_FILE
        self.audio_player = None
        self.current_verse = (1, 0)
        self.repeat_range = None
        self.conky_process = None
        self._lock_handle = None

        self.load_playback_state()

    # ------------------------------------------------------------------ client protocol
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
    def handle_stop(self):
        """Stop the daemon gracefully — conky shut down synchronously."""
        try:
            self.audio_player.stop()
            self.save_playback_state()
            self._stop_conky()
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

        try:
            self._lock_handle = open(config.LOCK_FILE, 'w')
            portalocker.lock(self._lock_handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except (IOError, OSError, portalocker.LockException):
            self.log_action("ERROR", "Daemon already running (locked)")
            sys.exit(1)

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
        os.chmod(config.SOCKET_FILE, 0o600)
        server.listen(5)
        server.settimeout(1)

        self.server_socket = server
        self.log_action("INFO", "Daemon started. Listening for commands.")
        self.running = True

        if self.conky_enabled:
            self._start_conky()

        # Ensure daemon.log exists even when log_level is above INFO, so
        # `qd info` and `qd log` always have something to read.
        if not os.path.exists(config.LOG_FILE):
            try:
                with open(config.LOG_FILE, 'a') as f:
                    f.write(
                        f"{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
                        f"|{os.getpid()}|handle_start|INFO|Daemon started\n"
                    )
            except IOError:
                pass
            
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
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    from cli_parser import build_parser

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    daemon = Daemon()

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


if __name__ == "__main__":
    main()

