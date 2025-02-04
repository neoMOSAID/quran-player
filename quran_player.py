import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1' 
import sys
import socket
import threading
import configparser
import inspect
import time
from datetime import datetime
from threading import Lock
from pathlib import Path
import pygame
import fcntl
import shutil
import subprocess
import signal


import quran_search
import arabic_topng

# Define global variables
# directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONTROL_DIR =  os.path.join(SCRIPT_DIR, "control")
USER_CONFIG_DIR = os.path.expanduser("~/.config/quran-player")

# daemon files
LOG_FILE = os.path.join(CONTROL_DIR, "daemon.log")
SOCKET_FILE = os.path.join(CONTROL_DIR, "daemon.sock")
PID_FILE = os.path.join(CONTROL_DIR, "daemon.pid")
LOCK_FILE = os.path.join(CONTROL_DIR, "daemon.lock")
DEFAULT_CONFIG_FILE = os.path.join(SCRIPT_DIR, "default_config.ini")

# user files
USER_CONFIG_FILE = os.path.join(USER_CONFIG_DIR, "config.ini")
STATE_FILE =  os.path.join(USER_CONFIG_DIR, "playback_state.ini")

AUDIO_SOURCE_DIR = os.path.join(SCRIPT_DIR, "audio")
SAMPLE_DIR = os.path.join(USER_CONFIG_DIR, "sample")

REQUIRED_FILES = [
    "001000.mp3", "001001.mp3", "001002.mp3", "001003.mp3", "001004.mp3", "001005.mp3", "001006.mp3", "001007.mp3",
    "002000.mp3", "002001.mp3", "002002.mp3", "002003.mp3", "002004.mp3", "002005.mp3", "002006.mp3", "002007.mp3", "002008.mp3", "002009.mp3", "002010.mp3"
]

def ensure_dirs():
    """Ensure directories exist and required audio files are present."""
    os.makedirs(USER_CONFIG_DIR, exist_ok=True)
    os.makedirs(CONTROL_DIR, exist_ok=True)
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    
    for filename in REQUIRED_FILES:
        dest_file = os.path.join(SAMPLE_DIR, filename)
        src_file = os.path.join(AUDIO_SOURCE_DIR, filename)
        
        if not os.path.exists(dest_file):
            if os.path.exists(src_file):
                shutil.copy2(src_file, dest_file)
                print(f"Copied: {filename}")
            else:
                print(f"Missing source file: {src_file}")




