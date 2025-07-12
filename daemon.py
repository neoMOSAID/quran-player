

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1' 
import sys
import socket
import threading
import inspect
import time
from datetime import datetime
import pygame
import psutil
import portalocker
import json
import tempfile
import shutil
import subprocess
import configparser
import signal
from collections import deque
from pathlib import Path



import quran_search
import arabic_topng
from audio_player import AudioPlayer
from config_manager import config  


# Log Level Mapping (keep as these are constants)
LOG_LEVELS = {
    "CRITICAL": 50,
    "ERROR": 40,
    "WARNING": 30,
    "INFO": 20,
    "DEBUG": 10,
    "DISABLED": 0,
}

# Critical messages (must always be logged)
CRITICAL_FLAGS = {"CRITICAL", "ERROR"}



class Daemon:
    def __init__(self):
        self.running = False
        self.error_msg = ""
        self.log_lock = threading.Lock()
        self.state_lock = threading.Lock()

        self.valid_commands = ["play", "pause", "resume", "toggle", "stop", "load", 
                                "repeat", "repeat_off", "dir",
                               "prev", "next", "start", "status", "config", "log"]

        # Surah-ayah count mapping (index 0 unused, 1-114 are surah numbers)
        self.surah_ayat = [
            0,   # Index 0 (unused)
            7,   286, 200, 176, 120, 165, 206, 75, 129, 109,
            123, 111, 43, 52, 99, 128, 111, 110, 98, 135,
            112, 78, 118, 64, 77, 227, 93, 88, 69, 60,
            34,  30,  73,  54, 45, 83, 182, 88, 75, 85,
            54,  53,  89,  59, 37, 35, 38, 29, 18, 45,
            60,  49,  62,  55, 78, 96, 29, 22, 24, 13,
            14,  11,  11,  18, 12, 12, 30, 52, 52, 44,
            28,  28,  20,  56, 40, 31, 50, 40, 46, 42,
            29,  19,  36,  25, 22, 17, 19, 26, 30, 20,
            15,  21,  11,  8, 8, 19, 5, 8, 8, 11,
            11,  8,   3,   9, 5, 4, 7, 3, 6, 3,
            5,   4,   5,   6  # Complete with all 114 values
        ]

        # Load configuration
        self.audio_base = config.get('daemon', 'FILES_DIRECTORY', config.SAMPLE_DIR)
        self.view_image = config.getboolean('image', 'ENABLE', True)

        # Image display settings
        if sys.platform not in {'linux', 'linux2'}:
            self.view_image = False
            self.log_action("WARNING", "Image display disabled - requires Linux")
        
        # Initialize audio player
        self.state_file = config.STATE_FILE
        self.audio_player = None
        self.current_verse = (1, 0)  # (surah, ayah)
        self.repeat_range = None  # (start, end) or None

        # Image display process
        self.feh_process = None 
        
        # Load previous state
        self.load_playback_state()
        
    def handle_dir(self, path):
        """Change audio directory and reload if playing"""
        # Validate path
        if not os.path.isdir(path):
            self.log_action("ERROR", f"Invalid directory: {path}")
            return False
            
        # Update configuration
        config.set('daemon', 'FILES_DIRECTORY', path)
        self.audio_base = path  # Update local reference
        
        # Reload current verse if playing
        if self.audio_player.state in ("playing", "paused") and self.current_verse:
            self.log_action("INFO", f"Reloading audio from new directory: {path}")
            current_verse = self.current_verse
            self.audio_player.stop()
            return self.play_verse(current_verse)
        
        return True

    def log_action(self, flag, msg):
        """Log an action based on log level settings."""
        # Retrieve log level from config
        log_level_str = config.get("daemon", "LOG_LEVEL", "INFO").upper()
        log_level = LOG_LEVELS.get(log_level_str, 20)

        # Determine message priority
        message_priority = LOG_LEVELS.get(flag, 20)  # Default to INFO if unknown flag

        # Skip logging if below the configured level (except for critical messages)
        if message_priority < log_level and flag not in CRITICAL_FLAGS:
            return

        # Get calling method dynamically
        method = inspect.currentframe().f_back.f_code.co_name
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        pid = os.getpid()
        
        log_entry = f"{timestamp}|{pid}|{method}|{flag}|{msg}\n"

        # Choose log file
        log_path = config.CLIENT_LOG_FILE if method == "handle_client" and flag == "ERROR" else config.LOG_FILE

        # Rotate log if needed
        self.rotate_log_if_needed(log_path)

        # Write to log file
        try:
            with open(log_path, "a") as log:
                log.write(log_entry)
        except IOError as e:
            print(f"Failed to write to log: {str(e)}", file=sys.stderr)

    def rotate_log_if_needed(self, logfile):
        """Rotate log file if it exceeds configured maximum size"""
        max_size = config.getint('daemon', 'MAX_LOG_SIZE', 1000000)

        with self.log_lock:
            try:
                if os.path.exists(logfile) and os.path.getsize(logfile) >= max_size:
                    # Rotate logs
                    rotated_log = f"{logfile}.1"
                    
                    # Remove old rotated log if exists
                    if os.path.exists(rotated_log):
                        os.remove(rotated_log)
                    
                    # Rotate current log
                    os.rename(logfile, rotated_log)
                    
                    # Log the rotation
                    with open(logfile, "w") as new_log:
                        new_log.write(f"{datetime.now().isoformat()}|SYSTEM|LOG|Rotated log file\n")
            except Exception as e:
                print(f"Log rotation failed: {str(e)}", file=sys.stderr)

    def show_verse_image(self, text, highlight_line=None):
        """Show verse image in single feh instance with auto-reload"""
        output_path = os.path.join(tempfile.gettempdir(), "quran_verse.png")
        
        # Generate new image - FIX: Use config.config to get the ConfigParser object
        success = arabic_topng.render_arabic_text_to_image(
            text=text,
            output_path=output_path,
            config=config.config,  # FIX: Use config.config instead of config
            highlight_line=highlight_line
        )
        
        if not success:
            return

        try:
            # Try to reload existing feh instance
            if self.feh_process and (self.feh_process.poll() is None):
                os.kill(self.feh_process.pid, signal.SIGUSR1)
                self.log_action("INFO", "Reloaded existing feh window")
                return
        except (ProcessLookupError, AttributeError):
            # Process dead or not exists, start new
            pass

        # Start new feh instance with clean options
        try:
            self.feh_process = subprocess.Popen([
                'feh',
                '--image-bg', 'none',
                '--no-menus',
                '--auto-zoom',
                '--title', 'QuranPlayer',  # Unique window title
                output_path
            ])
            self.log_action("INFO", "Launched new feh window")
        except (FileNotFoundError, subprocess.CalledProcessError):
            self.log_action("ERROR", "feh not installed!")

    def load_playback_state(self):
        """Load playback state from previous session"""
        state = configparser.ConfigParser()
        if os.path.exists(self.state_file):
            state.read(self.state_file)
            try:
                surah = state.getint('state', 'surah', fallback=1)
                ayah = state.getint('state', 'ayah', fallback=0)
                if self.is_valid_verse(surah, ayah):
                    self.current_verse = (surah, ayah)
                else:
                    self.current_verse = (1, 0)  # Reset to default if invalid
            except (ValueError, TypeError) as e:
                self.log_action("ERROR", f"Corrupted state file: {e}. Using defaults")
                self.current_verse = (1, 0)

    def save_playback_state(self):
        """Persist current playback state"""
        surah, ayah = self.current_verse
        state = configparser.ConfigParser()
        state['state'] = {
            'surah': str(surah),
            'ayah': str(ayah)
        }
        
        # Create temp file in same directory as state file
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
            except:
                pass

    def handle_playback_end(self):
        """Automatically advance to next verse when playback completes"""
        if self.audio_player.state != "playing":
            return
        with self.state_lock:
            next_verse = self.get_next_verse()
            if next_verse:
                self.current_verse = next_verse
                self.save_playback_state()
                self.play_verse(next_verse)


    def handle_playback_events(self):
        """Check for playback completion without using pygame events"""
        # Only check if we're supposed to be playing
        if self.audio_player.state == "playing":
            # Check if music has finished playing
            try:
                if not pygame.mixer.music.get_busy():
                    self.handle_playback_end()
            except pygame.error:
                # Handle audio system errors
                self.log_action("WARNING", "Audio system error, reinitializing")
                self.audio_player.init_audio()


    def is_valid_verse(self, surah, ayah):
        """Validate surah and ayah numbers"""
        if not (1 <= surah <= 114):
            return False
        if ayah < 0 or ayah > self.surah_ayat[surah]:
            return False
        return True


    def get_next_verse(self):
        """Calculate next verse based on repeat settings"""
        surah, ayah = self.current_verse
        
        if self.repeat_range:
            start, end = self.repeat_range
            next_ayah = ayah + 1
            if next_ayah > end:
                next_ayah = start
            return (surah, next_ayah)
        else:
            next_ayah = ayah + 1
            max_ayah = self.surah_ayat[surah]
            
            if next_ayah > max_ayah:
                next_surah = surah + 1
                if next_surah > 114:
                    next_surah = 1
                return (next_surah, 0)
            return (surah, next_ayah)

    def play_verse(self, verse):
        """Play specific verse"""
        surah, ayah = verse
        audio_path = self.audio_player.get_audio_path(surah, ayah)
        
        if audio_path:
            # Generate text and image if needed
            if ayah:
                quran_text = quran_search.command_line_mode(surah, ayah, ayah,
                    quran_search.uthmani, quran_search.simplified, quran_search.chapters)
            else:
                quran_text = "بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ"
                
            if self.view_image:
                self.show_verse_image(quran_text)
                
            return self.audio_player.play(audio_path)
        else:
            self.log_action("ERROR", f"Audio file not found: {surah:03}{ayah:03}.mp3")
        return False


    # Simplified command handlers
    def handle_play(self):
        if self.audio_player.state == "paused":
            return self.audio_player.play(self.audio_player.current_audio_path)
        return self.play_verse(self.current_verse)
        
    def handle_pause(self):
        return self.audio_player.pause()
        
    def handle_stop(self):
        return self.audio_player.stop()
        
    def handle_toggle(self):
        return self.audio_player.toggle_pause()

    def handle_resume(self):
        """Alias for play command"""
        return self.handle_play()
        
    def get_prev_verse(self):
        """Calculate previous verse with boundary checks"""
        surah, ayah = self.current_verse
        
        # Handle underflow
        if ayah == 0:
            prev_surah = surah - 1
            if prev_surah < 1:
                prev_surah = 114  # Wrap to last surah
            prev_ayah = self.surah_ayat[prev_surah]
            return (prev_surah, prev_ayah)
        else:
            return (surah, ayah - 1)
        
    def handle_next(self):
        next_verse = self.get_next_verse()
        if next_verse:
            self.current_verse = next_verse
            self.save_playback_state()
            return self.play_verse(next_verse)
        return False
        
    def handle_load(self, args):
        """Load a surah or a specific verse"""
        try:
            parts = args.split(':')
            if len(parts) == 1:  # Only surah provided
                surah = int(parts[0])
                if not (1 <= surah <= 114):
                    raise ValueError("Invalid surah number")
                # For surah 9, start at verse 1, otherwise start at verse 0 (bismillah)
                ayah = 0 if surah != 9 else 1
                # If bismillah audio doesn't exist, start from verse 1
                if ayah == 0 and not self.audio_player.get_audio_path(surah, 0):
                    ayah = 1
                self.current_verse = (surah, ayah)
            elif len(parts) == 2:  # Both surah and ayah provided
                surah, ayah = map(int, parts)
                if not self.is_valid_verse(surah, ayah):
                    raise ValueError("Invalid verse")
                self.current_verse = (surah, ayah)
            else:
                raise ValueError("Invalid format")
                
            self.repeat_range = None  # Break repeat mode
            self.save_playback_state()
            return self.play_verse(self.current_verse)
        except ValueError as e:
            self.log_action("ERROR", f"Invalid load format: {str(e)}")
            return False

        
    def handle_stop(self):
        try:
            self.audio_player.stop()
            # Signal main thread to stop
            self.running = False
            # Close server socket to unblock accept() call
            if hasattr(self, 'server_socket') and self.server_socket:
                try:
                    self.server_socket.close()
                except:
                    pass
            return "OK: Daemon shutting down"
        except Exception as e:
            self.log_action("ERROR", f"Error during stop: {str(e)}")
            return f"ERROR: {str(e)}"

            


    def handle_config(self):
        """Write the default configuration to the user's config file."""
        # Remove incorrect references:
        config = configparser.ConfigParser()
        config.read_dict(config._get_default_config())  # Use singleton's default config
        
        # Write to file
        with open(config.USER_CONFIG_FILE, "w", encoding="utf-8") as configfile:
            config.write(configfile)
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

    def handle_status(self):
        """Return accurate playback status"""
        surah, ayah = self.current_verse
        repeat_info = {
            "repeat": self.repeat_range is not None,
            "repeat_start": 0,
            "repeat_end": 0,
            "repeat_surah": surah
        }
        
        if self.repeat_range:
            repeat_info["repeat_start"] = self.repeat_range[0]
            repeat_info["repeat_end"] = self.repeat_range[1]
        
        return json.dumps({
            "playing": self.audio_player.state == "playing",
            "paused": self.audio_player.state == "paused",
            "surah": surah,
            "ayah": ayah,
            **repeat_info,
            "daemon_running": True
        })

        
    def handle_client(self, conn):
        try:
            conn.settimeout(5.0)  # Add timeout
            data = conn.recv(1024).decode().strip()
            if not data:
                conn.sendall(b"ERROR: Empty command\n")
                return

            parts = data.split(maxsplit=1)
            command = parts[0]
            args = parts[1] if len(parts) > 1 else ''

            # Handle status command
            if command == "status":
                status_response = self.handle_status()
                try:
                    conn.sendall(status_response.encode() + b"\n")
                except BrokenPipeError:
                    self.log_action("WARNING", "Client disconnected before receiving status")
                return

            # Handle stop command separately
            if command == "stop":
                response = self.handle_stop()
                try:
                    conn.sendall(response.encode() + b"\n")
                except BrokenPipeError:
                    self.log_action("WARNING", "Client disconnected during stop")
                return  # Stop command doesn't wait for callback

            # Handle log command
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
                
            # Handle about/help command
            if command in ("about", "help"):
                import io
                from contextlib import redirect_stdout
                buf = io.StringIO()
                with redirect_stdout(buf):
                    about()  
                about_text = buf.getvalue()
                try:
                    conn.sendall(about_text.encode() + b"\n")
                except BrokenPipeError:
                    self.log_action("WARNING", "Client disconnected before receiving about info")
                return

            # Handle other commands
            if command == "load":
                if not args:
                    conn.sendall(b"ERROR: Missing surah:ayah\n")
                    return
                success = self.handle_load(args)
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

            # Send response
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
            except:
                pass

    def handle_start(self):
        if not self.verify_audio_config():
            sys.exit(1)

        if not self.audio_player:
            self.audio_player = AudioPlayer(config, self.log_action)

        cleanup_orphaned_files()

        signal.signal(signal.SIGTERM, self.handle_stop)

        with open(config.LOCK_FILE, 'w') as f:
            try:
                portalocker.lock(f, portalocker.LOCK_EX)
            except IOError:
                self.log_action("ERROR", "Daemon already running (locked)")
                sys.exit(1)

            if is_daemon_running():
                self.log_action("ERROR", "Daemon already running!")
                sys.exit(1)

        for f in [config.PID_FILE, config.SOCKET_FILE]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception as e:
                    self.log_action("ERROR", f"Cleanup failed: {str(e)}")
                    sys.exit(1)

        # Fixed variable name conflict
        with open(config.PID_FILE, "w") as pid_file:
            pid_file.write(str(os.getpid()))

        if os.path.exists(config.SOCKET_FILE):
            os.remove(config.SOCKET_FILE)

        if sys.platform == 'win32' and hasattr(socket, "AF_UNIX"):
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(r'\\.\pipe\quran-daemon')
            server.listen(5)  
            server.settimeout(1)  
        else:
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(config.SOCKET_FILE)
            server.listen(5)
            server.settimeout(1)

        self.server_socket = server

        self.log_action("INFO", "Daemon started. Listening for commands.")
        self.running = True
        print("OK")

        # Setup signal handlers
        def shutdown_handler(signum, frame):
            self.log_action("INFO", f"Received signal {signum}, shutting down")
            self.running = False
            
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

        try:
            while self.running:
                try:
                    # Handle client connections
                    conn, _ = server.accept()
                    threading.Thread(target=self.handle_client, args=(conn,)).start()
                except socket.timeout:
                    pass
                    
                # Handle playback events
                self.handle_playback_events()
                
                # Small sleep to prevent busy waiting
                time.sleep(0.05)
        except KeyboardInterrupt:
            self.log_action("INFO", "Daemon shutting down.")
        finally:
            self.cleanup(server)


    def cleanup(self, server):
        """Clean up resources with signal protection"""
        # Ignore interrupts during cleanup
        original_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
        original_term = signal.signal(signal.SIGTERM, signal.SIG_IGN)
        
        try:
            self.running = False
            self.audio_player.cleanup()
            
            # Close server socket
            try:
                server.shutdown(socket.SHUT_RDWR)
                server.close()
            except:
                pass
                
            # Remove control files
            for f in [config.LOCK_FILE, config.PID_FILE, config.SOCKET_FILE]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except:
                        pass
                        
            # Cleanup feh process
            # Ensure feh is terminated
            try:
                if self.feh_process and self.feh_process.poll() is None:
                    self.feh_process.terminate()
                    self.feh_process.wait(timeout=1.0)
                    self.log_action("INFO", "Feh process terminated")
            except Exception as e:
                self.log_action("ERROR", f"Feh termination failed: {str(e)}")
            
            self.log_action("INFO", "Cleanup completed.")
        finally:
            # Restore signal handlers
            signal.signal(signal.SIGINT, original_int)
            signal.signal(signal.SIGTERM, original_term)


    def handle_cleanup(self):
        """Handle new cleanup command"""
        cleanup_orphaned_files()
        print("Orphaned files removed")

    def handle_prev(self):
        """Play previous verse"""
        prev_verse = self.get_prev_verse()
        if prev_verse:
            self.current_verse = prev_verse
            self.save_playback_state()
            return self.play_verse(prev_verse)
        return False

    def handle_repeat_off(self):
        """Exit repeat mode without changing playback"""
        with self.state_lock:
            if self.repeat_range is not None:
                self.repeat_range = None
                self.log_action("INFO", "Repeat mode turned off")
                return True
            return False

    def handle_repeat(self, args):
        """Handle repeat command with verse range validation"""
        if args.lower() == "off":
            return self.handle_repeat_off()

        parts = args.split(':')
        try:
            if len(parts) == 1:  # Single argument: surah
                surah = int(parts[0])
                if not (1 <= surah <= 114):
                    raise ValueError("Invalid surah number")
                start = 1
                end = self.surah_ayat[surah]
                # Set current surah to the specified one
                self.current_verse = (surah, start)
                current_surah = surah
            elif len(parts) == 2:  # Two arguments: start:end (current surah)
                current_surah, current_ayah = self.current_verse
                start = int(parts[0])
                end = int(parts[1])
            elif len(parts) == 3:  # Three arguments: surah:start:end
                surah = int(parts[0])
                start = int(parts[1])
                end = int(parts[2])
                if not (1 <= surah <= 114):
                    raise ValueError("Invalid surah number")
                # Set current surah to the specified one
                self.current_verse = (surah, start)
                current_surah = surah
            else:
                raise ValueError("Invalid number of arguments")
        except ValueError as e:
            self.log_action("ERROR", f"Invalid repeat format: {str(e)}")
            self.error_msg = f"ERROR: {str(e)}"
            return False

        # Validate the range
        max_ayat = self.surah_ayat[current_surah]
        
        # Special case for bismillah (verse 0)
        if start == 0:
            if current_surah == 9:  # Surah At-Tawbah has no bismillah
                self.log_action("ERROR", "Surah 9 has no bismillah")
                self.error_msg = "ERROR: Surah 9 has no bismillah"
                return False
            # Only allow start=0 if end is at least 0
            if end < 0:
                end = 0
        else:
            # Normal verse validation
            if start < 1 or end > max_ayat:
                self.log_action("ERROR", f"Invalid range {start}-{end} for Surah {current_surah} (1-{max_ayat})")
                self.error_msg = f"Invalid range {start}-{end} for Surah {current_surah} (1-{max_ayat})"
                return False

        if start > end:
            self.log_action("ERROR", f"Start verse {start} > end verse {end}")
            self.error_msg = f"Start verse {start} > end verse {end}"
            return False

        # Verify all audio files exist in range
        for ayah in range(start, end+1):
            path = self.audio_player.get_audio_path(current_surah, ayah)
            if not path:
                self.log_action("ERROR", f"Missing audio file {current_surah}:{ayah}")
                self.error_msg = f"Missing audio file {current_surah}:{ayah}"
                return False

        self.repeat_range = (start, end)
        self.save_playback_state()
        
        return self.play_verse(self.current_verse)

    def handle_info(self):
        """Print detailed information about daemon status, configuration, and file integrity."""
        info_lines = []
        info_lines.append("╔════════════════════════════════════════════════════╗")
        info_lines.append("║         📖 Quran Player Daemon Information         ║")
        info_lines.append("╚════════════════════════════════════════════════════╝")

        # Daemon Status
        daemon_running = is_daemon_running()
        info_lines.append("\n[🟢 Daemon Status]")
        info_lines.append(f"  ├─ Status        : {'Running ✅' if daemon_running else 'Not Running ❌'}")
        info_lines.append(f"  └─ Current PID   : {os.getpid()}")

        # Playback Mode
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

        # Audio Files Directory
        info_lines.append("\n[📁 Audio Files]")
        info_lines.append(f"  └─ Directory     : {self.audio_base}")

        # Missing Audio Files
        missing_audio = []
        for filename in config.REQUIRED_FILES:
            path = os.path.join(self.audio_base, filename)
            if not os.path.exists(path):
                missing_audio.append(filename)

        if missing_audio:
            info_lines.append("  ⚠️  Missing Required Files:")
            for f in missing_audio:
                info_lines.append(f"    - {f}")
        else:
            info_lines.append("  ✅ All required files are present.")

        # Core Directories
        info_lines.append("\n[📂 Core Directories]")
        core_dirs = {
            "User Config"   : config.USER_CONFIG_DIR,
            "Control Dir"   : config.CONTROL_DIR,
            "Sample Dir"    : config.SAMPLE_DIR,
            "Script Dir"    : config.SCRIPT_DIR
        }
        for name, path in core_dirs.items():
            exists = "✅ Exists" if os.path.exists(path) else "❌ Missing"
            info_lines.append(f"  ├─ {name:13}: {path} ({exists})")

        # Core Files
        info_lines.append("\n[📄 Core Files]")
        core_files = {
            "Default Config" : config.DEFAULT_CONFIG_FILE,
            "Arabic Font"    : os.path.join(config.SCRIPT_DIR, "arabic-font.ttf")
        }
        for name, path in core_files.items():
            exists = "✅ Exists" if os.path.exists(path) else "❌ Missing"
            info_lines.append(f"  ├─ {name:14}: {path} ({exists})")

        # State File
        info_lines.append("\n[💾 Playback State File]")
        if os.path.exists(config.STATE_FILE):
            mtime = datetime.fromtimestamp(os.path.getmtime(config.STATE_FILE))
            info_lines.append(f"  └─ File          : {config.STATE_FILE}")
            info_lines.append(f"     Last Modified: {mtime}")
        else:
            info_lines.append(f"  └─ File          : {config.STATE_FILE} (❌ Missing)")

        # Log File
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

        # System Info
        info_lines.append("\n[💻 System Info]")
        info_lines.append(f"  ├─ Platform      : {sys.platform}")
        info_lines.append(f"  ├─ Python        : {sys.version.split()[0]}")
        info_lines.append(f"  └─ SDL_AUDIODRIVER: {os.environ.get('SDL_AUDIODRIVER', 'Not Set')}")

        # Surah Ayah Info
        if 1 <= current_surah < len(self.surah_ayat):
            total_ayah = self.surah_ayat[current_surah]
            info_lines.append(f"\n[🔢 Surah Info]")
            info_lines.append(f"  └─ Total Ayahs in Surah {current_surah}: {total_ayah}")
        else:
            info_lines.append("\n[🔢 Surah Info]")
            info_lines.append("  └─ Surah information unavailable in surah_ayat list.")

        return "\n".join(info_lines)


    def verify_audio_config(self):
        """Check for valid audio configuration"""
        if 'pulse' not in os.popen('pactl info').read():
            self.log_action("ERROR", "PulseAudio/PipeWire not running!")
            return False
        return True








