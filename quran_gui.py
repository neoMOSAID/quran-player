
#!/usr/bin/env python3
"""
Quran Player GUI - v1.1.0

Dark-mode PyQt5 controller for quran-daemon.

Features:
- Play/Pause, Prev, Next, Start/Stop daemon
- Load verse / repeat range
- Conky display toggle
- System tray with context menu
- Keyboard shortcuts: Space (play/pause), ← (prev), → (next), Esc (hide)
- Config editor (auto-generates config if missing)
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


class DaemonCommunicator:
    """Talks to quran-daemon over the UNIX socket."""

    def __init__(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.control_dir = os.path.join(self.script_dir, "control")
        self.socket_path = os.path.join(self.control_dir, "daemon.sock")

    def send_command(self, command, *args):
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(self.socket_path)
            client.sendall((" ".join([command] + list(args))).encode() + b"\n")
            response = client.recv(65536).decode().strip()
            client.close()
            return response
        except (FileNotFoundError, ConnectionRefusedError):
            return "Daemon is not running."
        except Exception as e:
            return f"ERROR: {str(e)}"

    def get_status(self):
        try:
            data = json.loads(self.send_command("status"))
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
                "conky_enabled": data.get("conky_enabled", False),
                "conky_running": data.get("conky_running", False),
                "daemon_running": data.get("daemon_running", False),
            }
        except (json.JSONDecodeError, TypeError):
            return None

    def is_running(self):
        try:
            if not os.path.exists(self.socket_path):
                return "Daemon is not running"
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(1)
            client.connect(self.socket_path)
            client.sendall(b"status\n")
            response = client.recv(1024).decode().strip()
            client.close()
            return "Daemon is running" if response else "Daemon not responding"
        except Exception:
            return "Daemon is not running"

    def start_daemon(self):
        try:
            daemon_script = os.path.join(self.script_dir, "daemon.py")
            subprocess.Popen([sys.executable, daemon_script, 'start'])
            time.sleep(1)
        except Exception as e:
            print(f"Failed to start daemon: {e}")


class QuranPlayer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.daemon = DaemonCommunicator()
        self.repeat_range = None
        self.initUI()
        self.createTrayIcon()
        self.initShortcuts()
        self.initTimers()

    def initUI(self):
        self.setWindowTitle("Quran Player Controller")
        self.setMinimumSize(500, 340)

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)

        self.verse_label = QtWidgets.QLabel("Loading status...")
        self.verse_label.setAlignment(QtCore.Qt.AlignCenter)
        self.verse_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        self.verse_label.setMaximumHeight(30)
        layout.addWidget(self.verse_label)

        button_layout = QtWidgets.QHBoxLayout()
        self.prev_button = QtWidgets.QPushButton("⏮")
        self.play_button = QtWidgets.QPushButton("⏯")
        self.next_button = QtWidgets.QPushButton("⏭")
        button_layout.addWidget(self.prev_button)
        button_layout.addWidget(self.play_button)
        button_layout.addWidget(self.next_button)
        layout.addLayout(button_layout)

        bottom_layout = QtWidgets.QGridLayout()
        self.load_verse_button = QtWidgets.QPushButton("Load")
        self.repeat_verse_button = QtWidgets.QPushButton("Repeat")
        self.conky_button = QtWidgets.QPushButton("Conky On")
        self.config_button = QtWidgets.QPushButton("Config")
        self.stop_daemon_button = QtWidgets.QPushButton("Start/Stop Daemon")
        self.minimize_button = QtWidgets.QPushButton("Minimize")
        self.about_button = QtWidgets.QPushButton("About")
        self.exit_button = QtWidgets.QPushButton("Exit")
        self.visit_website_button = QtWidgets.QPushButton("Website")

        bottom_layout.addWidget(self.load_verse_button, 0, 0)
        bottom_layout.addWidget(self.repeat_verse_button, 0, 1)
        bottom_layout.addWidget(self.conky_button, 0, 2)
        bottom_layout.addWidget(self.config_button, 0, 3)
        bottom_layout.addWidget(self.stop_daemon_button, 0, 4)
        bottom_layout.addWidget(self.minimize_button, 1, 0)
        bottom_layout.addWidget(self.about_button, 1, 1)
        bottom_layout.addWidget(self.exit_button, 1, 2)
        bottom_layout.addWidget(self.visit_website_button, 1, 3)
        layout.addLayout(bottom_layout)

        self.status_bar = QtWidgets.QStatusBar()
        self.status_bar.showMessage(self.daemon.is_running())
        self.setStatusBar(self.status_bar)

        self.play_button.clicked.connect(self.play)
        self.prev_button.clicked.connect(self.previous)
        self.next_button.clicked.connect(self.next)
        self.load_verse_button.clicked.connect(self.load_verse)
        self.repeat_verse_button.clicked.connect(self.repeat_verse)
        self.conky_button.clicked.connect(self.toggle_conky)
        self.config_button.clicked.connect(self.config)
        self.stop_daemon_button.clicked.connect(self.stop_daemon)
        self.minimize_button.clicked.connect(self.hide)
        self.exit_button.clicked.connect(self.close)
        self.about_button.clicked.connect(self.about)
        self.visit_website_button.clicked.connect(self.visit_website)

        self.setStyleSheet("""
            QMainWindow { background-color: #2e2e2e; }
            QPushButton {
                font-size: 13px; color: white; background-color: #4a4a4a;
                border: 1px solid #6a6a6a; border-radius: 5px; padding: 5px;
            }
            QPushButton:hover { background-color: #6a6a6a; }
            QPushButton:pressed { background-color: #3a3a3a; }
            QLabel { color: white; }
            QStatusBar { color: white; background-color: #1e1e1e; }
        """)

    def initShortcuts(self):
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Space), self, self.play)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Left), self, self.previous)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Right), self, self.next)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self, self.hide)

    def createTrayIcon(self):
        self.tray_icon = QtWidgets.QSystemTrayIcon(self)
        self.tray_icon.setIcon(
            QtGui.QIcon(os.path.join(self.daemon.script_dir, "icon.png"))
        )
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
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()

    def initTimers(self):
        self.status_timer = QtCore.QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(2000)
        self.status_bar_timer = QtCore.QTimer(self)
        self.status_bar_timer.timeout.connect(self.update_status_bar)
        self.status_bar_timer.start(7000)

    def update_status(self):
        status = self.daemon.get_status()
        if status:
            surah = status.get("surah", "Unknown")
            ayah = status.get("ayah", "Unknown")
            playback_status = status.get("status", "Unknown")
            self.verse_label.setText(f"Surah {surah}, Ayah {ayah} ({playback_status})")
            self.repeat_range = (
                status.get("surah"),
                status.get("repeat_start"),
                status.get("repeat_end"),
            ) if status.get("repeat") else None
            self.repeat_verse_button.setText("Cancel Repeat" if status.get("repeat") else "Repeat")
            self.conky_button.setText("Conky Off" if status.get("conky_enabled") else "Conky On")
        else:
            self.verse_label.setText("Status unavailable.")
            self.repeat_range = None

    def update_status_bar(self):
        msg = self.daemon.is_running()
        if msg.startswith("Daemon is running"):
            status = self.daemon.get_status()
            if status:
                msg += f" | {status.get('status', 'Unknown')}"
                if status.get("conky_enabled"):
                    msg += " | Conky:on" if status.get("conky_running") else " | Conky:off"
        self.status_bar.showMessage(msg)

    def play(self):
        status = self.daemon.get_status()
        if not status or not status.get("daemon_running", False):
            self.status_bar.showMessage("Starting daemon...")
            QtWidgets.QApplication.processEvents()
            self.daemon.start_daemon()
            start_time = time.time()
            while not self.daemon.is_running().startswith("Daemon is running"):
                if time.time() - start_time > 5:
                    self.status_bar.showMessage("Failed to start daemon")
                    return
                time.sleep(0.2)
            time.sleep(0.5)
            response = self.daemon.send_command("play")
        elif status.get("status") == "paused":
            response = self.daemon.send_command("play")
        elif status.get("status") == "playing":
            response = self.daemon.send_command("pause")
        else:
            response = self.daemon.send_command("play")
        self.status_bar.showMessage(response)
        new_status = self.daemon.get_status()
        if new_status and new_status.get("status") in ("playing", "playing|repeat"):
            self.play_button.setText("⏸")
        else:
            self.play_button.setText("⏯")

    def previous(self):
        self.status_bar.showMessage(self.daemon.send_command("prev"))

    def next(self):
        self.status_bar.showMessage(self.daemon.send_command("next"))

    def load_verse(self):
        verse, ok = QtWidgets.QInputDialog.getText(
            self, "Load Verse",
            "Enter:\n• Surah only (e.g., '5')\n• Specific verse (e.g., '5:3')",
            text="",
        )
        if ok and verse:
            self.status_bar.showMessage(self.daemon.send_command("load", verse))
        else:
            self.status_bar.showMessage("Load verse canceled.")

    def repeat_verse(self):
        status = self.daemon.get_status()
        if status and status.get("repeat"):
            self.status_bar.showMessage(self.daemon.send_command("repeat_off"))
            return
        verse, ok = QtWidgets.QInputDialog.getText(
            self, "Repeat Verses",
            "Enter repeat range:\n• Surah only: '5'\n• Range: '1:7'\n• Full: '2:1:20'",
            text="",
        )
        if ok and verse:
            self.status_bar.showMessage(self.daemon.send_command("repeat", verse))
        else:
            self.status_bar.showMessage("Repeat verses canceled.")

    def toggle_conky(self):
        status = self.daemon.get_status()
        if not status:
            self.status_bar.showMessage("Daemon not running")
            return
        if status.get("conky_enabled"):
            response = self.daemon.send_command("conky_off")
        else:
            response = self.daemon.send_command("conky_on")
        self.status_bar.showMessage(response)

    def config(self):
        if not os.path.exists(config.USER_CONFIG_FILE):
            self.status_bar.showMessage("Generating default config...")
            self.daemon.send_command("config")
            time.sleep(0.3)
        if not os.path.exists(config.USER_CONFIG_FILE):
            self.status_bar.showMessage("Could not create config file.")
            return
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Configuration")
        dialog.setModal(True)
        dialog.resize(600, 400)
        layout = QtWidgets.QVBoxLayout(dialog)
        with open(config.USER_CONFIG_FILE, "r", encoding="utf-8") as f:
            text_edit = QtWidgets.QTextEdit(dialog)
            text_edit.setPlainText(f.read())
        layout.addWidget(text_edit)
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=dialog,
        )
        layout.addWidget(button_box)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            with open(config.USER_CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(text_edit.toPlainText())
            self.status_bar.showMessage("Configuration updated.", 3000)
        else:
            self.status_bar.showMessage("Configuration changes canceled.", 3000)

    def stop_daemon(self):
        msg = self.daemon.is_running()
        if msg.startswith("Daemon is not"):
            self.status_bar.showMessage("Starting daemon...")
            QtWidgets.QApplication.processEvents()
            self.daemon.start_daemon()
            time.sleep(1)
            self.status_bar.showMessage("Daemon started")
        else:
            self.status_bar.showMessage("Stopping daemon...")
            QtWidgets.QApplication.processEvents()
            self.status_bar.showMessage(self.daemon.send_command("stop"))

    def about(self):
        dlg = QtWidgets.QMessageBox(self)
        dlg.setWindowTitle("About")
        dlg.setText("""
        <h3>Quran Player Daemon v1.4.0</h3>
        <p>Linux-native Quran audio playback with Conky desktop verse display.</p>
        <p>
        <a style="color: #1E90FF;" href="https://mosaid.xyz/quran-player">https://mosaid.xyz/quran-player</a><br><br>
        <a style="color: #1E90FF;" href="https://github.com/neoMOSAID/quran-player">https://github.com/neoMOSAID/quran-player</a>
        </p>
        <p>&copy; 2026 Quran Player Project - GPLv3 License</p>
        """)
        dlg.resize(600, 500)
        dlg.setTextFormat(QtCore.Qt.RichText)
        dlg.setIcon(QtWidgets.QMessageBox.Information)
        dlg.exec_()

    def visit_website(self):
        if not QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://mosaid.xyz/quran-player")):
            self.status_bar.showMessage("Failed to open website.", 3000)


def main():
    signal.signal(signal.SIGINT, lambda s, f: QtWidgets.QApplication.quit())
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    p = QtGui.QPalette()
    p.setColor(QtGui.QPalette.Window, QtGui.QColor(45, 45, 45))
    p.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    p.setColor(QtGui.QPalette.Base, QtGui.QColor(30, 30, 30))
    p.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(45, 45, 45))
    p.setColor(QtGui.QPalette.ToolTipBase, QtCore.Qt.white)
    p.setColor(QtGui.QPalette.ToolTipText, QtCore.Qt.white)
    p.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
    p.setColor(QtGui.QPalette.Button, QtGui.QColor(45, 45, 45))
    p.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.white)
    p.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)
    p.setColor(QtGui.QPalette.Highlight, QtGui.QColor(90, 90, 90))
    p.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.white)
    app.setPalette(p)
    w = QuranPlayer()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

    