class Daemon:
    def __init__(self):
        self.running = False
        self.audio_lock = threading.Lock()
        self.valid_commands = {
            "start": "SYSTEM",
            "stop": "SYSTEM",
            "cleanup": "SYSTEM",
            "play": "PLAY",
            "pause": "NAV",
            "prev": "NAV",
            "next": "NAV",
            "load": "NAV",
            "status": "INFO",
            "config": "SYSTEM",
        }
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

        ensure_dirs()
        self.config = self.load_config()

        # State management
        self.current_surah = 1
        self.current_ayah = 1
        self.state_file = STATE_FILE

        self.current_playback = None
        self.resources_initialized = False  # Track initialization state of pygame
        # Add pause state tracking
        self.is_paused = False
        self.feh_process = None 
        # Initialize mixer with buffer settings
        # Initialize pygame only once
        if not pygame.get_init():
            pygame.init()
            pygame.mixer.init(frequency=44100, buffer=1024)
            
        # Load previous state
        self.load_playback_state()

        # Audio configuration
        self.audio_base = os.path.join(
            self.config.get('daemon', 'FILES_DIRECTORY',
                          fallback=os.path.join(USER_CONFIG_DIR, "sample/"))
        )

    def log_action(self, flag, msg):
        """Log an action with timestamp, PID, method, flag, and message."""
        method = inspect.currentframe().f_back.f_code.co_name
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        pid = os.getpid()
        log_entry = f"{timestamp}|{pid}|{method}|{flag}|{msg}\n"
        with open(LOG_FILE, "a") as log:
            log.write(log_entry)
        #print(log_entry.strip())


    def initialize_pygame(self):
        """Safely initialize pygame resources once"""
        if not pygame.get_init() and not self.resources_initialized:
            pygame.init()
            pygame.mixer.init(frequency=44100, buffer=1024)
            self.resources_initialized = True
            self.log_action("SYSTEM", "Pygame initialized")


    def get_default_config(self):
        """Return a dictionary of default configuration values for all sections."""
        return {
            "daemon": {
                "MAX_LOG_SIZE": 1000000,
                "LOG_LEVEL": "INFO",
                "FILES_DIRECTORY": os.path.join(USER_CONFIG_DIR, "sample"),
            },
            "image": {
                "default_resolution": "1240x170",
                "FONT_FILE": "Amiri",
                "FONT_SIZE": 48,
                "IMAGE_WIDTH": 1240,
                "WRAP_WIDTH": 170,
                "VERTICAL_PADDING": 20,
                "BG_COLOR": "0,0,0,0",
                "TEXT_COLOR": "255,255,255,255",
                "HIGHLIGHT_COLOR": "255,0,0,255",
            },
            # Add new sections as needed
        }


    def validate_config_value(self, section, key, value, default_value):
        """Validate and convert the config value for a given section and key."""
        validated_value = default_value  # Fallback to default

        try:
            if key == "MAX_LOG_SIZE":
                validated_value = int(value)
                if validated_value <= 0:
                    raise ValueError("Must be positive.")
            elif key == "FILES_DIRECTORY":
                if os.path.isdir(value):
                    validated_value = value
                else:
                    raise ValueError("Invalid files directory.")
            elif key == "default_resolution":
                # Validate resolution format (e.g., '1920x1080')
                parts = value.split('x')
                if len(parts) != 2 or not all(part.isdigit() for part in parts):
                    raise ValueError("Invalid resolution format.")
                validated_value = value
            elif key in ["FONT_FILE", "BG_COLOR", "TEXT_COLOR", "HIGHLIGHT_COLOR"]:
                validated_value = str(value)
            elif key in ["FONT_SIZE", "IMAGE_WIDTH", "WRAP_WIDTH", "VERTICAL_PADDING"]:
                validated_value = int(value)
                if validated_value <= 0:
                    raise ValueError("Must be positive.")
            else:
                # For keys without specific validation, keep as-is
                validated_value = value
        except (ValueError, TypeError, AttributeError) as e:
            self.log_action("WARNING",
                f"Invalid value for {section}.{key}: {value} ({str(e)}). Using default: {default_value}.")
            validated_value = default_value

        return validated_value


    def load_config(self):
        """Load configuration from defaults and user config, validating values."""
        defaults = self.get_default_config()
        config = configparser.ConfigParser()

        # Populate config with defaults
        for section in defaults:
            config[section] = {}
            for key, value in defaults[section].items():
                config[section][key] = str(value)

        # Read user config if available
        if os.path.exists(USER_CONFIG_FILE):
            config.read(USER_CONFIG_FILE)
            self.log_action("SYSTEM", f"Loaded user config from {USER_CONFIG_FILE}")
        else:
            self.log_action("WARNING", "No user config found. Using defaults.")

        # Validate each configuration value
        for section in defaults:
            for key in defaults[section]:
                default_value = defaults[section][key]
                current_value = config.get(section, key, fallback=str(default_value))

                # Validate and convert the value
                validated_value = self.validate_config_value(
                    section, key, current_value, default_value
                )
                config.set(section, key, str(validated_value))

        return config

    def handle_config(self):
        """Write the default configuration to the user's config file."""
        ensure_dirs()
        defaults = self.get_default_config()
        config = configparser.ConfigParser()

        # Populate with default values
        for section in defaults:
            config[section] = {}
            for key, value in defaults[section].items():
                config[section][key] = str(value)

        # Write to file
        with open(USER_CONFIG_FILE, "w") as configfile:
            config.write(configfile)
        self.log_action("SYSTEM", f"Default config generated at {USER_CONFIG_FILE}")

    def handle_command(self, command):
        """Process a received command using dedicated handler methods."""
        if command not in self.valid_commands:
            self.log_action("ERROR", f"Unknown command: {command}")
            return

        # Get the handler method using naming convention
        handler_name = f"handle_{command}"
        handler = getattr(self, handler_name, None)

        if not handler:
            self.log_action("ERROR", f"No handler implemented for {command}")
            return

        # Execute the command with proper logging
        self.log_action(self.valid_commands[command], f"Executing command: {command}")
        handler()

    def handle_client(self, conn):
        try:
            data = conn.recv(1024).decode().strip()
            if not data:
                conn.sendall(b"ERROR: Empty command\n")
                return

            parts = data.split(maxsplit=1)
            command = parts[0]
            args = parts[1] if len(parts) > 1 else ''

            # Handle status command first
            if command == "status":
                status_response = self.handle_status()
                conn.sendall(status_response.encode() + b"\n")
                return  
            
            if command == "load":
                if not args:
                    conn.sendall(b"ERROR: Missing surah:ayah\n")
                    return
                success = self.handle_load(args)
            elif command in ["play", "pause", "stop", "prev", "next","start","status"]:
                success = getattr(self, f"handle_{command}")()
            else:
                conn.sendall(b"ERROR: Unknown command\n")
                return

            # Send OK/ERROR based on success
            response = b"OK\n" if success else b"ERROR: Command failed\n"
            conn.sendall(response)

        except Exception as e:
            self.log_action("ERROR", f"Client error: {str(e)}")
            conn.sendall(f"ERROR: {str(e)}\n".encode())
        finally:
            conn.close()


    def handle_start(self):
        """Safe daemon startup with file lock to prevent races"""
        cleanup_orphaned_files()

        # Use a lock file to prevent multiple instances
        with open(LOCK_FILE, 'w') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError:
                self.log_action("ERROR", "Daemon already running (locked)")
                sys.exit(1)

            if is_daemon_running():
                self.log_action("ERROR", "Daemon already running!")
                sys.exit(1)

        # Double-check cleanup before creating files
        for f in [PID_FILE, SOCKET_FILE]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception as e:
                    self.log_action("ERROR", f"Cleanup failed: {str(e)}")
                    sys.exit(1)

        # Write PID file atomically
        with open(PID_FILE, "w") as pid_file:
            pid_file.write(str(os.getpid()))

        if os.path.exists(SOCKET_FILE):
            os.remove(SOCKET_FILE)

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_FILE)
        server.listen(5)
        server.settimeout(1)  # Add timeout to break accept() blocking

        self.log_action("SYSTEM", "Daemon started. Listening for commands.")
        self.running = True

        try:
            while self.running:
                try:
                    conn, _ = server.accept()
                    threading.Thread(target=self.handle_client, args=(conn,)).start()
                except socket.timeout:
                    # Timeout allows checking self.running periodically
                    continue
        except KeyboardInterrupt:
            self.log_action("SYSTEM", "Daemon shutting down.")
        finally:
            self.cleanup(server)

    def cleanup_resources(self):
        """Cleanup only if resources were initialized"""
        if self.resources_initialized:
            self.log_action("SYSTEM", "Cleaning up pygame resources")
            pygame.mixer.quit()
            pygame.quit()
            self.resources_initialized = False  # Reset state
        
        #Cleanup feh process on exit
        if self.feh_process and self.feh_process.poll() is None:
            self.feh_process.terminate()
            self.feh_process.wait()

    def cleanup(self, server):
        """Clean up resources."""
        server.close()
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        if os.path.exists(SOCKET_FILE):
            os.remove(SOCKET_FILE)
        if self.feh_process and self.feh_process.poll() is None:
            self.feh_process.terminate()
            self.feh_process.wait()
        self.log_action("SYSTEM", "Cleanup completed.")

    def handle_cleanup(self):
        """Handle new cleanup command"""
        cleanup_orphaned_files()
        print("Orphaned files removed")

    def handle_stop(self):
        """Handle stop command."""
        self.running = False
        self.log_action("SYSTEM", "Shutdown initiated")
        return True

    def handle_play(self):
        """Handle play command with success return"""
        print("Handling play command")
        try:
            return self.play_audio()
        except Exception as e:
            self.log_action("ERROR", f"Play failed: {str(e)}")
            return False
    def handle_status(self):
        """Return current playback status in pipe-separated format"""
        status = "PAUSED" if self.is_paused else "PLAYING"
        return f"STATUS|{self.current_surah}|{self.current_ayah}|{status}"

    def handle_pause(self):
        """Toggle pause state with proper state tracking"""
        try:
            with self.audio_lock:
                if pygame.mixer.music.get_busy() and not self.is_paused:
                    pygame.mixer.music.pause()
                    self.is_paused = True
                    self.log_action("PAUSE", "Playback paused")
                else:
                    pygame.mixer.music.unpause()
                    self.is_paused = False
                    self.log_action("PLAY", "Playback resumed")
                return True
        except pygame.error as e:
            self.log_action("ERROR", f"Pause failed: {str(e)}")
            return False

    def handle_prev(self):
        """Previous ayah with boundary checks"""
        original_surah = self.current_surah
        original_ayah = self.current_ayah
        
        self.current_ayah -= 1
        
        # Handle underflow
        if self.current_ayah < 1:
            self.current_surah -= 1
            # Handle surah underflow
            if self.current_surah < 1:
                self.current_surah = 114  # Wrap to last surah
            self.current_ayah = self.surah_ayat[self.current_surah]
        
        # Verify the new ayah exists
        if not self.get_audio_path():
            self.log_action("ERROR", "Previous ayah not found - resetting")
            self.current_surah = original_surah
            self.current_ayah = original_ayah
            return False
            
        self.save_playback_state()
        return self.play_audio()

    def handle_next(self):
        """Next ayah with boundary checks"""
        original_surah = self.current_surah
        original_ayah = self.current_ayah
        
        max_ayah = self.surah_ayat[self.current_surah]
        self.current_ayah += 1
        
        # Handle overflow
        if self.current_ayah > max_ayah:
            self.current_surah += 1
            # Handle surah overflow
            if self.current_surah > 114:
                self.current_surah = 1  # Wrap to first surah
            self.current_ayah = 1
        
        # Verify the new ayah exists
        if not self.get_audio_path():
            self.log_action("ERROR", "Next ayah not found - resetting")
            self.current_surah = original_surah
            self.current_ayah = original_ayah
            return False
            
        self.save_playback_state()
        return self.play_audio()


    def load_playback_state(self):
        """Load playback state from previous session"""
        state = configparser.ConfigParser()
        if os.path.exists(self.state_file):
            state.read(self.state_file)
            try:
                self.current_surah = state.getint('state', 'surah', fallback=1)
                self.current_ayah = state.getint('state', 'ayah', fallback=1)
            except (ValueError, TypeError) as e:
                self.log_action("ERROR", f"Corrupted state file: {e}. Using defaults")

    def save_playback_state(self):
        """Persist current playback state"""
        state = configparser.ConfigParser()
        state['state'] = {
            'surah': str(self.current_surah),
            'ayah': str(self.current_ayah)
        }
        with open(self.state_file, 'w') as f:
            state.write(f)

    def get_audio_path(self):
        """Get path to current audio file with validation"""
        audio_file = f"{self.current_surah:03}{self.current_ayah:03}.mp3"
        path = os.path.join(self.audio_base, audio_file)

        if not os.path.exists(path):
            self.log_action("ERROR", f"Audio file missing: {path}")
            return None

        return path

    def play_audio(self):
        with self.audio_lock:
            self.initialize_pygame() 
            audio_path = self.reset_file_not_found()
            if not audio_path:
                self.log_action("PLAY", "File not found, aborting...")
                return False
            self.is_paused = False
            try:
                quran_text = quran_search.command_line_mode(self.current_surah, self.current_ayah, self.current_ayah,
                 quran_search.uthmani, quran_search.simplified, quran_search.chapters)
                self.show_verse_image(quran_text)
                
                pygame.mixer.music.load(audio_path)
                pygame.mixer.music.play()
                self.log_action("PLAY", f"Started: {self.current_surah}:{self.current_ayah}")
                # Start simple completion checking
                threading.Thread(target=self.check_playback_status, daemon=True).start()
                return True
            except pygame.error as e:
                self.log_action("ERROR", f"Playback failed: {str(e)}")
                return False

    def check_playback_status(self):
        while pygame.mixer.music.get_busy():
            time.sleep(0.5)
        self.handle_playback_end()

    def reset_file_not_found(self,ayah=None,surah=None):
        if ayah:
            self.current_ayah = ayah
        next_path = self.get_audio_path()
        if not next_path or not os.path.exists(next_path):
            self.log_action("WARNING", "Next file missing, resetting")
            self.current_ayah = 1
            self.current_surah = 1
            #self.current_surah = 1 if surah > 114 else surah
            next_path = self.get_audio_path()
            
            if not next_path or not os.path.exists(next_path):
                self.log_action("ERROR", "Critical failure: Base file missing")
                self.playback_active = False
                return 
        return next_path

    def handle_playback_end(self):
        """Handle track completion and play next"""
        if not self.is_paused:
            # Increment state
            new_ayah = self.current_ayah + 1
            new_surah = self.current_surah
            
            # Validate next file before committing
            self.reset_file_not_found(ayah=new_ayah,surah=new_surah)

            # Commit state
            self.log_action("INFO", f"New state: {self.current_surah}:{self.current_ayah}")
            self.save_playback_state()
            self.play_audio()

    def stop_playback(self):
        pygame.mixer.music.stop()
        self.current_playback = None

    def load_surah_ayah(self, surah: int, ayah: int, autoplay: bool = True) -> bool:
        """
        Load specific Surah and Ayah with validation
        Args:
            surah (int): Surah number (1-114)
            ayah (int): Ayah number (1-last_ayah_of_surah)
            autoplay (bool): Start playback immediately if True
        Returns:
            bool: True if successful, False otherwise
        """
        # Input validation
        if not (1 <= surah <= 114):
            self.log_action("ERROR", f"Invalid surah number: {surah} (must be 1-114)")
            return False
            
        if ayah < 1:
            self.log_action("ERROR", f"Invalid ayah number: {ayah} (must be ≥1)")
            return False

        # TODO: Add validation for maximum ayah per surah
        # You'll need a surah_ayat.json file with {surah_number: ayat_count}

        # Set new state
        self.current_surah = surah
        self.current_ayah = ayah
        self.save_playback_state()
        
        # Verify audio file exists
        audio_path = self.get_audio_path()
        if not audio_path:
            self.log_action("ERROR", "Audio file not found for selected ayah")
            return False
            
        # Start playback if requested
        if autoplay:
            self.play_audio()
            
        return True

    def handle_load(self, args):
        """Handle load command with explicit argument validation"""
        try:
            surah, ayah = map(int, args.split(':', 1))
            
            if not (1 <= surah <= 114):
                self.log_action("ERROR", f"Invalid surah: {surah}")
                return False
                
            if ayah < 1 or ayah > self.surah_ayat[surah]:
                self.log_action("ERROR", f"Invalid ayah: {ayah} for surah {surah}")
                return False

            self.current_surah = surah
            self.current_ayah = ayah
            self.save_playback_state()
            return self.play_audio()

        except ValueError:
            self.log_action("ERROR", f"Invalid load format: {args}")
            return False
        except Exception as e:
            self.log_action("ERROR", f"Load failed: {str(e)}")
            return False

    def show_verse_image(self, text, highlight_line=None):
        """Show verse image in single feh instance with auto-reload"""
        output_path = "/tmp/quran_verse.png"
        
        # Generate new image
        success = arabic_topng.render_arabic_text_to_image(
            text=text,
            output_path=output_path,
            config=self.config,
            highlight_line=highlight_line
        )
        
        if not success:
            return

        try:
            # Try to reload existing feh instance
            if self.feh_process and (self.feh_process.poll() is None):
                os.kill(self.feh_process.pid, signal.SIGUSR1)
                self.log_action("IMAGE", "Reloaded existing feh window")
                return
        except (ProcessLookupError, AttributeError):
            # Process dead or not exists, start new
            pass

        # Start new feh instance with clean options
        self.feh_process = subprocess.Popen([
            'feh',
            '--image-bg', 'none',
            '--no-menus',
            '--auto-zoom',
            '--title', 'QuranPlayer',  # Unique window title
            output_path
        ])
        self.log_action("IMAGE", "Launched new feh window")



