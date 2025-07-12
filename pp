




















































class GUIManager:
    def __init__(self, daemon_comm):
        self.daemon_comm = daemon_comm
        self.create_gui()

    def update_status(self):
        """Update the status label and buttons"""
        try:
            if time.time() - getattr(self, '_last_update', 0) < 1:
                return
            self._last_update = time.time()

            daemon_running = self.is_daemon_running()
            
            # Update stop/start button
            if daemon_running:
                self.stop_button.config(text="Stop Daemon")
                self.update_status_bar("Daemon is running.")
            else:
                try:
                    self.stop_button.config(text="Start Daemon")
                    self.update_status_bar("Daemon is not running.", error=True)
                except Exception as e:
                    pass

            response = self.send_command("status")
            if response and response.startswith("STATUS"):
                parts = response.split("|")
                if len(parts) == 4:
                    self.current_state = {
                        "surah": int(parts[1]),
                        "ayah": int(parts[2]),
                        "paused": parts[3] == "PAUSED"
                    }
                    surah_name = quran_search.get_chapter_name(quran_search.chapters, self.current_state['surah'])
                    reshaped_text = arabic_reshaper.reshape(surah_name)
                    bidi_text = get_display(reshaped_text)
                    status_text = f"{self.current_state['ayah']} : {bidi_text}" 
                    self.status_label.config(text=status_text)
        except Exception as e:
            print(f"Status update error: {str(e)}")


    def create_gui(self):
        # Build the Tkinter UI and system tray
        # ...

    # Methods for button callbacks that use self.daemon_comm.send_command(...)

if __name__ == "__main__":
    socket_path = get_socket_path()
    daemon_comm = DaemonCommunicator(socket_path)
    gui = GUIManager(daemon_comm)
    gui.run()