def is_daemon_running():
    """Verify daemon is actually running with PID and process name"""
    if not os.path.exists(config.PID_FILE):
        return False

    try:
        with open(config.PID_FILE, "r") as f:
            pid = int(f.read().strip())

        # Check if process exists
        os.kill(pid, 0)  # Raises OSError if process doesn't exist

        # Get the script filename dynamically
        script_name = os.path.basename(__file__)

        # Linux-specific method (checking /proc)
        cmdline_path = Path(f"/proc/{pid}/cmdline")
        if cmdline_path.exists():
            cmdline = cmdline_path.read_bytes().decode().replace('\x00', ' ')
            return script_name in cmdline

        # Cross-platform fallback using psutil
        for proc in psutil.process_iter(['pid', 'cmdline']):
            if proc.info['pid'] == pid and proc.info['cmdline']:
                return script_name in ' '.join(proc.info['cmdline'])

    except (ValueError, OSError, FileNotFoundError, psutil.NoSuchProcess):
        return False

    return False


def cleanup_orphaned_files():
    """Remove PID/socket files if daemon not running"""
    if os.path.exists(config.PID_FILE) and not is_daemon_running():
        try:
            os.remove(config.PID_FILE)
            os.remove(config.SOCKET_FILE)
        except Exception as e:
            print(f"Cleanup warning: {str(e)}")


