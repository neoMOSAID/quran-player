
# quran_gui.py - Enhanced Python GUI Controller
import os
import socket
import sys
import threading
import time
import subprocess
import argparse
import tkinter as tk
from tkinter import messagebox, simpledialog
from PIL import Image, ImageTk
import pystray

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOCKET_FILE = os.path.join(SCRIPT_DIR, "control/daemon.sock")
DAEMON_SCRIPT = os.path.join(SCRIPT_DIR, "quran_player.py")

class QuranController:
    def __init__(self):
        self.current_state = {"surah": 1, "ayah": 1, "paused": False}
        self.tray_icon = None
        self.root = None
        self.daemon_process = None
        self.create_gui()
        self.start_status_poller()

    def is_daemon_running(self):
        """Check if daemon is running"""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.connect(SOCKET_FILE)
                return True
        except (ConnectionRefusedError, FileNotFoundError):
            return False

    def start_daemon(self):
        """Start the daemon process if not running"""
        if not self.is_daemon_running():
            try:
                self.daemon_process = subprocess.Popen(
                    [sys.executable, DAEMON_SCRIPT, "start"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(1)  # Give daemon time to start
                return True
            except Exception as e:
                messagebox.showerror("Error", f"Failed to start daemon: {str(e)}")
                return False
        return True

    def send_command(self, command):
        """Send command to daemon with auto-start capability"""
        try:
            if not self.start_daemon():
                return None

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(2)
                sock.connect(SOCKET_FILE)
                sock.sendall(command.encode() + b"\n")
                return sock.recv(1024).decode().strip()
        except (ConnectionRefusedError, FileNotFoundError):
            messagebox.showerror("Error", "Daemon not responding after startup!")
            return None
        except Exception as e:
            messagebox.showerror("Error", f"Communication error: {str(e)}")
            return None

    def update_status(self):
        response = self.send_command("status")
        if response and response.startswith("STATUS"):
            parts = response.split("|")
            if len(parts) == 4:
                self.current_state = {
                    "surah": int(parts[1]),
                    "ayah": int(parts[2]),
                    "paused": parts[3] == "PAUSED"
                }
                status_text = f"Surah {self.current_state['surah']}:{self.current_state['ayah']}\n"
                status_text += "⏸ Paused" if self.current_state['paused'] else "▶ Playing"
                self.status_label.config(text=status_text)

    def create_gui(self):
        # System Tray Icon
        menu = pystray.Menu(
            pystray.MenuItem("Play/Pause", self.toggle_playback),
            pystray.MenuItem("Next Verse", self.next_verse),
            pystray.MenuItem("Previous Verse", self.prev_verse),
            pystray.MenuItem("Load Verse", self.load_verse),
            pystray.MenuItem("Exit", self.exit_app)
        )
        
        image = Image.open("icon.png")  # Use your own 64x64 icon
        self.tray_icon = pystray.Icon("quran_player", image, "Quran Player", menu)

        # Main Window
        self.root = tk.Tk()
        self.root.title("Quran Player Controller")
        self.root.geometry("320x180")
        
        self.status_label = tk.Label(self.root, text="Loading status...")
        self.status_label.pack(pady=10)
        
        control_frame = tk.Frame(self.root)
        control_frame.pack(pady=10)
        
        tk.Button(control_frame, text="⏯", command=self.toggle_playback).grid(row=0, column=1, padx=5)
        tk.Button(control_frame, text="⏮", command=self.prev_verse).grid(row=0, column=0, padx=5)
        tk.Button(control_frame, text="⏭", command=self.next_verse).grid(row=0, column=2, padx=5)
        
        tk.Button(self.root, text="Load Verse", command=self.load_verse).pack(pady=5)
        tk.Button(self.root, text="Exit", command=self.exit_app).pack(pady=5)

        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

    def start_status_poller(self):
        def poller():
            while True:
                self.update_status()
                time.sleep(1)
                
        threading.Thread(target=poller, daemon=True).start()

    def exit_app(self):
        self.tray_icon.stop()
        self.root.destroy()
        sys.exit(0)

    def toggle_playback(self):
        self.send_command("pause" if self.current_state['paused'] else "play")

    def next_verse(self):
        self.send_command("next")

    def prev_verse(self):
        self.send_command("prev")

    def load_verse(self):
        verse = simpledialog.askstring("Load Verse", "Enter Surah:Ayah (e.g. 2:255):")
        if verse:
            self.send_command(f"load {verse}")

    def minimize_to_tray(self):
        self.root.withdraw()

    def run(self):
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        self.root.mainloop()

    # Rest of the class remains the same as previous version with:
    # create_gui(), start_status_poller(), update_status(), 
    # control methods, and GUI components...

def command_line_interface():
    """Handle command-line arguments"""
    parser = argparse.ArgumentParser(description='Quran Player Control')
    parser.add_argument('command', nargs='?', help='Command to send to daemon')
    parser.add_argument('args', nargs='*', help='Command arguments')
    
    args = parser.parse_args()
    
    if args.command:
        controller = QuranController()
        response = controller.send_command(f"{args.command} {' '.join(args.args)}")
        print(response or "No response from daemon")
    else:
        # Start GUI if no command specified
        controller = QuranController()
        controller.run()

if __name__ == "__main__":
    command_line_interface()