class QuranController:
    def __init__(self):
        self.current_state = {"surah": 1, "ayah": 1, "paused": False}
        self.socket_path = get_socket_path()
        self.tray_icon = None
        self.root = None
        self.daemon_process = None
        self.polling_thread = None
        self.running = True
        self.daemon_stopped = False 
        self.tray_thread = None  # Add this line

        self.create_gui()
        self.start_status_poller()
        signal.signal(signal.SIGINT, self.handle_exit)




    



    def send_command(self, command):
        """Send command to daemon with conditional auto-start"""
        try:
            # Only auto-start if not manually stopped
            if not self.is_daemon_running() and not self.daemon_stopped:
                if not self.start_daemon():
                    return None

            sock = self.create_socket()  
            sock.settimeout(2)
            sock.connect(self.socket_path)  
            sock.sendall(command.encode() + b"\n")
            return sock.recv(1024).decode().strip()
        except (ConnectionRefusedError, FileNotFoundError):
            if command == "status":
                msg = "Daemon is not running."
            else:
                msg = "Daemon not responding!"
            self.update_status_bar(msg, error=True)
            return None
        except Exception as e:
            self.update_status_bar(f"Communication error: {str(e)}", error=True)
            return None



    def update_status_bar(self, message, error=False):
        """Update the status bar with a message"""
        self.status_bar.config(text=message)
        if error:
            self.status_bar.config(fg="red", bg="#330000")  # Dark red background for errors
        else:
            self.status_bar.config(fg=FG_COLOR, bg=STATUS_BAR_COLOR)

    def create_gui(self):
        """Create the enhanced dark theme GUI"""
        # System Tray Icon
        menu = pystray.Menu(
            pystray.MenuItem("Show Window", self.show_window, default=True),
            pystray.MenuItem("Play", self.play),
            pystray.MenuItem("Pause", self.pause),
            pystray.MenuItem("Next Verse", self.next_verse),
            pystray.MenuItem("Previous Verse", self.prev_verse),
            pystray.MenuItem("Load Verse", self.load_verse),
            pystray.MenuItem("Stop Daemon", self.stop_daemon),
            pystray.MenuItem("Exit", self.exit_app)
        )
        
        image = Image.open(ICON_FILE)
        self.tray_icon = pystray.Icon("quran_player", image, "Quran Player", menu)

        self.tray_icon._root = self.root  # Keep reference to main window
        
        # Add explicit left-click handler
        self.tray_icon._handler = {
            'ON_CLICK': lambda icon, item: self.show_window()
        }


        # Main Window Configuration
        self.root = tk.Tk()
        self.root.title("Quran Player Controller")
        self.root.geometry("460x280")
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

        # Configure Styles
        style = ttk.Style()
        style.theme_use('clam')

        # Configure root background
        style.configure('.', background=BG_COLOR)

        # Button styling
        style.configure('TButton', 
                      background=BUTTON_BG,
                      foreground=FG_COLOR,
                      borderwidth=0,
                      font=('Helvetica', 10),
                      bordercolor=BG_COLOR,
                      focuscolor=BG_COLOR,
                      relief='flat',
                      padding=5)
        
        style.map('TButton', 
            background=[('active', BUTTON_ACTIVE_BG)],
            foreground=[('active', FG_COLOR)]
        )

        # Frame styling
        style.configure('TFrame', background=BG_COLOR)
        style.configure('MainFrame.TFrame', background=BG_COLOR)

        # Main Layout
        main_frame = ttk.Frame(self.root)
        main_frame.pack(padx=20, pady=20, fill='both', expand=True)

        # Status Display
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill='x', pady=10)
        
        self.status_label = tk.Label(
            status_frame,
            text="Loading status...",
            font=('Amiri', 14, 'bold'),
            fg=FG_COLOR,
            bg=BG_COLOR,
            anchor='e',  # Align text to the right
            justify='right'  # Justify text to the right
        )
        self.status_label.pack()

        # Control Buttons
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(pady=15)

        self.prev_button = ttk.Button(
            control_frame,
            text="⏮",
            command=self.prev_verse,
            style='TButton',
            width=3
        )
        self.prev_button.grid(row=0, column=0, padx=5)

        self.play_button = ttk.Button(
            control_frame,
            text="▶",
            command=self.play,
            style='TButton',
            width=3,
        )
        self.play_button.grid(row=0, column=1, padx=5)

        self.pause_button = ttk.Button(
            control_frame,
            text="⏸",
            command=self.pause,
            style='TButton',
            width=3,
        )
        self.pause_button.grid(row=0, column=2, padx=5)

        self.next_button = ttk.Button(
            control_frame,
            text="⏭",
            command=self.next_verse,
            style='TButton',
            width=3
        )
        self.next_button.grid(row=0, column=3, padx=5)


        # Action Buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(pady=15)

        # First row of buttons
        ttk.Button(action_frame, text="Load Verse", command=self.load_verse).grid(row=0, column=0, padx=5)
        ttk.Button(action_frame, text="Stop Daemon", command=self.toggle_daemon).grid(row=0, column=1, padx=5)
        ttk.Button(action_frame, text="Minimize", command=self.minimize_to_tray).grid(row=0, column=2, padx=5)
        ttk.Button(action_frame, text="Exit", command=self.exit_app).grid(row=0, column=3, padx=5)

        self.stop_button = action_frame.grid_slaves(row=0, column=1)[0]
        # Second row with Config button
        ttk.Button(action_frame,text="Config",command=self.open_config).grid(row=1, column=0, pady=5)
        ttk.Button(action_frame, text="About", command=self.show_about).grid(row=1, column=1, pady=5)

        # Status Bar with Padding
        self.status_bar = tk.Label(
            self.root,
            text="Checking daemon status...",
            font=('Helvetica', 9),
            fg=FG_COLOR,
            bg=STATUS_BAR_COLOR,
            relief=tk.SUNKEN,
            anchor=tk.CENTER,
            padx=5,  # Horizontal padding
            pady=5   # Vertical padding
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)  # Add bottom margin   , pady=(0, 2)

        #self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

    def handle_exit(self, signum=None, frame=None):
        """Handle Ctrl+C and other exits"""
        self.exit_app()

    def play(self):
        """Play the current verse"""
        self.send_command("play")

    def pause(self):
        """Pause the current verse"""
        self.send_command("pause")

    def next_verse(self):
        """Play next verse"""
        self.send_command("next")

    def prev_verse(self):
        """Play previous verse"""
        self.send_command("prev")

    def load_verse(self):
        """Load a specific verse"""
        verse = simpledialog.askstring("Load Verse", "Enter Surah:Ayah (e.g. 2:255):", parent=self.root)
        if verse:
            self.send_command(f"load {verse}")

    def start_status_poller(self):
        """Poll daemon status in the background"""
        def poller():
            while self.running:
                try:
                    self.update_status()
                except Exception as e:
                    print(f"Status poll error: {str(e)}")
                time.sleep(1)
                
        self.polling_thread = threading.Thread(target=poller, daemon=True)
        self.polling_thread.start()

    def minimize_to_tray(self):
        """Minimize to system tray"""
        self.root.withdraw()
        self.tray_icon.run_detached()  # Run the system tray icon in a separate thread

    def run(self):
        """Start the GUI and system tray"""
        #self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        #self.tray_thread.start()
        #self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        self.root.mainloop()

    def exit_app(self):
        """Gracefully exit the application"""
        self.running = False
        
        # Kill subprocesses
        if hasattr(self, 'daemon_process') and self.daemon_process:
            self.daemon_process.terminate()
        
        # Stop tray icon
        print("stopping tray icon")
        if self.tray_icon:
            self.tray_icon.stop()
        
        # Destroy window
        print("destroy window")
        if self.root:
            self.root.destroy()
        
        # Ensure process termination
        print("exit all")
        os._exit(0)  # Force exit all threads

    def show_window(self, icon=None, item=None):
        """Force window restoration"""
        self.root.after(0, self.root.deiconify)
        self.root.after(0, self.root.lift)

    def open_config(self):
        """Open config file with default editor using daemon"""
        try:
            # Send config command to daemon (handles file creation)
            if not os.path.exists(USER_CONFIG_FILE):
                response = self.send_command("config")
            
            # Give the daemon a moment to create the file
            time.sleep(0.5)  
            
            # Open the config file with detatched process
            if sys.platform == 'win32':
                os.startfile(USER_CONFIG_FILE)
            else:
                opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
                subprocess.Popen(
                    [opener, USER_CONFIG_FILE],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    # Detach from parent process on supported platforms
                    start_new_session=True if sys.platform != 'win32' else None
                )
                
        except Exception as e:
            self.update_status_bar(f"Could not open config file: {str(e)}",error=True)

    def show_about(self):
        """Show about dialog with command documentation"""
        about_window = tk.Toplevel(self.root)
        about_window.title("About Quran Player")
        about_window.geometry("500x400")
        about_window.resizable(False, False)
        about_window.grab_set()  # Make it modal
        about_window.configure(bg=BG_COLOR)

        # Main container with scrollbar
        main_frame = ttk.Frame(about_window)
        main_frame.pack(fill='both', expand=True)

        canvas = tk.Canvas(main_frame, bg=BG_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Header
        header_frame = ttk.Frame(scrollable_frame)
        header_frame.pack(pady=10, fill='x')
        
        tk.Label(header_frame, 
                text="Quran Player", 
                font=('Helvetica', 16, 'bold'),
                fg=FG_COLOR, bg=BG_COLOR).pack()

        # Author Info
        tk.Label(scrollable_frame, 
                text="Author: MOSAID Radouan", 
                fg=FG_COLOR, bg=BG_COLOR).pack(pady=5)

        # Clickable Links
        def open_url(url):
            webbrowser.open(url)

        links_frame = ttk.Frame(scrollable_frame)
        links_frame.pack(pady=5)
        
        website = tk.Label(links_frame, 
                        text="Website: mosaid.xyz", 
                        fg=ACCENT_COLOR, bg=BG_COLOR,
                        cursor='hand2')
        website.pack(side=tk.LEFT, padx=10)
        website.bind("<Button-1>", lambda e: open_url("https://mosaid.xyz"))

        github = tk.Label(links_frame, 
                        text="GitHub Repository", 
                        fg=ACCENT_COLOR, bg=BG_COLOR,
                        cursor='hand2')
        github.pack(side=tk.LEFT, padx=10)
        github.bind("<Button-1>", lambda e: open_url("https://github.com/neoMOSAID/quran-player"))

        # Command List
        commands_frame = ttk.Frame(scrollable_frame)
        commands_frame.pack(pady=10, padx=20, fill='x')

        tk.Label(commands_frame, 
                text="Supported Commands:",
                font=('Helvetica', 12, 'bold'),
                fg=FG_COLOR, bg=BG_COLOR).pack(anchor='w')

        commands = [
            ("play", "Resume playback of current verse"),
            ("pause", "Pause current playback"),
            ("next", "Play next verse"),
            ("prev", "Play previous verse"),
            ("load [surah:ayah]", "Load specific verse (e.g. '2:255')"),
            ("status", "Get current playback status"),
            ("config", "Create/update configuration file"),
            ("about", "Show this information"),
            ("stop", "Stop the daemon process")
        ]

        for cmd, desc in commands:
            frame = ttk.Frame(commands_frame)
            frame.pack(fill='x', pady=2)
            
            tk.Label(frame, text=f"• {cmd}:", 
                    font=('Helvetica', 10, 'bold'),
                    fg=FG_COLOR, bg=BG_COLOR).pack(side='left')
            tk.Label(frame, text=desc,
                    fg=FG_COLOR, bg=BG_COLOR).pack(side='left', padx=5)

        # Close button (fixed at bottom)
        button_frame = ttk.Frame(about_window)
        button_frame.pack(side='bottom', pady=10)
        
        ttk.Button(button_frame, 
                text="Close", 
                command=about_window.destroy).pack()

        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Set minimum size for scroll region
        scrollable_frame.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

def command_line_interface():
    """Handle command-line arguments"""
    parser = argparse.ArgumentParser(description='Quran Player Control')
    parser.add_argument('command', nargs='?', help='Command to send to daemon')
    parser.add_argument('args', nargs='*', help='Command arguments')

    args = parser.parse_args()

    if args.command:
        if args.command == "about":
            about()
        else:
            controller = QuranController()
            response = controller.send_command(f"{args.command} {' '.join(args.args)}")
            print(response or "No response from daemon")
    else:
        controller = QuranController()
        controller.run()



if __name__ == "__main__":
    command_line_interface()

























-----------------------------------------------------------





























import inspect
import os
import sys
from datetime import datetime

# Log Level Mapping
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

# Optional non-critical logs (can be disabled)
NON_CRITICAL_FLAGS = {"INFO", "DEBUG", "WARNING", "SYSTEM"}

def log_action(self, flag, msg):
    """Log an action based on log level settings."""
    # Retrieve log level from config
    log_level_str = self.config.get("daemon", "LOG_LEVEL", fallback="INFO").upper()
    log_level = LOG_LEVELS.get(log_level_str, 20)  # Default to INFO

    # Determine message priority
    message_priority = LOG_LEVELS.get(flag, 20)  # Default to INFO if unknown flag

    # Skip logging if below the configured level (except for critical messages)
    if message_priority < log_level and flag not in CRITICAL_FLAGS:
        return  # ✅ Exit early (reduces unnecessary log writes)

    # Get calling method dynamically
    method = inspect.currentframe().f_back.f_code.co_name
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    pid = os.getpid()
    
    log_entry = f"{timestamp}|{pid}|{method}|{flag}|{msg}\n"

    # Choose log file
    log_path = CILENT_LOG_FILE if method == "handle_client" and flag == "ERROR" else LOG_FILE

    # Rotate log if needed
    self.rotate_log_if_needed(log_path)

    # Write to log file
    try:
        with open(log_path, "a") as log:
            log.write(log_entry)
    except IOError as e:
        print(f"Failed to write to log: {str(e)}", file=sys.stderr)



























this is the log_action method:
    def log_action(self, flag, msg):
        """Log an action with timestamp, PID, method, flag, and message."""
        method = inspect.currentframe().f_back.f_code.co_name
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        pid = os.getpid()
        log_entry = f"{timestamp}|{pid}|{method}|{flag}|{msg}\n"
        
        # Determine which log file to use
        if method == 'handle_client' and flag == "ERROR":
            log_path = CILENT_LOG_FILE
        else:
            log_path = LOG_FILE

        # Rotate log if needed
        self.rotate_log_if_needed(log_path)

        # Write to log file
        try:
            with open(log_path, "a") as log:
                log.write(log_entry)
        except IOError as e:
            print(f"Failed to write to log: {str(e)}", file=sys.stderr)

log level can be read using : self.config
    def get_default_config(self):
        """Return a dictionary of default configuration values for all sections."""
        return {
            "daemon": {
                "MAX_LOG_SIZE": 1000000,
                "LOG_LEVEL": "INFO",
                "FILES_DIRECTORY": os.path.join(USER_CONFIG_DIR, "sample"),
            },
            "image": {
                "ENABLE": "yes",
                "DEFAULT_RESOLUTION": "1240x170",
                "FONT_FILE": os.path.join(USER_CONFIG_DIR, "arabic-font.ttf"),
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
                if validated_value < 1024:
                    raise ValueError("Must at least 1024 bytes.")
            elif key == "FILES_DIRECTORY":
                if os.path.isdir(value):
                    validated_value = value
                else:
                    raise ValueError("Invalid files directory.")
            elif key == "DEFAULT_RESOLUTION":
                # Validate resolution format (e.g., '1920x1080')
                parts = value.split('x')
                if len(parts) != 2 or not all(part.isdigit() for part in parts):
                    raise ValueError("Invalid resolution format.")
                validated_value = value
            elif key == "FONT_FILE":
                if not os.path.exists(value):  
                    raise ValueError("Font file missing")
            elif key in ["BG_COLOR", "TEXT_COLOR", "HIGHLIGHT_COLOR"]:
                validated_value = str(value)
            elif key in ["FONT_SIZE", "IMAGE_WIDTH", "WRAP_WIDTH", "VERTICAL_PADDING"]:
                validated_value = int(value)
                if validated_value <= 0:
                    raise ValueError("Must be positive.")
            elif key == "ENABLE":
                # Accept both string and boolean representations
                if isinstance(value, str):
                    value = value.lower()
                    if value in {'yes', 'true', '1', 'on'}:
                        validated_value = True
                    elif value in {'no', 'false', '0', 'off'}:
                        validated_value = False
                    else:
                        raise ValueError("Invalid boolean value")
                else:
                    validated_value = bool(value)
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

I can add the key log level
since there are a lot of calls to the lor_action, method
let it check log level, if disabled return, make list of critical /no critical messages
then I'll slowly go through them later and check them carefuly



























import os
import psutil
from pathlib import Path

PID_FILE = "/tmp/quran_player.pid"  # Adjust this path if needed

def is_daemon_running():
    """Verify daemon is actually running with PID and process name"""
    if not os.path.exists(PID_FILE):
        return False

    try:
        with open(PID_FILE, "r") as f:
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





























def __init__(self):
    # Add log rotation lock
    self.log_lock = threading.Lock()
    # ... rest of existing init code ...

def log_action(self, flag, msg):
    """Log an action with timestamp, PID, method, flag, and message."""
    method = inspect.currentframe().f_back.f_code.co_name
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    pid = os.getpid()
    log_entry = f"{timestamp}|{pid}|{method}|{flag}|{msg}\n"
    
    # Determine which log file to use
    if method == 'handle_client' and flag == "ERROR":
        log_path = CILENT_LOG_FILE
    else:
        log_path = LOG_FILE

    # Rotate main log if needed
    if log_path == LOG_FILE:
        self.rotate_log_if_needed()

    # Write to log file
    try:
        with open(log_path, "a") as log:
            log.write(log_entry)
    except IOError as e:
        print(f"Failed to write to log: {str(e)}", file=sys.stderr)

def rotate_log_if_needed(self):
    """Rotate log file if it exceeds configured maximum size"""
    max_size = self.config.getint('daemon', 'MAX_LOG_SIZE', fallback=1000000)
    
    with self.log_lock:
        try:
            if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) >= max_size:
                # Rotate logs
                rotated_log = f"{LOG_FILE}.1"
                
                # Remove old rotated log if exists
                if os.path.exists(rotated_log):
                    os.remove(rotated_log)
                
                # Rotate current log
                os.rename(LOG_FILE, rotated_log)
                
                # Log the rotation
                with open(LOG_FILE, "w") as new_log:
                    new_log.write(f"{datetime.now().isoformat()}|SYSTEM|LOG|Rotated log file\n")
        except Exception as e:
            print(f"Log rotation failed: {str(e)}", file=sys.stderr)



























These documents provide comprehensive documentation covering both command-line usage (via manpage) and project overview/installation instructions (via README). The manpage follows standard UNIX manual conventions while the README uses modern GitHub formatting with badges and clear section organization.




































def create_custom_dialog():
    """Create a dark-themed RTL input dialog with proper event handling."""
    dialog = tk.Toplevel()
    dialog.title("Quran Search")
    dialog.configure(bg=DARK_BG)
    dialog.geometry("400x150")
    
    # Create StringVar to store the result
    result = tk.StringVar()
    
    # Configure Arabic font
    font_name = 'Amiri' if 'Amiri' in tk.font.families() else 'Arial'
    font = (font_name, 14)
    
    label = ttk.Label(dialog, text="Enter Arabic search term:", 
                     background=DARK_BG, foreground=DARK_FG, font=font)
    label.pack(pady=10)
    
    # Create RTL entry widget
    entry = ttk.Entry(
        dialog,
        font=font,
        justify='right',
        textvariable=result
    )
    entry.pack(pady=10, padx=20, fill='x')
    
    # Bind Enter key to submit
    entry.bind('<Return>', lambda e: dialog.destroy())
    
    # Create OK button
    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=10)
    
    ok_btn = ttk.Button(btn_frame, text="OK", command=dialog.destroy)
    ok_btn.pack(side='right', padx=10)
    
    # Focus management
    entry.focus_set()
    dialog.grab_set()
    
    # Wait for dialog to close
    dialog.wait_window()
    
    return result.get()

def interactive_mode(uthmani, simplified, chapters):
    """Handle interactive mode with GUI input."""
    original_layout = get_current_layout()
    root = tk.Tk()
    root.withdraw()
    
    try:
        set_layout('ara')
        # Create and show dialog directly
        search_term = create_custom_dialog()
    finally:
        if original_layout:
            set_layout(original_layout)
        root.destroy()

    if not search_term:
        print("No search term entered.")
        return

    # Rest of the function remains the same...

















def create_custom_dialog():
    """Create a dark-themed RTL input dialog with proper event handling."""
    dialog = tk.Toplevel()
    dialog.title("Quran Search")
    dialog.configure(bg=DARK_BG)
    dialog.geometry("400x150")
    
    # Create StringVar to store the result
    result = tk.StringVar()
    
    # Set Arabic font configuration
    font_name = 'Amiri' if 'Amiri' in tk.font.families() else 'Arial'
    font = (font_name, 14)
    
    # Configure RTL layout
    dialog.tk.call('tk', 'textDirection', 'right')
    
    label = ttk.Label(dialog, text="Enter Arabic search term:", 
                     background=DARK_BG, foreground=DARK_FG, font=font)
    label.pack(pady=10)
    
    entry = ttk.Entry(dialog, font=font, justify='right', textvariable=result)
    entry.pack(pady=10, padx=20, fill='x')
    
    # Bind Enter key to dialog destruction
    entry.bind('<Return>', lambda e: dialog.destroy())
    
    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=10)
    
    ok_btn = ttk.Button(btn_frame, text="OK", command=dialog.destroy)
    ok_btn.pack(side='right', padx=10)
    
    # Force focus on entry widget
    entry.focus_set()
    
    # Wait for dialog to close
    dialog.wait_window()
    
    return result.get()

