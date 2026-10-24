
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

import warnings
warnings.filterwarnings("ignore", message=".*avx2 capable.*", category=RuntimeWarning)

import sys
import socket
import threading
import time
import signal

import portalocker

from datetime import datetime

import quran_search
from audio_player import AudioPlayer
from config_manager import config

from quran_data import SURAH_AYAT
from daemon_utils import is_daemon_running, cleanup_orphaned_files
from logging_utils import LoggingMixin
from state_manager import StateMixin
from conky_manager import ConkyMixin
from playback_controller import PlaybackMixin
from status_reports import StatusMixin, about


def _recv_all(sock):
    """Read from sock until the peer closes; return decoded bytes."""
    chunks = []
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks).decode()


class Daemon(LoggingMixin, StateMixin, ConkyMixin, PlaybackMixin, StatusMixin):

    surah_ayat = SURAH_AYAT

    def __init__(self):
        # Per-thread error state so concurrent clients don't see each
        # other's error messages.
        self._tls = threading.local()

        self.running = False
        self.log_lock = threading.Lock()
        self.state_lock = threading.Lock()

        self.valid_commands = [
            "play", "pause", "resume", "toggle", "stop", "load",
            "repeat", "repeat_off", "dir", "ns", "ps", "goto",
            "prev", "next", "status", "config", "log",
            "conky_on", "conky_off", "conky_toggle",
            "reload_config",
            "conky_config", "conky_config_defaults",
            "conky_config_set", "conky_config_reset",
            "config_get", "config_defaults", "config_set",
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

    # ------------------------------------------------------------------ error_msg
    @property
    def error_msg(self):
        return getattr(self._tls, 'error_msg', '')

    @error_msg.setter
    def error_msg(self, value):
        self._tls.error_msg = value

    # ------------------------------------------------------------------ client protocol
    def handle_client(self, conn):
        try:
            conn.settimeout(5.0)
            MAX_BYTES = 65536
            PAYLOAD_COMMANDS = ("config_set", "conky_config_set")

            # Phase 1: read until we have a complete first line (or EOF / oversize).
            buf = b""
            while b"\n" not in buf and len(buf) < MAX_BYTES:
                try:
                    chunk = conn.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                buf += chunk

            if not buf:
                try:
                    conn.sendall(b"ERROR: Empty command\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            if len(buf) > MAX_BYTES:
                try:
                    conn.sendall(b"ERROR: Command too large\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            first_line, sep, remainder = buf.partition(b"\n")
            parts = first_line.decode().strip().split(maxsplit=1)
            command = parts[0] if parts else ""
            args = parts[1] if len(parts) > 1 else ""

            # Phase 2: payload commands read until EOF (client sends SHUT_WR).
            if command in PAYLOAD_COMMANDS:
                payload_chunks = [remainder] if remainder else []
                total = len(buf)
                while True:
                    try:
                        chunk = conn.recv(4096)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_BYTES:
                        try:
                            conn.sendall(b"ERROR: Command too large\n")
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        return
                    payload_chunks.append(chunk)
                payload = b"".join(payload_chunks).decode()
                args = (args + "\n" + payload) if args else payload

            if not command:
                try:
                    conn.sendall(b"ERROR: Empty command\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            if command == "status":
                try:
                    conn.sendall(self.handle_status().encode() + b"\n")
                except BrokenPipeError:
                    self.log_action("WARNING", "Client disconnected before receiving status")
                return

            # Commands that return raw text payloads (JSON or rendered config),
            # not OK/ERROR.
            if command in ("conky_config", "conky_config_defaults",
                           "config_get", "config_defaults"):
                try:
                    data = getattr(self, f"handle_{command}")()
                    conn.sendall(data.encode() + b"\n")
                except BrokenPipeError:
                    self.log_action("WARNING",
                                    f"Client disconnected before receiving {command}")
                except Exception as e:
                    try:
                        conn.sendall(f"ERROR: {e}\n".encode())
                    except BrokenPipeError:
                        pass
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
                buf_out = io.StringIO()
                with redirect_stdout(buf_out):
                    about()
                try:
                    conn.sendall(buf_out.getvalue().encode() + b"\n")
                except BrokenPipeError:
                    self.log_action("WARNING", "Client disconnected before receiving about")
                return

            # Clear any stale error from a previous command (or from the
            # main-loop's handle_playback_end) before dispatching.
            self.error_msg = ""

            if command == "load":
                if not args:
                    conn.sendall(b"ERROR: Missing surah:ayah\n")
                    return
                success = self.handle_load(args)
            elif command == "conky_config_set":
                if not args:
                    conn.sendall(b"ERROR: Missing JSON payload\n")
                    return
                success = self.handle_conky_config_set(args)
            elif command == "config_set":
                if not args:
                    conn.sendall(b"ERROR: Missing config text\n")
                    return
                success = self.handle_config_set(args)
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
                if success:
                    conn.sendall(b"OK\n")
                else:
                    msg = self.error_msg or "Command failed (no details)"
                    conn.sendall(f"ERROR: {msg}\n".encode())
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

    if args.command == "start":
        if is_daemon_running():
            print("Error: Daemon already running")
            sys.exit(1)
        Daemon().handle_start()

    elif args.command == "stop":
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(5)
            client.connect(config.SOCKET_FILE)
            client.sendall(b"stop\n")
            print(_recv_all(client).strip())
        except (ConnectionRefusedError, FileNotFoundError):
            print("Error: Daemon unavailable")
            sys.exit(1)

    elif args.command == "info":
        if not is_daemon_running():
            print(Daemon().handle_info())
        else:
            try:
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(5)
                client.connect(config.SOCKET_FILE)
                client.sendall(b"info\n")
                print(_recv_all(client).strip())
            except (ConnectionRefusedError, FileNotFoundError):
                print(Daemon().handle_info())

    elif args.command == "cleanup":
        cleanup_orphaned_files()
        print("Orphaned files cleaned up")

    elif args.command in ("about", "help"):
        about()

    elif args.command == "config":
        Daemon().handle_config()
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
                client.sendall(f"load {args.verse}\n".encode())
            elif args.command == "repeat":
                client.sendall(f"repeat {args.range}\n".encode())
            elif args.command == "goto":
                client.sendall(f"goto {args.ayah}\n".encode())
            elif args.command == "dir":
                client.sendall(f"dir {args.path}\n".encode())
            elif args.command == "conky_config_set":
                payload = args.json_config
                if payload == "-":
                    payload = sys.stdin.read().strip()
                    if not payload:
                        print("Error: no JSON on stdin", file=sys.stderr)
                        sys.exit(1)
                client.sendall(f"conky_config_set\n{payload}".encode())
                client.shutdown(socket.SHUT_WR)
            elif args.command == "config_set":
                payload = args.config_text
                if payload == "-":
                    payload = sys.stdin.read()
                    if not payload.strip():
                        print("Error: no config text on stdin", file=sys.stderr)
                        sys.exit(1)
                client.sendall(f"config_set\n{payload.rstrip()}".encode())
                client.shutdown(socket.SHUT_WR)
            else:
                client.sendall(f"{args.command}\n".encode())

            print(_recv_all(client).strip())
        except (ConnectionRefusedError, FileNotFoundError):
            print("Error: Daemon unavailable")
            sys.exit(1)


if __name__ == "__main__":
    main()

