# quran_gui.py - Final Fixes
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

import arabic_reshaper
from bidi.algorithm import get_display

from quran_player import USER_CONFIG_FILE, about
import quran_search


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOCKET_FILE = os.path.join(SCRIPT_DIR, "control/daemon.sock")
DAEMON_SCRIPT = os.path.join(SCRIPT_DIR, "quran_player.py")
ICON_FILE = os.path.join(SCRIPT_DIR, "icon.png")

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
        self.daemon_stopped = False 
        self.tray_thread = None  # Add this line

        self.create_gui()
        self.start_status_poller()
        signal.signal(signal.SIGINT, self.handle_exit)

    def is_daemon_running(self):
        """Check if daemon is running"""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.connect(SOCKET_FILE)
                return True
        except (ConnectionRefusedError, FileNotFoundError):
            return False
    
    def start_daemon(self):
        """Start the daemon process if not running and not stopped by user"""
        if self.daemon_stopped:
            self.update_status_bar("daemon is stopped", error=True)
            return False  # Don't start if user stopped it
        
        if not self.is_daemon_running():
            self.update_status_bar("trying to start daemon", error=False)
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

    def toggle_daemon(self):
        """Toggle daemon state based on current status"""
        if self.daemon_stopped or not self.is_daemon_running():
            self.daemon_stopped = False
            if self.start_daemon():
                self.stop_button.config(text="Stop Daemon")
        else:
            self.stop_daemon()

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