def interactive_mode(uthmani, simplified, chapters):
    """Handle interactive mode with GUI input."""
    original_layout = get_current_layout()
    root = tk.Tk()
    root.withdraw()
    
    try:
        set_layout('ara')
        search_term = create_custom_dialog()  # Directly get the result
    finally:
        if original_layout:
            set_layout(original_layout)
        root.destroy()

    if not search_term:
        print("No search term entered.")
        return

    # Rest of the function remains the same...























        self.valid_commands = {
            "start": "SYSTEM",
            "stop": "SYSTEM",
            "cleanup": "SYSTEM",
            "play": "PLAY",
            "toggle": "PLAY",
            "pause": "PAUSE",
            "prev": "NAV",
            "next": "NAV",
            "load": "NAV",
            "status": "INFO",
            "config": "SYSTEM",
        }













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


















# Add to QuranController class
def __init__(self):
    # Add this line
    self.daemon_stopped = False  # Track if user explicitly stopped daemon
    # ... rest of existing init code ...

# Modified start_daemon method
def start_daemon(self):
    """Start the daemon process if not running and not stopped by user"""
    if self.daemon_stopped:
        return False  # Don't start if user stopped it
    
    if not self.is_daemon_running():
        try:
            self.daemon_process = subprocess.Popen(
                [sys.executable, DAEMON_SCRIPT, "start"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1)
            self.daemon_stopped = False
            return True
        except Exception as e:
            self.update_status_bar(f"Failed to start daemon: {str(e)}", error=True)
            return False
    return True

# Modified stop_daemon method
def stop_daemon(self):
    """Stop the daemon process and update state"""
    if self.is_daemon_running():
        response = self.send_command("stop")
        if response:
            self.daemon_stopped = True
            self.update_status_bar("Daemon stopped. (Manual restart required)")
            # Update button text
            self.stop_button.config(text="Start Daemon")
            return True
        else:
            self.update_status_bar("Failed to stop daemon.", error=True)
            return False
    else:
        self.update_status_bar("Daemon is not running.")
        return False

# New method to handle start/stop toggle
def toggle_daemon(self):
    """Toggle daemon state based on current status"""
    if self.daemon_stopped or not self.is_daemon_running():
        if self.start_daemon():
            self.daemon_stopped = False
            self.stop_button.config(text="Stop Daemon")
    else:
        self.stop_daemon()

# Modified send_command method
def send_command(self, command):
    """Send command to daemon with conditional auto-start"""
    try:
        # Only auto-start if not manually stopped
        if not self.is_daemon_running() and not self.daemon_stopped:
            if not self.start_daemon():
                return None

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(SOCKET_FILE)
            sock.sendall(command.encode() + b"\n")
            return sock.recv(1024).decode().strip()
    # ... rest of existing send_command code ...

# In create_gui method, modify the action buttons:
# Change this line in action buttons section
ttk.Button(action_frame, text="Stop Daemon", command=self.toggle_daemon).grid(row=0, column=1, padx=5)
# Add this line to create a reference to the stop button
self.stop_button = action_frame.grid_slaves(row=0, column=1)[0]

# Add to update_status method
def update_status(self):
    """Update the status label and buttons"""
    daemon_running = self.is_daemon_running()
    
    # Update stop/start button
    if daemon_running:
        self.stop_button.config(text="Stop Daemon")
    else:
        self.stop_button.config(text="Start Daemon")
    
    # Rest of existing update_status code...

















# In the QuranController class, add this method:
def open_config(self):
    """Open config file with default editor"""
    config_path = os.path.expanduser("~/.config/quran-player/config.ini")
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        if not os.path.exists(config_path):
            with open(config_path, 'w') as f:
                f.write("# Quran Player Configuration\n\n[settings]\n")
        
        if sys.platform == 'win32':
            os.startfile(config_path)
        else:
            opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
            subprocess.call([opener, config_path])
    except Exception as e:
        messagebox.showerror("Error", f"Could not open config file: {str(e)}")

# In the create_gui method, modify the action_frame section:
# Action Buttons
action_frame = ttk.Frame(main_frame)
action_frame.pack(pady=15)

# First row of buttons
ttk.Button(action_frame, text="Load Verse", command=self.load_verse).grid(row=0, column=0, padx=5)
ttk.Button(action_frame, text="Stop Daemon", command=self.stop_daemon).grid(row=0, column=1, padx=5)
ttk.Button(action_frame, text="Minimize", command=self.minimize_to_tray).grid(row=0, column=2, padx=5)
ttk.Button(action_frame, text="Exit", command=self.exit_app).grid(row=0, column=3, padx=5)

# Second row with Config button
ttk.Button(
    action_frame,
    text="Config",
    command=self.open_config
).grid(row=1, column=0, columnspan=4, pady=5, sticky='ew')




















# quran_gui.py - Final Tray Fixes
import os
import socket
import sys
import threading
import time
import subprocess
import argparse
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import pystray
import signal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOCKET_FILE = os.path.join(SCRIPT_DIR, "control/daemon.sock")
DAEMON_SCRIPT = os.path.join(SCRIPT_DIR, "quran_player.py")
ICON_FILE = os.path.join(CRIPT_DIR, "icon.png")

# Color Scheme
BG_COLOR = "#2d2d2d"
FG_COLOR = "#ffffff"
BUTTON_BG = "#3d3d3d"
BUTTON_ACTIVE_BG = "#4d4d4d"
ACCENT_COLOR = "#1e90ff"
ACCENT_ACTIVE = "#0066cc"
STATUS_BAR_COLOR = "#1e1e1e"

class QuranController:
    def __init__(self):
        self.current_state = {"surah": 1, "ayah": 1, "paused": False}
        self.tray_icon = None
        self.root = None
        self.daemon_process = None
        self.polling_thread = None
        self.running = True

        self.create_gui()
        self.start_status_poller()
        signal.signal(signal.SIGINT, self.handle_exit)

    # [Keep previous methods unchanged until create_gui]

    def create_gui(self):
        """Create the enhanced dark theme GUI"""
        # System Tray Icon with proper click handling
        menu = pystray.Menu(
            pystray.MenuItem("Show Window", self.show_window),
            pystray.MenuItem("Play", self.play),
            pystray.MenuItem("Pause", self.pause),
            pystray.MenuItem("Next Verse", self.next_verse),
            pystray.MenuItem("Previous Verse", self.prev_verse),
            pystray.MenuItem("Load Verse", self.load_verse),
            pystray.MenuItem("Stop Daemon", self.stop_daemon),
            pystray.MenuItem("Exit", self.exit_app)
        )
        
        image = Image.open(ICON_FILE)
        self.tray_icon = pystray.Icon("quran_player", image, "Quran Player", menu)
        
        # Add explicit left-click handler
        self.tray_icon._handler = {
            'ON_CLICK': lambda icon, item: self.show_window()
        }

        # Main Window Configuration
        self.root = tk.Tk()
        self.root.title("Quran Player Controller")
        self.root.geometry("400x300")
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

        # Configure Styles
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', 
                      background=BUTTON_BG, 
                      foreground=FG_COLOR,
                      borderwidth=0,
                      font=('Helvetica', 10),
                      bordercolor=BG_COLOR,
                      focuscolor=BG_COLOR,
                      relief='flat',
                      padding=5)
        style.map('TButton', 
                background=[('active', BUTTON_ACTIVE_BG)],
                foreground=[('active', FG_COLOR)])

        # Main Layout
        main_frame = ttk.Frame(self.root)
        main_frame.pack(padx=20, pady=20, fill='both', expand=True)

        # Status Display
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill='x', pady=10)
        
        self.status_label = tk.Label(
            status_frame,
            text="Loading status...",
            font=('Helvetica', 14, 'bold'),
            fg=FG_COLOR,
            bg=BG_COLOR
        )
        self.status_label.pack()

        # [Keep control buttons unchanged]

        # Status Bar with Padding
        self.status_bar = tk.Label(
            self.root,
            text="Checking daemon status...",
            font=('Helvetica', 9),
            fg=FG_COLOR,
            bg=STATUS_BAR_COLOR,
            relief=tk.SUNKEN,
            anchor=tk.CENTER,
            padx=5,  # Horizontal padding
            pady=2   # Vertical padding
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 2))  # Add bottom margin

        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

    def show_window(self, icon=None, item=None):
        """Force window restoration for i3"""
        self.root.deiconify()
        self.root.attributes('-topmost', 1)
        self.root.focus_force()
        self.root.attributes('-topmost', 0)
        self.root.lift()

    # [Keep remaining methods unchanged]

if __name__ == "__main__":
    command_line_interface()





































import signal
import os

class Daemon:
    def __init__(self):
        self.feh_process = None  # Track feh process
        # ... other init code ...

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

    def cleanup_resources(self):
        """Cleanup feh process on exit"""
        if self.feh_process and self.feh_process.poll() is None:
            self.feh_process.terminate()
            self.feh_process.wait()
        # ... other cleanup code ...


