def is_daemon_running():
    """Verify daemon is actually running with PID and process name"""
    if not os.path.exists(PID_FILE):
        return False

    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())

        # Check if process exists first
        os.kill(pid, 0)  # Will throw OSError if process doesn't exist

        # Check process name in command line arguments
        cmdline_path = Path(f"/proc/{pid}/cmdline")
        if not cmdline_path.exists():
            return False

        cmdline = cmdline_path.read_bytes().decode().replace('\x00', ' ')
        
        return "quran_player.py" in cmdline  

    except (ValueError, OSError, FileNotFoundError):
        return False
    except Exception as e:
        print(f"Unexpected error checking process: {str(e)}")
        return False


def cleanup_orphaned_files():
    """Remove PID/socket files if daemon not running"""
    if os.path.exists(PID_FILE) and not is_daemon_running():
        try:
            os.remove(PID_FILE)
            os.remove(SOCKET_FILE)
        except Exception as e:
            print(f"Cleanup warning: {str(e)}")


def print_usage():
    print("Usage: python3 quran-player.py <command>")
    print("Commands:")
    print("  start   - Start the daemon")
    print("  stop    - Stop the daemon")
    print("  play    - Play the track")
    print("  pause   - Pause playback")
    print("  prev    - Play previous track")
    print("  next    - Play next track")
    print("  load <surah> <ayah>    - Load track")
    print("  config  - Generate default config file")

if __name__ == "__main__":
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
    import pygame  # Hidden import
    
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
    elif command == "cleanup":
        cleanup_orphaned_files()
    elif command == "config":
        daemon.handle_config()
        print(f"Generated config at {USER_CONFIG_FILE}")
        
    elif command in ["stop", "play", "pause", "prev", "next", "load","status"]:
        if not is_daemon_running():
            print(f"Error: Start daemon first with: {sys.argv[0]} start")
            sys.exit(1)

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(5)
                client.connect(SOCKET_FILE)
                
                # Send raw command string
                client.sendall((' '.join(sys.argv[1:])).encode() + b"\n")
                print(client.recv(1024).decode().strip())
                
        except (ConnectionRefusedError, FileNotFoundError):
            print("Error: Daemon unavailable")
            sys.exit(1)
            
    else:
        print_usage()
        sys.exit(1)


