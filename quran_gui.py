#!/usr/bin/env python3
"""
Quran Player GUI using PyQt5 - v1.0.1

Features:
- Dark mode styling with Fusion palette.
- Playback controls: Play/Pause, Previous, Next, Stop Daemon.
- Volume slider, verse navigation (Jump to surah:ayah), and repeat controls.
- Log display (combining daemon log and local errors) updated periodically.
- Native system tray icon with context menu (Show, Play/Pause, Prev, Next, About, Exit).
- Keyboard shortcuts: Space (Play/Pause), Left (Previous), Right (Next), Esc (Hide Window).
- "About" dialog that retrieves information from the daemon.
- Graceful exit on Ctrl+C.
- **New:** “Load Verse” now shows an input dialog (format: surah:ayah) and sends a `load` command.
- **New:** The verse label is updated dynamically using the `status` command.
"""

import sys
import os
import socket
import subprocess
import time
import signal
import json


from PyQt5 import QtCore, QtGui, QtWidgets
from config_manager import config 

#############################
# DaemonCommunicator Class
#############################
class DaemonCommunicator:
    """Handles communication with the Quran Player Daemon."""
    def __init__(self):
        self.is_windows = (sys.platform == 'win32')
        self.setup_paths()

    def setup_paths(self):
        """Configure socket paths based on platform."""
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.control_dir = os.path.join(self.script_dir, "control")
        if sys.platform == 'win32':
            self.socket_path = r'\\.\pipe\quran-daemon'
            self.host = 'localhost'
            self.port = 58901
        else:
            self.socket_path = os.path.join(self.control_dir, "daemon.sock")


    def send_command(self, command, *args):
        """Send a command to the daemon and return its response."""
        try:
            if self.is_windows:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.connect((self.host, self.port))
            else:
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.connect(self.socket_path)
            full_cmd = " ".join([command] + list(args))
            client.sendall(full_cmd.encode() + b"\n")
            # Increase buffer size for multi-line responses (e.g., about command)
            response = client.recv(4096).decode().strip()
            client.close()
            return response
        except (FileNotFoundError, ConnectionRefusedError) as e:
            # This catches errors when the socket file doesn't exist or connection fails.
            return "Daemon is not running."
        except Exception as e:
            return f"ERROR: {str(e)}"


    def get_status(self):
        """Retrieve current playback status from the daemon."""
        response = self.send_command("status")
        try:
            data = json.loads(response)
            playing = data.get("playing", False)
            paused = data.get("paused", False)
            repeat = data.get("repeat", False)

            if paused:
                status = "paused"
            elif playing and repeat:
                status = "playing|repeat"
            elif playing:
                status = "playing"
            else:
                status = "stopped"

            return {
                "surah": data.get("surah"),
                "ayah": data.get("ayah"),
                "status": status,
                "repeat": repeat,
                "repeat_start": data.get("repeat_start"),
                "repeat_end": data.get("repeat_end"),
                "daemon_running": data.get("daemon_running", False)
            }
        except json.JSONDecodeError:
            return None


    
    def is_running(self):
        try:
            if self.is_windows:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.settimeout(1)
                client.connect((self.host, self.port))
                client.sendall(b"status\n")
                response = client.recv(1024).decode().strip()
                client.close()
                return "Daemon is running" if response else "Daemon is not running"
            else:
                # More reliable check for Linux
                if os.path.exists(self.socket_path):
                    try:
                        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        client.settimeout(1)
                        client.connect(self.socket_path)
                        client.sendall(b"status\n")
                        response = client.recv(1024).decode().strip()
                        client.close()
                        return "Daemon is running" if response else "Daemon not responding"
                    except:
                        return "Daemon not responding"
                return "Daemon is not running"
        except:
            return "Daemon is not running"
            
        
    def get_logs(self, max_lines="1"):
        """Retrieve current playback status from the daemon."""
        response = self.send_command("log",max_lines)
        return response
    
    def start_daemon(self):
        """Attempt to start the daemon process."""
        try:
            daemon_script = os.path.join(self.script_dir, "daemon.py")
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW
            else:
                creation_flags = 0  # No special flag for Linux/macOS

            subprocess.Popen([sys.executable, daemon_script, 'start'], creationflags=creation_flags)

            # Give the daemon some time to start up.
            time.sleep(1)
        except Exception as e:
            print(f"Failed to start daemon: {e}")