def get_default_config(self):
    """Return a dictionary of default configuration values for all sections."""
    return {
        "daemon": {
            "MAX_LOG_SIZE": 1000000,
            "LOG_LEVEL": "INFO",
            "FILES_DIRECTORY": os.path.join(USER_CONFIG_DIR, "sample"),
        },
        "image": {
            "default_resolution": "1920x1080",
            "FONT_FAMILY": "Amiri",
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
        elif key in ["FONT_FAMILY", "BG_COLOR", "TEXT_COLOR", "HIGHLIGHT_COLOR"]:
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





























# In your daemon code
import arabic_topng
import subprocess
from configparser import ConfigParser

class Daemon:
    def __init__(self):
        self.config = self.load_config()
        
    def show_verse_image(self, text, highlight_line=None):
        output_path = "/tmp/quran_verse.png"
        
        # Generate image
        success = arabic_topng.render_arabic_text_to_image(
            text=text,
            output_path=output_path,
            config=self.config,
            highlight_line=highlight_line
        )
        
        if success:
            # Display with feh
            geometry = self.config.get('image', 'default_resolution', fallback='1240x1080')
            subprocess.Popen([
                'feh', '-x', '-g', geometry,
                '--no-menus', '--auto-zoom', output_path
            ])


















import os
import configparser
from PIL import Image, ImageDraw, ImageFont
import textwrap

def rgba_from_config(config_str):
    """Convert config RGBA string to tuple"""
    return tuple(map(int, config_str.split(',')))

def render_arabic_text_to_image(text, output_path, config, highlight_line=None):
    """
    Renders Arabic text to image using settings from daemon config
    """
    try:
        # Get config values with fallbacks
        image_section = config['image']
        
        font_family = image_section.get('FONT_FAMILY', 'Amiri')
        font_size = image_section.getint('FONT_SIZE', 48)
        image_width = image_section.getint('IMAGE_WIDTH', 1240)
        wrap_width = image_section.getint('WRAP_WIDTH', 170)
        vertical_padding = image_section.getint('VERTICAL_PADDING', 20)
        
        # Parse color values
        bg_color = rgba_from_config(image_section.get('BG_COLOR', '0,0,0,0'))
        text_color = rgba_from_config(image_section.get('TEXT_COLOR', '255,255,255,255'))
        highlight_color = rgba_from_config(image_section.get('HIGHLIGHT_COLOR', '255,0,0,255'))

        # Load font
        font = ImageFont.truetype(font_family, font_size)
        
        # Original text processing
        original_lines = text.split("\n")
        lines_with_bullets = [f"•{line}" for line in original_lines]

        wrapped_lines = []
        line_mapping = []
        highlighted_lines = []

        for i, line in enumerate(lines_with_bullets):
            is_highlighted = highlight_line == (i + 1)
            wrapped = textwrap.wrap(line, width=wrap_width)

            wrapped_lines.extend(wrapped)
            line_mapping.extend([i] * len(wrapped))
            highlighted_lines.extend([is_highlighted] * len(wrapped))

        # Calculate dimensions
        draw = ImageDraw.Draw(Image.new("RGBA", (image_width, 100), bg_color))
        _, _, _, text_height = draw.textbbox((0, 0), "A", font=font)
        line_height = text_height + 24
        total_text_height = line_height * len(wrapped_lines) + 2 * vertical_padding

        # Create image
        image = Image.new("RGBA", (image_width, total_text_height), bg_color)
        draw = ImageDraw.Draw(image)
        y = vertical_padding

        for i, line in enumerate(wrapped_lines):
            text_bbox = draw.textbbox((0, 0), line, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            x = image_width - text_width - 20  # Right-aligned

            color = highlight_color if highlighted_lines[i] else text_color
            draw.text((x, y), line, font=font, fill=color, direction="rtl")
            y += line_height

        image.save(output_path, "PNG")
        return True

    except Exception as e:
        print(f"Image generation error: {str(e)}")
        return False

if __name__ == "__main__":
    # Maintain standalone functionality
    import sys
    import argparse
    
    # ... (keep original argparse implementation here for standalone use) ...





























import os
import shutil

USER_CONFIG_DIR = "path/to/user/config"  # Update with the actual path
CONTROL_DIR = "path/to/control/dir"  # Update with the actual path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
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




def handle_start(self):
    """Safe daemon startup"""
    cleanup_orphaned_files()  # Add this first
    
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
    
    # Rest of startup logic...



























def handle_play(self):
    """Handle play command"""
    self.play_audio()
    return True

def handle_pause(self):
    """Toggle playback pause state"""
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.pause()
        self.log_action("PAUSE", "Playback paused")
    else:
        pygame.mixer.music.unpause()
        self.log_action("PLAY", "Playback resumed")
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
        self.play_audio()
        return True
        
    except ValueError:
        self.log_action("ERROR", f"Invalid load format: {args}")
        return False
    except Exception as e:
        self.log_action("ERROR", f"Load failed: {str(e)}")
        return False





































def handle_play(self):
    """Handle play command (no arguments)"""
    self.play_audio()
    return True

def handle_pause(self):
    """Handle pause command (no arguments)"""
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.pause()
    else:
        pygame.mixer.music.unpause()
    return True

def handle_load(self, args):
    """Handle load command (requires arguments)"""
    try:
        surah_str, ayah_str = args.split(":", 1)
        surah = int(surah_str)
        ayah = int(ayah_str)
        
        if not (1 <= surah <= 114):
            self.log_action("ERROR", f"Invalid surah: {surah}")
            return False
            
        if ayah < 1:
            self.log_action("ERROR", f"Invalid ayah: {ayah}")
            return False

        return self.load_surah_ayah(surah, ayah)
        
    except ValueError:
        self.log_action("ERROR", f"Invalid load arguments: {args}")
        return False
    except Exception as e:
        self.log_action("ERROR", f"Load failed: {str(e)}")
        return False






















def handle_client(self, conn):
    """Handle client connection with improved argument detection"""
    try:
        data = conn.recv(1024).decode().strip()
        if not data:
            conn.sendall(b"ERROR: Empty command\n")
            return

        parts = data.split(maxsplit=1)
        command = parts[0]
        args = parts[1] if len(parts) > 1 else None

        if command not in self.valid_commands:
            conn.sendall(b"ERROR: Unknown command\n")
            return

        handler = getattr(self, f"handle_{command}", None)
        if not handler:
            conn.sendall(b"ERROR: No handler\n")
            return

        # Get parameter count excluding 'self'
        sig = inspect.signature(handler)
        param_count = len(sig.parameters) - 1  # Subtract self parameter

        # Validate arguments
        if param_count > 0 and not args:
            conn.sendall(b"ERROR: Missing arguments\n")
            return
        elif param_count > 0:
            response = handler(args)
        else:
            response = handler()

        conn.sendall(b"OK\n" if response else b"ERROR\n")
        
    except Exception as e:
        self.log_action("ERROR", f"Client error: {str(e)}")
        conn.sendall(b"ERROR: Processing failed\n")
    finally:
        conn.close()




























def handle_client(self, conn):
    """Handle client connection with proper argument checking"""
    try:
        data = conn.recv(1024).decode().strip()
        if not data:
            conn.sendall(b"ERROR: Empty command\n")
            return

        parts = data.split(maxsplit=1)
        command = parts[0]
        args = parts[1] if len(parts) > 1 else None

        if command not in self.valid_commands:
            conn.sendall(b"ERROR: Unknown command\n")
            return

        handler = getattr(self, f"handle_{command}", None)
        if not handler:
            conn.sendall(b"ERROR: No handler\n")
            return

        # Check if handler expects arguments
        params = inspect.signature(handler).parameters
        if len(params) > 1 and not args:
            conn.sendall(b"ERROR: Missing arguments\n")
            return
        elif len(params) > 1:
            success = handler(args)
        else:
            success = handler()  # Call without arguments

        conn.sendall(b"OK\n" if success else b"ERROR\n")
        
    except Exception as e:
        self.log_action("ERROR", f"Client error: {str(e)}")
        conn.sendall(b"ERROR: Processing failed\n")
    finally:
        conn.close()














class Daemon:
    # Surah-ayah count mapping (index 0 unused, 1-114 are surah numbers)
    surah_ayat = [
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
            return
            
        self.save_playback_state()
        self.play_audio()

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
            return
            
        self.save_playback_state()
        self.play_audio()
















class Daemon:
    # ... existing code ...
    
    def handle_load(self, args):
        """Handle load command with surah:ayah argument"""
        try:
            if ":" not in args:
                self.log_action("ERROR", "Invalid load format - missing colon")
                return False
                
            surah_str, ayah_str = args.split(":", 1)
            surah = int(surah_str)
            ayah = int(ayah_str)
            
            if not (1 <= surah <= 114):
                self.log_action("ERROR", f"Invalid surah: {surah}")
                return False
                
            if ayah < 1:
                self.log_action("ERROR", f"Invalid ayah: {ayah}")
                return False

            return self.load_surah_ayah(surah, ayah)
            
        except ValueError:
            self.log_action("ERROR", f"Non-numeric values in {args}")
            return False























class Daemon:
    # ... existing code ...
    
    def handle_client(self, conn):
        """Handle client connection with argument support"""
        try:
            data = conn.recv(1024).decode().strip()
            if not data:
                conn.sendall(b"ERROR: Empty command\n")
                return

            # Split command and arguments
            parts = data.split(maxsplit=1)
            command = parts[0]
            args = parts[1] if len(parts) > 1 else ""

            if command not in self.valid_commands:
                conn.sendall(b"ERROR: Unknown command\n")
                return

            handler_name = f"handle_{command}"
            handler = getattr(self, handler_name, None)
            
            if not handler:
                conn.sendall(b"ERROR: No handler\n")
                return

            # Execute with arguments
            success = handler(args)
            conn.sendall(b"OK\n" if success else b"ERROR\n")
            
        except Exception as e:
            self.log_action("ERROR", f"Client error: {str(e)}")
            conn.sendall(b"ERROR: Processing failed\n")
        finally:
            conn.close()



























class Daemon:
    # ... existing code ...
    
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

    # Example helper for command handling
    def handle_load(self, surah: int, ayah: int):
        """Command handler for loading specific ayah"""
        if self.load_surah_ayah(surah, ayah):
            self.log_action("NAV", f"Loaded {surah}:{ayah}")
        else:
            self.log_action("ERROR", f"Failed to load {surah}:{ayah}")



























I have 3 files :
uthmani quran containing text organized like this :

1|1|بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ
1|2|ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ
1|3|ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ
1|4|مَـٰلِكِ يَوْمِ ٱلدِّينِ
1|5|إِيَّاكَ نَعْبُدُ وَإِيَّاكَ نَسْتَعِينُ
1|6|ٱهْدِنَا ٱلصِّرَٰطَ ٱلْمُسْتَقِيمَ
1|7|صِرَٰطَ ٱلَّذِينَ أَنْعَمْتَ عَلَيْهِمْ غَيْرِ ٱلْمَغْضُوبِ عَلَيْهِمْ وَلَا ٱلضَّآلِّينَ
2|1|بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ الٓمٓ
2|2|ذَٰلِكَ ٱلْكِتَـٰبُ لَا رَيْبَ ۛ فِيهِ ۛ هُدًى لِّلْمُتَّقِينَ


and a similar one with simplified text :

1|1|بسم الله الرحمن الرحيم
1|2|الحمد لله رب العالمين
1|3|الرحمن الرحيم
1|4|مالك يوم الدين
1|5|إياك نعبد وإياك نستعين
1|6|اهدنا الصراط المستقيم
1|7|صراط الذين أنعمت عليهم غير المغضوب عليهم ولا الضالين
2|1|بسم الله الرحمن الرحيم الم
2|2|ذلك الكتاب لا ريب فيه هدى للمتقين
2|3|الذين يؤمنون بالغيب ويقيمون الصلاة ومما رزقناهم ينفقون


and a file with chapters names:

الفاتحة 
البقرة 
آل عمران 
النساء 
المائدة 
الأنعام 
الأعراف 
الأنفال 
التوبة 

I want to create a python script that:
when passed ayah_surah ayah_number <optional number for a range of ayat >
it will print the ayat text line by line and at the end of each line (chaptername ayah)
uthman to stdout, simplified clean text to a file

also if no argument is passed, create a dialog, change the keyboard layout  to arabic for search in the simplified arabic
, and then restores the keyboard, and then if search patter was found, show the results in the same manner 





import os
import sys
import socket
import json
import shutil
import threading
import configparser
import inspect
import time
from datetime import datetime
from threading import Lock
from pathlib import Path
import subprocess

# Define global variables
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_FILE = os.path.join(SCRIPT_DIR, "default_config.ini")
USER_CONFIG_DIR = os.path.expanduser("~/.config/quran-player")
USER_CONFIG_FILE = os.path.join(USER_CONFIG_DIR, "config.ini")
LOG_FILE = os.path.join(SCRIPT_DIR, "daemon.log")
SOCKET_FILE = os.path.join(SCRIPT_DIR, "daemon.sock")
PID_FILE = os.path.join(SCRIPT_DIR, "daemon.pid")

def ensure_config_dir():
    """Ensure user config directory exists."""
    os.makedirs(USER_CONFIG_DIR, exist_ok=True)


class Daemon:
    def __init__(self):
        self.running = False
        self.valid_commands = {
            "start": "SYSTEM",
            "stop": "SYSTEM",
            "play": "PLAY",
            "pause": "INFO",
            "prev": "INFO",
            "next": "INFO",
            "config": "SYSTEM",
        }
        self.config = self.load_config()

        # MPV IPC Setup
        self.ipc_socket = os.path.join(USER_CONFIG_DIR, "mpv_ipc.sock")
        self.mpv_process = None
        self.playback_active = False
        self.playback_thread = None
        self.last_playback_end = 0
        self.cooldown_period = 1.0  # Minimum time between state changes
        self.playback_lock = Lock()
        self.mpv_connected = False


        # State management
        self.current_surah = 1
        self.current_ayah = 1
        self.state_file = os.path.join(USER_CONFIG_DIR, "playback_state.ini")

        # Load previous state
        self.load_playback_state()

        # Audio configuration
        self.audio_base = os.path.join(
            self.config.get('mpv', 'FILES_DIRECTORY',
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

    def get_default_config(self):
        """Return a dictionary of default configuration values for all sections."""
        return {
            "daemon": {
                "example_var": "default_value",
                "MAX_LOG_SIZE": 1000000,
                "LOG_LEVEL": "INFO",
            },
            "mpv": {
                "audio_output": "auto",
                "FILES_DIRECTORY": os.path.join(USER_CONFIG_DIR, "sample"),
            },
            "image": {
                "default_resolution": "1920x1080",
                "format": "png",
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
            elif key == "LOG_LEVEL":
                if value.upper() in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                    validated_value = value.upper()
                else:
                    raise ValueError("Invalid log level.")
            elif key == "FILES_DIRECTORY":
                if os.path.isdir(value):
                    validated_value = value
                else:
                    raise ValueError("Invalid files directory.")
            elif key == "audio_output":
                # Example validation for audio output (customize as needed)
                validated_value = value  # Accept any value, could add checks
            elif key == "default_resolution":
                # Validate resolution format (e.g., '1920x1080')
                parts = value.split('x')
                if len(parts) != 2 or not all(part.isdigit() for part in parts):
                    raise ValueError("Invalid resolution format.")
                validated_value = value
            elif key == "format":
                if value.lower() in ["png", "jpeg", "gif"]:
                    validated_value = value.lower()
                else:
                    raise ValueError("Invalid image format.")
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
        ensure_config_dir()
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
        """Process a client connection in a separate thread."""
        try:
            command = conn.recv(1024).decode().strip()
            if not command:
                self.log_action("ERROR", "No command received")
                conn.sendall(b"ERROR: No command received\n")
            elif command in self.valid_commands:
                self.handle_command(command)
                conn.sendall(b"OK\n")
            else:
                self.log_action("ERROR", f"Unknown command: {command}")
                conn.sendall(b"ERROR: Unknown command\n")
        except BrokenPipeError:
            self.log_action("WARNING", "Client disconnected before response.")
        except Exception as e:
            self.log_action("ERROR", f"Client error: {e}")
        finally:
            conn.close()

    def handle_start(self):
        """Run the daemon process."""
        if os.path.exists(PID_FILE):
            self.log_action("ERROR", "Daemon already running!")
            sys.exit(1)

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

    def cleanup(self, server):
        """Clean up resources."""
        server.close()
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        if os.path.exists(SOCKET_FILE):
            os.remove(SOCKET_FILE)
        self.log_action("SYSTEM", "Cleanup completed.")

    def handle_stop(self):
        """Handle stop command."""
        self.running = False
        self.log_action("SYSTEM", "Shutdown initiated")

    def handle_play(self):
        """Handle play command."""
        print("Handling play command")
        self.monitor_playback()
        # Add actual play logic here

    def handle_pause(self):
        """Handle pause command."""
        print("Handling pause command")
        # Add actual pause logic here

    def handle_prev(self):
        """Handle previous track command."""
        print("Handling previous track")
        # Add actual prev logic here

    def handle_next(self):
        """Handle next track command."""
        print("Handling next track")
        # Add actual next logic here

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

    def mpv_command(self, command):
        """MPV command with connection state handling"""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect(self.ipc_socket)
                s.send(json.dumps(command).encode() + b"\n")
                return json.loads(s.recv(4096).decode())
        except Exception as e:
            self.mpv_connected = False
            self.log_action("WARNING", f"MPV command failed: {str(e)}")
            return None

    def verify_mpv_connection(self):
        """Check if MPV is truly responsive"""
        try:
            response = self.mpv_command({"command": ["get_property", "mpv-version"]})
            if response and "error" not in response:
                return True
            return False
        except:
            return False
            
    def start_mpv(self):
        """Robust MPV startup with detailed diagnostics"""
        try:
            # 1. Verify MPV executable exists
            mpv_path = shutil.which("mpv")
            if not mpv_path:
                self.log_action("ERROR", "MPV not found in PATH. Install with 'sudo apt install mpv'")
                return False

            # 2. Clean up previous socket file
            socket_path = Path(self.ipc_socket)
            if socket_path.exists():
                try:
                    socket_path.unlink()
                    self.log_action("DEBUG", f"Removed existing socket: {self.ipc_socket}")
                except Exception as e:
                    self.log_action("ERROR", f"Failed to remove socket: {str(e)}")
                    return False

            # 3. Start MPV process with logging
            self.log_action("DEBUG", f"Starting MPV from: {mpv_path}")
            self.mpv_process = subprocess.Popen(
                [
                    "mpv",
                    "--idle",
                    f"--input-ipc-server={self.ipc_socket}",
                    "--no-video",
                    "--no-terminal",
                    "--msg-level=all=v",  # Enable verbose logging
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge output streams
                text=True
            )

            def log_output(pipe):
                while True:
                    line = pipe.readline()
                    if not line: break
                    self.log_action("MPV_DEBUG", line.strip())

            threading.Thread(target=log_output, args=(self.mpv_process.stdout,)).start()

            # 4. Verify socket creation with timeout
            max_retries = 5
            for attempt in range(max_retries):
                if socket_path.exists():
                    # Verify socket is actually functional
                    try:
                        test_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        test_socket.connect(self.ipc_socket)
                        test_socket.close()
                        self.mpv_connected = True
                        self.log_action("INFO", "MPV connection established successfully")
                        return True
                    except Exception as e:
                        self.log_action("WARNING", f"Socket test failed: {str(e)}")

                time.sleep(0.5)
                if self.mpv_process.poll() is not None:
                    # MPV exited prematurely
                    stderr = self.mpv_process.stderr.read().decode()
                    self.log_action("ERROR", f"MPV crashed on startup. Error:\n{stderr}")
                    return False

            # 5. Final failure analysis
            self.log_action("ERROR", "Socket never appeared. Possible causes:")
            self.log_action("ERROR", f"- Check permissions on directory: {socket_path.parent}")
            self.log_action("ERROR", "- MPV version might be too old (need ≥ 0.34)")
            self.log_action("ERROR", "- AppArmor/SELinux blocking socket creation")
            return False

        except Exception as e:
            self.log_action("CRITICAL", f"MPV startup failed: {str(e)}")
            import traceback
            self.log_action("DEBUG", f"Stack trace:\n{traceback.format_exc()}")
            return False

    def play_audio(self):
        """Handle audio playback with proper threading"""
        if not self.verify_mpv_connection():
            self.log_action("ERROR", "MPV connection verification failed")
            return

        audio_path = self.get_audio_path()
        if not audio_path or not os.path.exists(audio_path):
            self.log_action("ERROR", f"Missing audio file: {audio_path}")
            return

        try:
            # Start monitoring thread first
            self.playback_active = True
            self.playback_thread = threading.Thread(
                target=self.monitor_playback,
                name="PlaybackMonitor"
            )
            self.playback_thread.start()
            
            # Send play commands after thread starts
            self.mpv_command({"command": ["stop"]})
            time.sleep(0.1)
            self.mpv_command({"command": ["loadfile", audio_path, "replace"]})
            self.log_action("PLAY", f"Started: {self.current_surah}:{self.current_ayah}")

        except Exception as e:
            self.log_action("ERROR", f"Play failed: {str(e)}")
            self.playback_active = False

    def monitor_playback(self):
        """Persistent playback monitoring with keepalive"""
        try:
            with self.playback_lock:
                self.log_action("DEBUG", "Starting monitoring loop")
                
                while self.playback_active:
                    if not self.mpv_connected:
                        self.log_action("INFO", "Reconnecting to MPV")
                        if not self.start_mpv():
                            time.sleep(1)
                            continue

                    try:
                        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                            s.settimeout(2)
                            s.connect(self.ipc_socket)
                            s.sendall(b'{"command": ["observe_property", 1, "core-idle"]}\n')
                            
                            buffer = ""
                            while self.playback_active:
                                try:
                                    data = s.recv(4096)
                                    if not data:
                                        self.log_action("WARNING", "MPV connection closed")
                                        break
                                    
                                    buffer += data.decode()
                                    while "\n" in buffer:
                                        line, buffer = buffer.split("\n", 1)
                                        self.process_mpv_event(line.strip())

                                except socket.timeout:
                                    # Send keepalive
                                    s.sendall(b'{"command": ["get_time"]}\n')
                                    continue

                    except (ConnectionRefusedError, FileNotFoundError):
                        self.mpv_connected = False
                        time.sleep(1)
                        
                    except Exception as e:
                        self.log_action("ERROR", f"Monitoring error: {str(e)}")
                        self.mpv_connected = False

        except Exception as e:
            self.log_action("CRITICAL", f"Monitoring crashed: {str(e)}")
            
        finally:
            self.playback_active = False
            self.log_action("INFO", "Playback monitoring stopped")

    def process_mpv_event(self, line):
        """Process individual MPV events"""
        try:
            data = json.loads(line)
            current_time = time.time()
            
            # Handle core-idle state
            if data.get("event") == "property-change" \
                    and data.get("name") == "core-idle" \
                    and data.get("data") is True:
                if current_time - self.last_playback_end > self.cooldown_period:
                    self.log_action("DEBUG", "Valid idle state detected")
                    self.last_playback_end = current_time
                    self.handle_playback_end()
                    
        except json.JSONDecodeError:
            self.log_action("WARNING", f"Invalid JSON: {line[:50]}...")
        except KeyError as e:
            self.log_action("WARNING", f"Missing key in event: {str(e)}")

    def handle_playback_end(self):
        """Safe state update handler"""
        # Verify MPV is still connected
        if not self.verify_mpv_connection():
            self.log_action("ERROR", "Skipping state update - MPV disconnected")
            return
            
        try:
            # Original playback validation
            original_path = self.get_audio_path()
            if not original_path or not os.path.exists(original_path):
                self.log_action("ERROR", "Original file missing, aborting update")
                return

            # Increment state
            new_ayah = self.current_ayah + 1
            new_surah = self.current_surah
            
            # Validate next file before committing
            self.current_ayah = new_ayah
            next_path = self.get_audio_path()
            if not next_path or not os.path.exists(next_path):
                self.log_action("WARNING", "Next file missing, resetting")
                self.current_ayah = 1
                self.current_surah = 1 if new_surah > 114 else new_surah
                next_path = self.get_audio_path()
                
                if not next_path or not os.path.exists(next_path):
                    self.log_action("ERROR", "Critical failure: Base file missing")
                    self.playback_active = False
                    return

            # Commit state
            self.save_playback_state()
            self.log_action("INFO", f"New state: {self.current_surah}:{self.current_ayah}")

            # Play next file
            self.play_audio()

        except Exception as e:
            self.log_action("ERROR", f"Playback end failed: {str(e)}")
            self.playback_active = False

    def stop_playback(self):
        """Stop current playback"""
        if self.mpv_process:
            self.mpv_command({"command": ["stop"]})
            self.playback_active = False
            self.log_action("SYSTEM", "Playback stopped")

    def log_thread_status(self):
        active = [t.name for t in threading.enumerate()]
        self.log_action("DEBUG", f"Active threads: {active}")


def print_usage():
    print("Usage: python3 quran-player.py <command>")
    print("Commands:")
    print("  start   - Start the daemon")
    print("  stop    - Stop the daemon")
    print("  play    - Play the track")
    print("  pause   - Pause playback")
    print("  prev    - Play previous track")
    print("  next    - Play next track")
    print("  config  - Generate default config file")

if __name__ == "__main__":
    daemon = Daemon()

    if len(sys.argv) < 2:  # No command provided
        print_usage()
        sys.exit(1)

    command = sys.argv[1]

    if command == "start":
        daemon.handle_start()
    elif command in ["stop", "play", "pause", "prev", "next", "config"]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            try:
                client.connect(SOCKET_FILE)
                client.sendall(command.encode() + b"\n")
                print(client.recv(1024).decode().strip())
            except Exception as e:
                print(f"Error: {e}")
    else:
        print_usage()
        sys.exit(1)



I want you to simplify mpv play audio related methods, they do not work
































class Daemon:
    def __init__(self):
        # ... (keep previous initializations)
        self.mpv_process = None
        self.current_playback_thread = None

    def start_mpv(self):
        """Simplified MPV startup with IPC socket"""
        if self.mpv_process and self.mpv_process.poll() is None:
            return True

        try:
            self.mpv_process = subprocess.Popen(
                ["mpv", "--idle", f"--input-ipc-server={self.ipc_socket}", "--no-video"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1)  # Allow socket creation
            return True
        except Exception as e:
            self.log_action("ERROR", f"MPV startup failed: {e}")
            return False

    def mpv_command(self, command):
        """Send command to MPV with basic error handling"""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(self.ipc_socket)
                s.send(json.dumps({"command": command}).encode() + b"\n")
                return json.loads(s.recv(4096).decode())
        except Exception as e:
            self.log_action("ERROR", f"MPV command failed: {e}")
            return None

    def play_audio(self):
        """Simplified play handling with polling-based completion check"""
        if not self.start_mpv():
            return

        audio_path = self.get_audio_path()
        if not audio_path:
            return

        # Stop any existing playback
        self.mpv_command(["stop"])
        
        # Start new playback
        response = self.mpv_command(["loadfile", audio_path])
        if not response or response.get("error") != "success":
            self.log_action("ERROR", "Failed to start playback")
            return

        # Start completion monitoring in background
        self.current_playback_thread = threading.Thread(
            target=self.monitor_playback_status,
            daemon=True
        )
        self.current_playback_thread.start()

    def monitor_playback_status(self):
        """Poll MPV status until playback completes"""
        while True:
            time.sleep(0.5)
            status = self.mpv_command(["get_property", "idle-active"])
            
            if not status or status.get("data"):
                self.handle_playback_end()
                break

    def handle_playback_end(self):
        """Handle track completion and play next"""
        self.current_ayah += 1
        # Add boundary checks (e.g., surah/ayah limits)
        self.save_playback_state()
        self.play_audio()

    def stop_playback(self):
        """Stop current playback"""
        self.mpv_command(["stop"])
        if self.current_playback_thread:
            self.current_playback_thread.join()






























def start_mpv(self):
    """Robust MPV startup with detailed diagnostics"""
    try:
        # 1. Verify MPV executable exists
        mpv_path = shutil.which("mpv")
        if not mpv_path:
            self.log_action("ERROR", "MPV not found in PATH. Install with 'sudo apt install mpv'")
            return False

        # 2. Clean up previous socket file
        socket_path = Path(self.ipc_socket)
        if socket_path.exists():
            try:
                socket_path.unlink()
                self.log_action("DEBUG", f"Removed existing socket: {self.ipc_socket}")
            except Exception as e:
                self.log_action("ERROR", f"Failed to remove socket: {str(e)}")
                return False

        # 3. Start MPV process with logging
        self.log_action("DEBUG", f"Starting MPV from: {mpv_path}")
        self.mpv_process = subprocess.Popen(
            [
                "mpv",
                "--idle",
                f"--input-ipc-server={self.ipc_socket}",
                "--no-video",
                "--no-terminal",
                "--msg-level=all=no",  # Suppress all messages
                "--really-quiet",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 4. Verify socket creation with timeout
        max_retries = 5
        for attempt in range(max_retries):
            if socket_path.exists():
                # Verify socket is actually functional
                try:
                    test_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    test_socket.connect(self.ipc_socket)
                    test_socket.close()
                    self.mpv_connected = True
                    self.log_action("INFO", "MPV connection established successfully")
                    return True
                except Exception as e:
                    self.log_action("WARNING", f"Socket test failed: {str(e)}")

            time.sleep(0.5)
            if self.mpv_process.poll() is not None:
                # MPV exited prematurely
                stderr = self.mpv_process.stderr.read().decode()
                self.log_action("ERROR", f"MPV crashed on startup. Error:\n{stderr}")
                return False

        # 5. Final failure analysis
        self.log_action("ERROR", "Socket never appeared. Possible causes:")
        self.log_action("ERROR", f"- Check permissions on directory: {socket_path.parent}")
        self.log_action("ERROR", "- MPV version might be too old (need ≥ 0.34)")
        self.log_action("ERROR", "- AppArmor/SELinux blocking socket creation")
        return False

    except Exception as e:
        self.log_action("CRITICAL", f"MPV startup failed: {str(e)}")
        import traceback
        self.log_action("DEBUG", f"Stack trace:\n{traceback.format_exc()}")
        return False

def verify_mpv_connection(self):
    """Manual connection test method"""
    try:
        test_cmd = json.dumps({"command": ["get_version"]})
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect(self.ipc_socket)
            s.sendall(test_cmd.encode() + b"\n")
            response = s.recv(1024).decode()
            self.log_action("DEBUG", f"MPV test response: {response}")
            return True
    except Exception as e:
        self.log_action("ERROR", f"MPV verification failed: {str(e)}")
        return False































import time
from threading import Lock

class Daemon:
    def __init__(self):
        # Add these new instance variables
        self.last_playback_end = 0
        self.cooldown_period = 1.0  # Minimum time between state changes
        self.playback_lock = Lock()
        self.mpv_connected = False

    def mpv_command(self, command):
        """MPV command with connection state handling"""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect(self.ipc_socket)
                s.send(json.dumps(command).encode() + b"\n")
                return json.loads(s.recv(4096).decode())
        except Exception as e:
            self.mpv_connected = False
            self.log_action("WARNING", f"MPV command failed: {str(e)}")
            return None

    def monitor_playback(self):
        """Robust playback monitoring with cooldown checks"""
        try:
            with self.playback_lock:
                if not self.mpv_connected:
                    self.log_action("INFO", "Reconnecting to MPV")
                    if not self.start_mpv():
                        return

                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.connect(self.ipc_socket)
                    s.send(b'{"command": ["observe_property", 1, "core-idle"]}\n')
                    
                    buffer = ""
                    while self.playback_active:
                        try:
                            response = s.recv(4096).decode()
                            if not response:
                                continue
                                
                            buffer += response
                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)
                                line = line.strip()
                                if not line:
                                    continue

                                try:
                                    data = json.loads(line)
                                    current_time = time.time()
                                    
                                    # Cooldown check
                                    if current_time - self.last_playback_end < self.cooldown_period:
                                        continue
                                        
                                    # Handle core-idle state
                                    if data.get("event") == "property-change" and \
                                       data.get("name") == "core-idle" and \
                                       data.get("data") is True:
                                        self.log_action("DEBUG", "Valid idle state detected")
                                        self.last_playback_end = current_time
                                        self.handle_playback_end()
                                        break

                                except json.JSONDecodeError:
                                    continue

        except Exception as e:
            self.log_action("ERROR", f"Monitoring error: {str(e)}")
        finally:
            self.playback_active = False
            self.playback_thread = None

    def handle_playback_end(self):
        """Atomic state handler with validation"""
        try:
            # Validate current file actually played
            original_path = self.get_audio_path()
            if not original_path or not os.path.exists(original_path):
                self.log_action("ERROR", "Original file validation failed")
                return

            # Increment state
            new_ayah = self.current_ayah + 1
            new_surah = self.current_surah
            
            # Validate next file before committing
            self.current_ayah = new_ayah
            next_path = self.get_audio_path()
            if not next_path or not os.path.exists(next_path):
                self.log_action("WARNING", "Next file missing, resetting")
                self.current_ayah = 1
                self.current_surah = 1 if new_surah > 114 else new_surah
                next_path = self.get_audio_path()
                
                if not next_path or not os.path.exists(next_path):
                    self.log_action("ERROR", "Critical failure: Base file missing")
                    self.playback_active = False
                    return

            # Commit state
            self.save_playback_state()
            self.log_action("INFO", f"New state: {self.current_surah}:{self.current_ayah}")

            # Play next file
            self.play_audio()

        except Exception as e:
            self.log_action("ERROR", f"Playback end failed: {str(e)}")
            self.playback_active = False

    def start_mpv(self):
        """MPV startup with connection verification"""
        try:
            # Cleanup old processes
            if self.mpv_process and self.mpv_process.poll() is None:
                self.mpv_process.terminate()
                self.mpv_process.wait(2)

            # Remove old socket
            if os.path.exists(self.ipc_socket):
                os.remove(self.ipc_socket)

            # Start new instance
            self.mpv_process = subprocess.Popen([
                "mpv", "--idle",
                "--input-ipc-server=" + self.ipc_socket,
                "--no-video", "--keep-open=no",
                "--audio-display=no", "--msg-level=ipc=no"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Verify connection
            for _ in range(5):
                if os.path.exists(self.ipc_socket):
                    self.mpv_connected = True
                    return True
                time.sleep(0.2)
            raise Exception("MPV socket not created")

        except Exception as e:
            self.log_action("ERROR", f"MPV startup failed: {str(e)}")
            return False

    def play_audio(self):
        """Play audio with pre-validation"""
        if not self.mpv_connected:
            self.log_action("WARNING", "Skipping play - MPV not connected")
            return

        audio_path = self.get_audio_path()
        if not audio_path or not os.path.exists(audio_path):
            self.log_action("ERROR", f"Critical missing file: {audio_path}")
            return

        try:
            self.mpv_command({"command": ["stop"]})
            time.sleep(0.2)
            self.mpv_command({"command": ["loadfile", audio_path, "replace"]})
            self.log_action("PLAY", f"Started: {self.current_surah}:{self.current_ayah}")
        except Exception as e:
            self.log_action("ERROR", f"Play failed: {str(e)}")





































def monitor_playback(self):
    """Monitor playback completion using MPV events"""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.ipc_socket)
            s.send(b'{"command": ["observe_property", 1, "idle-active"]}\n')

            buffer = ""
            while self.playback_active:
                # Read larger chunks and handle partial JSON
                response = s.recv(4096).decode()
                if not response:
                    continue

                buffer += response
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        self.log_action("DEBUG", f"MPV response: {line[:80]}...")  # Truncate long lines

                        # Handle end-file event
                        if data.get("event") == "end-file":
                            if data.get("reason") == "eof":
                                self.log_action("INFO", "Playback completed normally")
                                self.handle_playback_end()
                                break

                        # Handle idle state change
                        if data.get("event") == "property-change" and \
                           data.get("name") == "idle-active" and \
                           data.get("data") is True:
                            self.log_action("INFO", "Playback finished, MPV is idle")
                            self.handle_playback_end()
                            break

                    except json.JSONDecodeError as e:
                        self.log_action("WARNING", f"Failed to parse JSON: {line} | Error: {str(e)}")
                        continue

    except Exception as e:
        self.log_action("ERROR", f"Monitoring error: {str(e)}")
    finally:
        self.playback_active = False
        self.playback_thread = None
        self.log_action("DEBUG", "Playback monitoring stopped")















+++++++++++++++++++++++++
    def monitor_playback(self):
        """Monitor playback completion using MPV events"""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(self.ipc_socket)
                s.send(b'{"command": ["observe_property", 1, "idle-active"]}\n')

                buffer = ""
                while self.playback_active:
                    # Read larger chunks and handle partial JSON
                    response = s.recv(4096).decode()
                    if not response:
                        continue

                    buffer += response
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                            self.log_action("DEBUG", f"MPV response: {line[:80]}...")  # Truncate long lines

                            # Handle end-file event
                            if data.get("event") == "end-file":
                                if data.get("reason") == "eof":
                                    self.log_action("INFO", "Playback completed normally")
                                    self.handle_playback_end()
                                    break

                            # Handle idle state change
                            if data.get("event") == "property-change" and \
                               data.get("name") == "idle-active" and \
                               data.get("data") is True:
                                self.log_action("INFO", "Playback finished, MPV is idle")
                                self.handle_playback_end()
                                break

                        except json.JSONDecodeError as e:
                            self.log_action("WARNING", f"Failed to parse JSON: {line} | Error: {str(e)}")
                            continue

        except Exception as e:
            self.log_action("ERROR", f"Monitoring error: {str(e)}")
        finally:
            self.playback_active = False
            self.playback_thread = None
            self.log_action("DEBUG", "Playback monitoring stopped")





















def monitor_playback(self):
    """Monitor playback completion using MPV events"""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.ipc_socket)
            s.send(b'{"command": ["observe_property", 1, "idle-active"]}\n')

            while self.playback_active:
                response = s.recv(1024).decode().strip()
                if not response:
                    continue

                self.log_action("DEBUG", f"MPV response: {response}")
                data = json.loads(response)

                # Check for end of file event
                if data.get("event") == "end-file":
                    reason = data.get("reason", "")
                    if reason == "eof":
                        self.log_action("DEBUG", "Playback naturally completed")
                        self.handle_playback_end()
                        break

                # Check if player is idle
                if data.get("event") == "property-change" and \
                   data.get("name") == "idle-active" and \
                   data.get("data") is True:
                    self.log_action("DEBUG", "MPV entered idle state")
                    self.handle_playback_end()
                    break

    except Exception as e:
        self.log_action("ERROR", f"Monitoring error: {str(e)}")
    finally:
        self.playback_active = False
        self.playback_thread = None
        self.log_action("DEBUG", "Playback monitoring stopped")

def handle_playback_end(self):
    """Handle successful playback completion"""
    try:
        # Increment ayah number
        self.current_ayah += 1
        self.log_action("DEBUG", f"Incremented ayah to {self.current_ayah}")

        # Check if next ayah exists
        if not self.get_audio_path():
            self.log_action("INFO", "Reached end of surah, resetting to ayah 1")
            self.current_ayah = 1
            self.current_surah += 1  # Optional: Implement surah boundary logic

        self.save_playback_state()
        self.log_action("INFO", f"New state: {self.current_surah}:{self.current_ayah}")

        # Auto-play next ayah
        self.log_action("DEBUG", "Starting next playback")
        self.play_audio()

    except Exception as e:
        self.log_action("ERROR", f"Playback end handler failed: {str(e)}")



















import os
import subprocess
import threading
import json
import socket
import time
from pathlib import Path

class Daemon:
    def __init__(self):
        # MPV IPC Setup
        self.ipc_socket = os.path.join(USER_CONFIG_DIR, "mpv_ipc.sock")
        self.mpv_process = None
        self.playback_active = False
        self.playback_thread = None

        # State management
        self.current_surah = 1
        self.current_ayah = 1
        self.state_file = os.path.join(USER_CONFIG_DIR, "playback_state.ini")
        self.load_playback_state()

    def mpv_command(self, command):
        """Send commands to MPV via IPC"""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(self.ipc_socket)
                s.send(json.dumps(command).encode() + b"\n")
                response = s.recv(1024)
                return json.loads(response.decode())
        except Exception as e:
            self.log_action("ERROR", f"MPV command failed: {str(e)}")
            return None

    def start_mpv(self):
        """Start MPV with IPC socket"""
        if self.mpv_process and self.mpv_process.poll() is None:
            return True

        try:
            self.mpv_process = subprocess.Popen([
                "mpv",
                "--idle",
                "--input-ipc-server=" + self.ipc_socket,
                "--no-video",
                "--no-terminal",
                "--audio-display=no"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)  # Wait for socket creation
            return True
        except Exception as e:
            self.log_action("ERROR", f"MPV startup failed: {str(e)}")
            return False

    def play_audio(self):
        """Handle audio playback with IPC control"""
        if not self.start_mpv():
            return

        audio_path = self.get_audio_path()
        if not audio_path:
            return

        try:
            # Load and play file
            self.mpv_command({"command": ["loadfile", audio_path, "replace"]})

            # Start playback monitoring
            self.playback_active = True
            self.playback_thread = threading.Thread(target=self.monitor_playback)
            self.playback_thread.start()

            self.log_action("PLAY", f"Started: {self.current_surah}:{self.current_ayah}")
        except Exception as e:
            self.log_action("ERROR", f"Playback failed: {str(e)}")

    def monitor_playback(self):
        """Monitor playback status through MPV properties"""
        try:
            while self.playback_active:
                # Check playback time remaining
                status = self.mpv_command({"command": ["get_property", "time-remaining"]})

                if status is None or status.get("error") == "success":
                    time.sleep(0.5)
                    continue

                # When playback completes
                if status.get("data") == 0:
                    self.playback_active = False
                    self.handle_playback_end()
                    break

                time.sleep(1)

        except Exception as e:
            self.log_action("ERROR", f"Monitoring error: {str(e)}")
        finally:
            self.playback_thread = None

    def handle_playback_end(self):
        """Handle post-playback operations"""
        try:
            # Update state
            self.current_ayah += 1
            if not self.get_audio_path():
                self.current_ayah = 1
                self.current_surah += 1  # Optionally handle surah boundaries

            self.save_playback_state()
            self.log_action("INFO", f"Playback completed. New state: {self.current_surah}:{self.current_ayah}")

            # IMAGE GENERATION HOOK - Add here

            # Auto-play next ayah
            self.play_audio()

        except Exception as e:
            self.log_action("ERROR", f"Playback end handler failed: {str(e)}")

    def stop_playback(self):
        """Stop current playback"""
        if self.mpv_process:
            self.mpv_command({"command": ["stop"]})
            self.playback_active = False
            self.log_action("SYSTEM", "Playback stopped")

    # ... [Keep existing state management methods] ...
















import os
import subprocess
import threading
import configparser

class Daemon:
    def __init__(self):
        # Playback state
        self.current_surah = 1
        self.current_ayah = 1
        self.player_process = None
        self.playback_lock = threading.Lock()
        self.state_file = os.path.join(USER_CONFIG_DIR, "playback_state.ini")

        # Load previous state
        self.load_playback_state()

        # Audio configuration
        self.audio_base = os.path.join(
            self.config.get('paths', 'FILES_DIRECTORY',
                          fallback=os.path.join(USER_CONFIG_DIR, "quran-player/sample"))
        )

    def load_playback_state(self):
        """Load playback state from previous session"""
        state = configparser.ConfigParser()
        if os.path.exists(self.state_file):
            try:
                state.read(self.state_file)
                self.current_surah = state.getint('state', 'surah', fallback=1)
                self.current_ayah = state.getint('state', 'ayah', fallback=1)
            except Exception as e:
                self.log_action("ERROR", f"Failed loading state: {str(e)}")

    def save_playback_state(self):
        """Persist current playback state"""
        state = configparser.ConfigParser()
        state['state'] = {
            'surah': str(self.current_surah),
            'ayah': str(self.current_ayah)
        }
        try:
            with open(self.state_file, 'w') as f:
                state.write(f)
        except Exception as e:
            self.log_action("ERROR", f"Failed saving state: {str(e)}")

    def get_audio_path(self):
        """Get validated audio path with fallback logic"""
        audio_file = f"{self.current_surah:03}_{self.current_ayah:03}.mp3"
        path = os.path.join(self.audio_base, audio_file)

        if not os.path.exists(path):
            self.log_action("WARNING", f"Audio file missing: {path}")
            return None

        return path

    def play_audio(self):
        """Handle audio playback with state management"""
        with self.playback_lock:
+++++++++++++++++++
            if self.player_process and self.player_process.poll() is None:
                self.log_action("WARNING", "Playback already in progress")
                return

            audio_path = self.get_audio_path()
            original_ayah = self.current_ayah

            # Fallback to ayah 1 if needed
            if not audio_path:
                self.log_action("ERROR", "Missing audio, resetting to ayah 1")
                self.current_ayah = 1
                self.save_playback_state()
                audio_path = self.get_audio_path()
                if not audio_path:
                    self.log_action("ERROR", "Fallback ayah 1 also missing")
                    return

            try:
                self.log_action("PLAY", f"Starting playback: {audio_path}")

                # IMAGE GENERATION HOOK - Add pre-playback image display here

                self.player_process = subprocess.Popen(
                    ["mpv", "--no-video", audio_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                # Start playback monitoring thread
                threading.Thread(target=self.monitor_playback, args=(original_ayah,)).start()
            except Exception as e:
                self.log_action("ERROR", f"Playback failed: {str(e)}")
                self.player_process = None

    def monitor_playback(self, original_ayah):
        """Monitor playback completion and update state"""
        try:
            exit_code = self.player_process.wait()

            if exit_code == 0:
                # Only increment if we played the original requested ayah
                if self.current_ayah == original_ayah:
                    self.current_ayah += 1

                    # Check if next ayah exists
                    if not self.get_audio_path():
                        self.current_ayah = 1
                        self.log_action("INFO", "Resetting to ayah 1 for next playback")

                    self.save_playback_state()

                    # IMAGE GENERATION HOOK - Add post-playback image update here

                self.log_action("INFO", f"Playback completed. New state: {self.current_surah}:{self.current_ayah}")
            else:
                self.log_action("ERROR", f"Playback failed with code {exit_code}")
        except Exception as e:
            self.log_action("ERROR", f"Playback monitoring failed: {str(e)}")









import os
import subprocess
from pathlib import Path

class Daemon:
    def __init__(self):
        # State management
        self.current_surah = 1
        self.current_ayah = 1
        self.player_process = None  # Holds subprocess.Popen instance
        self.state_file = os.path.join(USER_CONFIG_DIR, "playback_state.ini")

        # Load previous state
        self.load_playback_state()

        # Audio configuration
        self.audio_base = os.path.join(
            self.config.get('paths', 'FILES_DIRECTORY',
                          fallback=os.path.join(USER_CONFIG_DIR, "quran-player/sample"))
        )

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
        audio_file = f"{self.current_surah:03}_{self.current_ayah:03}.mp3"
        path = os.path.join(self.audio_base, audio_file)

        if not os.path.exists(path):
            self.log_action("ERROR", f"Audio file missing: {path}")
            return None

        return path

    def play_audio(self):
        """Play current ayah and monitor playback"""
        if self.player_process and self.player_process.poll() is None:
            self.log_action("WARNING", "Playback already in progress")
            return

        audio_path = self.get_audio_path()
        if not audio_path:
            return

        try:
            # IMAGE GENERATION HOOK #1 - Add pre-playback image generation here
            self.player_process = subprocess.Popen(
                ["mpv", "--no-video", audio_path],
                stdout=subprocess.DEVNULL










for play,pause,next,prev commands, aeventually more
they all will call player method
player method will need to do:
need current ayah, surah if not playing or if called by next, prev methods
assume there is a script that will prepare ayah text
assume there is a script that will convert ayah text to png image
these scripts need to use config known to the daemon at the start
then with image generated and opened in feh
run audio file prepared from the numbers: (ayah,surah) and a "FILES_DIRECTORY"
variable that default to "user config dir/quran-player/sample"
that will be dumped with a few audio files that will be available in script current directory

which paradigm is better to use, implement these functions in the daemon script
or create multiple smaller scripts to handle these functions











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

# Add these to the Daemon class
def handle_stop(self):
    """Handle stop command."""
    self.running = False
    self.log_action("SYSTEM", "Shutdown initiated")

def handle_config(self):
    """Handle config command."""
    self.dump_default_config()

def handle_play(self):
    """Handle play command."""
    print("Handling play command")
    # Add actual play logic here

def handle_pause(self):
    """Handle pause command."""
    print("Handling pause command")
    # Add actual pause logic here

def handle_prev(self):
    """Handle previous track command."""
    print("Handling previous track")
    # Add actual prev logic here

def handle_next(self):
    """Handle next track command."""
    print("Handling next track")
    # Add actual next logic here

def handle_start(self):
    """Handle start command (if needed post-initialization)."""
    print("Handling start command")
    # Useful if you need restart functionality later
















def start(self):
    """Run the daemon process."""
    if os.path.exists(PID_FILE):
        self.log_action("ERROR", "Daemon already running!")
        sys.exit(1)

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

def cleanup(self, server):
    """Clean up resources."""
    server.close()
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    if os.path.exists(SOCKET_FILE):
        os.remove(SOCKET_FILE)
    self.log_action("SYSTEM", "Cleanup completed.")



















import os
import sys
import socket
import threading
import configparser
import inspect
from datetime import datetime

# ... [Keep previous global variables and helper functions] ...

class Daemon:
    def __init__(self):
        self.running = False
        self.valid_commands = {
            "start": "SYSTEM",
            "stop": "SYSTEM",
            "play": "PLAY",
            "pause": "INFO",
            "prev": "INFO",
            "next": "INFO",
            "config": "SYSTEM",
        }
        self.config = self.load_config()

    # ... [Keep log_action, ensure_config_dir, get_default_config] ...

    def validate_config_value(self, section, key, value, default_value):
        """Validate and convert the config value for a given section and key."""
        validated_value = default_value  # Fallback to default

        try:
            if key == "MAX_LOG_SIZE":
                validated_value = int(value)
                if validated_value <= 0:
                    raise ValueError("Must be positive.")
            elif key == "LOG_LEVEL":
                if value.upper() in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                    validated_value = value.upper()
                else:
                    raise ValueError("Invalid log level.")
            elif key == "video_quality":
                if value.lower() in ["high", "medium", "low"]:
                    validated_value = value.lower()
                else:
                    raise ValueError("Invalid video quality.")
            elif key == "audio_output":
                # Example validation for audio output (customize as needed)
                validated_value = value  # Accept any value, could add checks
            elif key == "default_resolution":
                # Validate resolution format (e.g., '1920x1080')
                parts = value.split('x')
                if len(parts) != 2 or not all(part.isdigit() for part in parts):
                    raise ValueError("Invalid resolution format.")
                validated_value = value
            elif key == "format":
                if value.lower() in ["png", "jpeg", "gif"]:
                    validated_value = value.lower()
                else:
                    raise ValueError("Invalid image format.")
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

    def dump_default_config(self):
        """Write the default configuration to the user's config file."""
        ensure_config_dir()
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

    # ... [Keep the rest of the methods unchanged] ...






























class Daemon:
    def __init__(self):
        self.running = False
        self.valid_commands = {
            "start": "SYSTEM",
            "stop": "SYSTEM",
            "play": "PLAY",
            "pause": "INFO",
            "prev": "INFO",
            "next": "INFO",
            "config": "SYSTEM",
        }
        self.config = self.load_config()

    def log_action(self, flag, msg):
        """Log an action with timestamp, PID, method, flag, and message."""
        method = inspect.currentframe().f_back.f_code.co_name
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        pid = os.getpid()
        log_entry = f"{timestamp}|{pid}|{method}|{flag}|{msg}\n"
        with open(LOG_FILE, "a") as log:
            log.write(log_entry)

    def get_default_config(self):
        """Return a dictionary of default configuration values for all sections."""
        return {
            "daemon": {
                "example_var": "default_value",
                "MAX_LOG_SIZE": 1000000,
                "LOG_LEVEL": "INFO",
            },
            "mpv": {
                "video_quality": "high",
                "audio_output": "auto",
            },
            "image": {
                "default_resolution": "1920x1080",
                "format": "png",
            },
            # Add new sections as needed
        }

    def validate_config_value(self, section, key, value, default_value):
        """Validate the config value for a given section and key."""
        # Integer validation for certain keys (e.g., MAX_LOG_SIZE)
        if key == "MAX_LOG_SIZE":
            try:
                value = int(value)
                if value <= 0:
                    raise ValueError("Invalid value for MAX_LOG_SIZE, must be a positive integer.")
            except (ValueError, TypeError):
                value = default_value  # Fallback to default
                self.log_action("WARNING", f"Invalid value for {key}, using default.")

        # Validate other keys (e.g., LOG_LEVEL, video_quality, etc.)
        elif key == "LOG_LEVEL":
            if value not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                value = default_value
                self.log_action("WARNING", f"Invalid {key} value, using default.")

        # Add more conditions for other key types if needed

        return value

    def load_config(self):
        """Load configuration from default and user config file."""
        config = configparser.ConfigParser()
        defaults = self.get_default_config()

        # Load the default values into the config
        for section, values in defaults.items():
            if not config.has_section(section):
                config.add_section(section)
            for key, value in values.items():
                config.set(section, key, str(value))

        if os.path.exists(USER_CONFIG_FILE):
            config.read(USER_CONFIG_FILE)
            self.log_action("SYSTEM", f"Loaded config from {USER_CONFIG_FILE}")
        else:
            self.log_action("WARNING", "No user config found, using defaults.")

        # Validate and load each section's variables
        for section, values in defaults.items():
            for key, default_value in values.items():
                config_value = config.get(section, key, fallback=str(default_value))
                validated_value = self.validate_config_value(section, key, config_value, default_value)
                setattr(self, key.lower(), validated_value)

        return config

    def dump_default_config(self):
        """Write default config to user directory."""
        ensure_config_dir()
        with open(USER_CONFIG_FILE, "w") as configfile:
            self.config.write(configfile)
        self.log_action("SYSTEM", f"Default config written to {USER_CONFIG_FILE}")

    def handle_command(self, command):
        """Process a received command."""
        if command in self.valid_commands:
            self.log_action(self.valid_commands[command], f"Executing command: {command}")
            if command == "config":
                self.dump_default_config()
            elif command == "stop":
                self.running = False
        else:
            self.log_action("ERROR", f"Unknown command: {command}")

    # Other methods remain the same...















class Daemon:
    def __init__(self):
        self.running = False
        self.valid_commands = {
            "start": "SYSTEM",
            "stop": "SYSTEM",
            "play": "PLAY",
            "pause": "INFO",
            "prev": "INFO",
            "next": "INFO",
            "config": "SYSTEM",
        }
        self.config = self.load_config()

    def log_action(self, flag, msg):
        """Log an action with timestamp, PID, method, flag, and message."""
        method = inspect.currentframe().f_back.f_code.co_name
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        pid = os.getpid()
        log_entry = f"{timestamp}|{pid}|{method}|{flag}|{msg}\n"
        with open(LOG_FILE, "a") as log:
            log.write(log_entry)

    def load_config(self):
        """Load configuration from default and user config file."""
        config = configparser.ConfigParser()
        config["daemon"] = {"example_var": "default_value", "MAX_LOG_SIZE": "1000000", "LOG_LEVEL": "INFO"}

        if os.path.exists(USER_CONFIG_FILE):
            config.read(USER_CONFIG_FILE)
            self.log_action("SYSTEM", f"Loaded config from {USER_CONFIG_FILE}")
        else:
            self.log_action("WARNING", "No user config found, using defaults.")

        # Handle MAX_LOG_SIZE: Ensure it's a valid number
        try:
            max_log_size = int(config.get("daemon", "MAX_LOG_SIZE"))
            if max_log_size <= 0:
                raise ValueError("Invalid value for MAX_LOG_SIZE, must be a positive integer.")
        except (ValueError, TypeError):
            max_log_size = int(config["daemon"]["MAX_LOG_SIZE"])  # Fallback to default value
            self.log_action("WARNING", "Invalid MAX_LOG_SIZE value, using default.")
        self.max_log_size = max_log_size

        # Handle LOG_LEVEL: Read as string (no validation required for this)
        log_level = config.get("daemon", "LOG_LEVEL", fallback="INFO")
        self.log_level = log_level

        return config

    def dump_default_config(self):
        """Write default config to user directory."""
        ensure_config_dir()
        with open(USER_CONFIG_FILE, "w") as configfile:
            self.config.write(configfile)
        self.log_action("SYSTEM", f"Default config written to {USER_CONFIG_FILE}")

    def handle_command(self, command):
        """Process a received command."""
        if command in self.valid_commands:
            self.log_action(self.valid_commands[command], f"Executing command: {command}")
            if command == "config":
                self.dump_default_config()
            elif command == "stop":
                self.running = False
        else:
            self.log_action("ERROR", f"Unknown command: {command}")

    # Other methods remain the same...






class Daemon:
    def __init__(self):
        self.running = False
        self.valid_commands = {
            "start": "SYSTEM",
            "stop": "SYSTEM",
            "play": "PLAY",
            "pause": "INFO",
            "prev": "INFO",
            "next": "INFO",
            "config": "SYSTEM",
        }
        self.config = self.load_config()

    def log_action(self, flag, msg):
        """Log an action with timestamp, PID, method, flag, and message."""
        method = inspect.currentframe().f_back.f_code.co_name
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        pid = os.getpid()
        log_entry = f"{timestamp}|{pid}|{method}|{flag}|{msg}\n"
        with open(LOG_FILE, "a") as log:
            log.write(log_entry)

    def get_default_config(self):
        """Return a dictionary of default configuration values for all sections."""
        return {
            "daemon": {
                "example_var": "default_value",
                "MAX_LOG_SIZE": 1000000,
                "LOG_LEVEL": "INFO",
            },
            "mpv": {
                "video_quality": "high",
                "audio_output": "auto",
            },
            "image": {
                "default_resolution": "1920x1080",
                "format": "png",
            },
            # Add new sections as needed
        }

    def validate_max_log_size(self, value):
        """Ensure MAX_LOG_SIZE is a valid integer and positive."""
        try:
            max_log_size = int(value)
            if max_log_size <= 0:
                raise ValueError("Invalid value for MAX_LOG_SIZE, must be a positive integer.")
            return max_log_size
        except (ValueError, TypeError):
            self.log_action("WARNING", "Invalid MAX_LOG_SIZE value, using default.")
            return self.get_default_config()["daemon"]["MAX_LOG_SIZE"]

    def validate_log_level(self, value):
        """Validate the LOG_LEVEL string."""
        return value if value in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] else "INFO"

    def load_config(self):
        """Load configuration from default and user config file."""
        config = configparser.ConfigParser()
        defaults = self.get_default_config()

        # Load the default values into the config
        for section, values in defaults.items():
            if not config.has_section(section):
                config.add_section(section)
            for key, value in values.items():
                config.set(section, key, str(value))

        if os.path.exists(USER_CONFIG_FILE):
            config.read(USER_CONFIG_FILE)
            self.log_action("SYSTEM", f"Loaded config from {USER_CONFIG_FILE}")
        else:
            self.log_action("WARNING", "No user config found, using defaults.")

        # Validate and load each section based on defaults
        self.max_log_size = self.validate_max_log_size(config.get("daemon", "MAX_LOG_SIZE", fallback=defaults["daemon"]["MAX_LOG_SIZE"]))
        self.log_level = self.validate_log_level(config.get("daemon", "LOG_LEVEL", fallback=defaults["daemon"]["LOG_LEVEL"]))

        # Add logic for other sections, like mpv, image, etc.
        self.mpv_config = {
            "video_quality": config.get("mpv", "video_quality", fallback=defaults["mpv"]["video_quality"]),
            "audio_output": config.get("mpv", "audio_output", fallback=defaults["mpv"]["audio_output"]),
        }

        self.image_config = {
            "default_resolution": config.get("image", "default_resolution", fallback=defaults["image"]["default_resolution"]),
            "format": config.get("image", "format", fallback=defaults["image"]["format"]),
        }

        return config

    def dump_default_config(self):
        """Write default config to user directory."""
        ensure_config_dir()
        with open(USER_CONFIG_FILE, "w") as configfile:
            self.config.write(configfile)
        self.log_action("SYSTEM", f"Default config written to {USER_CONFIG_FILE}")

    def handle_command(self, command):
        """Process a received command."""
        if command in self.valid_commands:
            self.log_action(self.valid_commands[command], f"Executing command: {command}")
            if command == "config":
                self.dump_default_config()
            elif command == "stop":
                self.running = False
        else:
            self.log_action("ERROR", f"Unknown command: {command}")

    # Other methods remain the same...