def about():
    """Generate formatted about information with command documentation"""
    about_info = f"""
    ┌──────────────────────────────────────────────────────┐
    │                  Quran Player Daemon                 │
    │                  Version 1.2.0                       │
    └──────────────────────────────────────────────────────┘

    A robust daemon for Quran audio playback with synchronized 
    visual display. Features include:
    
    • Verse-by-verse playback with auto-advance
    • Repeat a range of verses
    • Display current verse in feh
    • Cross-platform audio backend support
    • Persistent playback state
    • Arabic text rendering with proper shaping
    • Configurable through ~/.config/quran-player/config.ini
    
    ┌──────────────────────────────────────────────────────┐
    │                     Project Links                    │
    └──────────────────────────────────────────────────────┘
    
    \033]8;;https://quran-player.example.com\a🌐 Website\033]8;;\a
    \033]8;;https://github.com/user/quran-player\a🐙 GitHub Repository\033]8;;\a
    
    ┌──────────────────────────────────────────────────────┐
    │                 Supported Commands                   │
    └──────────────────────────────────────────────────────┘
    """

    commands = [
        ("start", "Initialize the daemon process"),
        ("stop", "Terminate the daemon"),
        ("play", "Resume audio playback"),
        ("pause", "Pause current playback"),
        ("prev", "Previous verse"),
        ("next", "Next verse"),
        ("load <surah>", "Load entire surah starting from beginning"),
        ("load <surah:ayah>", "Load specific verse"),
        ("repeat <range>", "Repeat verses: <surah>, <start:end>, or <surah:start:end>"),
        ("dir <path>", "Change audio directory and reload current verse"),
        ("status", "Get playback status"),
        ("cleanup", "Clean up orphaned runtime files"),
        ("config", "Generate and override user config file"),
        ("info", "info dump of all relevent data"),
        ("help", "Show this information"),
        ("about", "Show this information")
    ]

    cmd_list = "\n".join([f"  {cmd[0]:<18} {cmd[1]}" for cmd in commands])
    
    print(f"{about_info}\n{cmd_list}\n\n    © 2024 Quran Player Project - GPLv3 License")
    return True