#############################
# MainWindow Class
#############################
class QuranPlayer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.daemon = DaemonCommunicator()
        self.initUI()
        self.createTrayIcon()   
        self.initTimers()
        self.repeat_mode = False


    def initUI(self):
        self.setWindowTitle("Quran Player Controller")
        self.setFixedSize(400, 300)

        # Central widget
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        layout = QtWidgets.QVBoxLayout(central_widget)

        # Verse label (will be updated dynamically)
        self.verse_label = QtWidgets.QLabel("Loading status...")
        self.verse_label.setAlignment(QtCore.Qt.AlignCenter)
        self.verse_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        self.verse_label.setMaximumHeight(30)
        layout.addWidget(self.verse_label)

        # Buttons layout
        button_layout = QtWidgets.QHBoxLayout()
        
        self.prev_button = QtWidgets.QPushButton("⏮")
        self.play_button = QtWidgets.QPushButton("⏯")
        self.next_button = QtWidgets.QPushButton("⏭")

        button_layout.addWidget(self.prev_button)
        button_layout.addWidget(self.play_button)
        button_layout.addWidget(self.next_button)

        layout.addLayout(button_layout)

        # Bottom button row
        bottom_layout = QtWidgets.QGridLayout()

        self.load_verse_button = QtWidgets.QPushButton("Load")
        self.repeat_verse_button = QtWidgets.QPushButton("Repeat")
        self.stop_daemon_button = QtWidgets.QPushButton("Start/Stop Daemon")
        self.visit_website_button = QtWidgets.QPushButton("Visit Our Website")
        self.minimize_button = QtWidgets.QPushButton("Minimize")
        self.exit_button = QtWidgets.QPushButton("Exit")
        self.config_button = QtWidgets.QPushButton("Config")
        self.about_button = QtWidgets.QPushButton("About")

        bottom_layout.addWidget(self.load_verse_button, 0, 0)
        bottom_layout.addWidget(self.repeat_verse_button, 0, 1)
        bottom_layout.addWidget(self.config_button, 0, 2)
        bottom_layout.addWidget(self.stop_daemon_button, 0, 3)
        bottom_layout.addWidget(self.minimize_button, 1, 0)
        bottom_layout.addWidget(self.about_button, 1, 1)
        bottom_layout.addWidget(self.exit_button, 1, 2)
        bottom_layout.addWidget(self.visit_website_button, 1, 3)

        layout.addLayout(bottom_layout)

        # Status bar
        self.status_bar = QtWidgets.QStatusBar()
        self.status_bar.showMessage(self.daemon.is_running())
        self.setStatusBar(self.status_bar)

        # Signals
        self.play_button.clicked.connect(self.play)
        self.prev_button.clicked.connect(self.previous)
        self.next_button.clicked.connect(self.next)
        self.load_verse_button.clicked.connect(self.load_verse)
        self.repeat_verse_button.clicked.connect(self.repeat_verse)
        self.config_button.clicked.connect(self.config)
        self.stop_daemon_button.clicked.connect(self.stop_daemon)
        self.minimize_button.clicked.connect(self.hide)
        self.exit_button.clicked.connect(self.close)
        self.about_button.clicked.connect(self.about)
        self.visit_website_button.clicked.connect(self.visit_website)

        # Styling (Dark Mode)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2e2e2e;
            }
            QPushButton {
                font-size: 14px;
                color: white;
                background-color: #4a4a4a;
                border: 1px solid #6a6a6a;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #6a6a6a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
            QLabel {
                color: white;
            }
            QStatusBar {
                color: white;
                background-color: #1e1e1e;
            }
        """)

    def createTrayIcon(self):
        self.tray_icon = QtWidgets.QSystemTrayIcon(self)
        # Provide a valid icon file path or use a default icon
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.tray_icon.setIcon(QtGui.QIcon(os.path.join(self.script_dir, "icon.png")))
        
        tray_menu = QtWidgets.QMenu()

        restore_action = QtWidgets.QAction("Restore", self)
        restore_action.triggered.connect(self.show)
        tray_menu.addAction(restore_action)

        exit_action = QtWidgets.QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.onTrayIconActivated)        
        if QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()
        else:
            self.tray_icon.hide()


    def onTrayIconActivated(self, reason):
        # QSystemTrayIcon.Trigger is typically a single left click.
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            # Toggle window visibility:
            if self.isVisible():
                self.hide()  # Hide/minimize if currently visible.
            else:
                self.showNormal()  # Restore if hidden.

    def initTimers(self):
        """Initialize timers for periodic tasks."""
        self.status_timer = QtCore.QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(2000)  # update every 2 seconds

        self.status_bar_timer = QtCore.QTimer(self)
        self.status_bar_timer.timeout.connect(self.update_status_bar)
        self.status_bar_timer.start(7000)

    def update_status(self):
        """Poll the daemon for current status and update the verse label."""
        status = self.daemon.get_status()
        if status:
            surah = status.get("surah", "Unknown")
            ayah = status.get("ayah", "Unknown")
            playback_status = status.get("status", "Unknown")
            self.verse_label.setText(f"Surah {surah}, Ayah {ayah} ({playback_status})")
            # Update button text based on repeat state
            self.repeat_verse_button.setText("Cancel Repeat" if self.repeat_mode else "Repeat")
    
        else:
            self.verse_label.setText("Status unavailable.")

    def update_status_bar(self):
        """Update the status bar with the most recent log message, if available."""
        status_message = self.daemon.is_running()
        
        # Add playback status if daemon is running
        if status_message.startswith("Daemon is running"):
            status = self.daemon.get_status()
            if status:
                playback_status = status.get("status", "Unknown")
                status_message += f" | {playback_status}"
        
        self.status_bar.showMessage(status_message)

    def play(self):
        """Send appropriate play command based on current state"""
        # Immediately update status message
        status = self.daemon.get_status()
        if not status or not status.get("daemon_running", False):
            # Start daemon if not running
            self.status_bar.showMessage("Starting daemon...")
            QtWidgets.QApplication.processEvents()  # Force UI update
        
            self.daemon.start_daemon()
            
            # Wait for daemon to start with timeout
            start_time = time.time()
            while not self.daemon.is_running().startswith("Daemon is running"):
                if time.time() - start_time > 5:  # 5 second timeout
                    self.status_bar.showMessage("Failed to start daemon")
                    return
                time.sleep(0.2)  # Short delay between checks
                
            # Update status bar with running message
            self.status_bar.showMessage("Daemon started, playing...")
            QtWidgets.QApplication.processEvents()  # Force UI update
            time.sleep(0.5)  # Give daemon time to initialize
            
            # Send play command
            response = self.daemon.send_command("play")
        elif status.get("status") == "paused":
            # If paused, send play to resume
            response = self.daemon.send_command("play")
        elif status.get("status") == "playing":
            # If playing, send pause
            response = self.daemon.send_command("pause")
        else:
            # Otherwise start playback
            response = self.daemon.send_command("play")
        
        self.status_bar.showMessage(response)
        
        # Update button text based on new state
        new_status = self.daemon.get_status()
        if new_status and new_status.get("status") == "playing":
            self.play_button.setText("⏸")
        else:
            self.play_button.setText("⏯")

    def previous(self):
        response = self.daemon.send_command("prev")
        self.status_bar.showMessage(response)

    def next(self):
        response = self.daemon.send_command("next")
        self.status_bar.showMessage(response)

    def load_verse(self):
        """
        Show an input dialog for the user to enter:
        - Surah number only (to load entire surah)
        - Surah:ayah (to load specific verse)
        """
        verse, ok = QtWidgets.QInputDialog.getText(
            self, 
            "Load Verse", 
            "Enter:\n"
            "• Surah only (e.g., '5')\n"
            "• Specific verse (e.g., '5:3')", 
            text=""
        )
        if ok and verse:
            response = self.daemon.send_command("load", verse)
            self.status_bar.showMessage(response)
        else:
            self.status_bar.showMessage("Load verse canceled.")

    def repeat_verse(self):
        """Toggle repeat mode or set repeat range"""
        if self.repeat_mode:
            # If already in repeat mode, turn it off
            response = self.daemon.send_command("repeat_off")
            self.status_bar.showMessage(response)
            self.repeat_mode = False
        else:
            verse, ok = QtWidgets.QInputDialog.getText(
                self, 
                "Repeat Verses", 
                "Enter repeat range:\n"
                "• Surah only: '5'\n"
                "• Current surah range: '1:7'\n"
                "• Specific surah range: '2:1:20'", 
                text=""
            )
            if ok and verse:
                response = self.daemon.send_command("repeat", verse)
                self.status_bar.showMessage(response)
                self.repeat_mode = True
            else:
                self.status_bar.showMessage("Repeat verses canceled.")

        self.repeat_verse_button.setText("Cancel Repeat" if self.repeat_mode else "Repeat")

    def config(self):
        # Create the configuration dialog.
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Configuration")
        dialog.setModal(True)
        
        dialog.resize(600, 400)
        # Set up the layout for the dialog.
        layout = QtWidgets.QVBoxLayout(dialog)

        lines = []
        with open(config.USER_CONFIG_FILE, "r", encoding="utf-8") as file:
            for line in file:
                lines.append(line)

        combined_text = "".join(lines)

        # Create a QTextEdit pre-populated with the current configuration.
        text_edit = QtWidgets.QTextEdit(dialog)
        text_edit.setPlainText(combined_text)
        layout.addWidget(text_edit)
        
        # Create a standard dialog button box with OK and Cancel.
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=dialog
        )
        layout.addWidget(button_box)
        
        # Connect signals: OK will accept the dialog; Cancel will reject it.
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        
        # Execute the dialog modally.
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # On OK, update the configuration.
            new_config = text_edit.toPlainText()
            with open(config.USER_CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(new_config)
                self.status_bar.showMessage("Configuration updated.", 3000)
        else:
            self.status_bar.showMessage("Configuration changes canceled.", 3000)


    def stop_daemon(self):
        msg = self.daemon.is_running()
        if msg.startswith("Daemon is not"):
            self.status_bar.showMessage("Starting daemon...")
            QtWidgets.QApplication.processEvents()  # Force UI update
            self.daemon.start_daemon()
            time.sleep(1)  # Give daemon time to start
            self.status_bar.showMessage("Daemon started")
        else:
            self.status_bar.showMessage("Stopping daemon...")
            QtWidgets.QApplication.processEvents()  # Force UI update
            response = self.daemon.send_command("stop")
            self.status_bar.showMessage(response)
            

    def about(self):
        about_dialog = QtWidgets.QMessageBox(self)
        about_dialog.setWindowTitle("About")
        about_text = """
        <h3>Quran Player Daemon v1.3.0</h3>
        <p>A robust daemon for Quran audio playback.</p>
        <p>
        <a style="color: #1E90FF;" href="https://mosaid.xyz/quran-player">https://mosaid.xyz/quran-player</a><br><br>
        <a style="color: #1E90FF;" href="https://github.com/neoMOSAID/quran-player">https://github.com/neoMOSAID/quran-player</a>
        </p>
        <p>&copy; 2025 Quran Player Project - GPLv3 License</p>
        """
        about_dialog.setText(about_text)
        about_dialog.resize(600, 500)
        about_dialog.setTextFormat(QtCore.Qt.RichText)  # Enable HTML formatting.
        about_dialog.setIcon(QtWidgets.QMessageBox.Information)
        about_dialog.exec_()


    def visit_website(self):
        website_url = "https://mosaid.xyz/quran-player"  
        url = QtCore.QUrl(website_url)
        if not QtGui.QDesktopServices.openUrl(url):
            self.status_bar.showMessage("Failed to open website.", 3000)

#############################
# Main Entry Point
#############################
def main():
    # Graceful exit on Ctrl+C
    signal.signal(signal.SIGINT, lambda s, f: QtWidgets.QApplication.quit())
    app = QtWidgets.QApplication(sys.argv)
    # Use Fusion style and set a dark palette for consistency
    app.setStyle("Fusion")
    dark_palette = QtGui.QPalette()
    dark_palette.setColor(QtGui.QPalette.Window, QtGui.QColor(45, 45, 45))
    dark_palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Base, QtGui.QColor(30, 30, 30))
    dark_palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(45, 45, 45))
    dark_palette.setColor(QtGui.QPalette.ToolTipBase, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.ToolTipText, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Button, QtGui.QColor(45, 45, 45))
    dark_palette.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)
    dark_palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(90, 90, 90))
    dark_palette.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.white)
    app.setPalette(dark_palette)

    main_window = QuranPlayer()
    main_window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