def print_usage():
    print("Usage: quran-daemon <command>")
    print("Commands:")
    print("  start   - Start the daemon")
    print("  stop    - Stop the daemon")
    print("  play    - Play the track")
    print("  pause   - Pause playback")
    print("  prev    - Play previous track")
    print("  next    - Play next track")
    print("  load <surah>:<ayah>    - Load track")
    print("  repeat <start>:<end>    - repeat verses, load and play commands break repeat mode")
    print("  cleanup - Clean up files")
    print("  info    - info dump of all data ")
    print("  about   - Print info about this daemon")
    print("  help    - Print info about this daemon")
    print("  config  - Generate default config  and override user config file")

if __name__ == "__main__":
    
    daemon = Daemon()

    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]  # Get additional arguments

    if command == "start":
        if is_daemon_running():
            print("Error: Daemon already running")
            sys.exit(1)
        daemon.handle_start()

    elif command == "stop":
        # Special handling for stop command
        try:
            if sys.platform == 'win32':
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.settimeout(5)
                client.connect(('localhost', 58901))
            else:
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(5)
                client.connect(config.SOCKET_FILE)
                
            # Send stop command
            client.sendall(b"stop\n")
            # Get immediate response
            print(client.recv(1024).decode().strip())
        except (ConnectionRefusedError, FileNotFoundError):
            print("Error: Daemon unavailable")
            sys.exit(1)

    elif command == "info":
        info_str = daemon.handle_info()
        print(info_str)
    elif command == "cleanup":
        cleanup_orphaned_files()
    elif command == "about" or command == "help":
        about()
    elif command == "config":
        daemon.handle_config()
        print(f"Generated config at {config.USER_CONFIG_FILE}")
        
    elif command in daemon.valid_commands:
        if not is_daemon_running():
            print(f"Error: Daemon not running, Start it first with: quran-daemon start")
            sys.exit(1)

        try:
            if sys.platform == 'win32':
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.settimeout(5)
                client.connect(('localhost', 58901))
            else:
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(5)
                client.connect(config.SOCKET_FILE)
                
            # Send raw command string
            client.sendall((' '.join(sys.argv[1:])).encode() + b"\n")
            print(client.recv(1024).decode().strip())
                
        except (ConnectionRefusedError, FileNotFoundError):
            print("Error: Daemon unavailable")
            sys.exit(1)
            
    else:
        print_usage()
        sys.exit(1)






