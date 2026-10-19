
"""Load a surah:ayah via the daemon. Opens an RTL input dialog."""

import subprocess
import os
import sys
from PyQt5 import QtWidgets, QtCore, QtGui


def get_rtl_search_input(title="Load Surah Ayah", label="Example: 2 255, or just 2", default_text=""):
    app = QtWidgets.QApplication.instance()
    created_app = False
    if app is None:
        app = QtWidgets.QApplication([])
        created_app = True

    input_dialog = QtWidgets.QInputDialog()
    input_dialog.setWindowTitle(title)
    input_dialog.setLabelText(label)
    input_dialog.setTextValue(default_text)
    input_dialog.setLayoutDirection(QtCore.Qt.RightToLeft)
    input_dialog.setFont(QtGui.QFont("Amiri", 14))
    input_dialog.setStyleSheet("""
    QDialog, QWidget { background-color: #2e2e2e; color: #ffffff; }
    QLineEdit { background-color: #3e3e3e; border: 1px solid #555555; color: #ffffff; }
    QLabel { color: #ffffff; }
    QPushButton { background-color: #3e3e3e; border: 1px solid #555555; color: #ffffff;
                  padding: 5px; min-width: 80px; min-height: 30px; }
    QPushButton:hover { background-color: #4e4e4e; }
    QPushButton:pressed { background-color: #1e1e1e; }
    """)
    input_dialog.resize(400, 150)

    button_box = input_dialog.findChild(QtWidgets.QDialogButtonBox)
    if button_box:
        button_box.setCenterButtons(True)

    if input_dialog.exec_() == QtWidgets.QDialog.Accepted:
        search_term = input_dialog.textValue().strip()
    else:
        search_term = None

    if created_app:
        app.quit()
    return search_term


def load():
    args = get_rtl_search_input()
    if not args:
        return

    parts = args.strip().split()
    if len(parts) == 1:
        parts.append("0")
    if len(parts) > 2 or not all(p.isdigit() for p in parts):
        print("Invalid input. Use 'surah' or 'surah ayah'.", file=sys.stderr)
        return
    verse = ":".join(parts)

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        daemon_path = os.path.join(current_dir, "daemon.py")
        if not os.path.exists(daemon_path):
            print(f"Error: daemon.py not found at {daemon_path}", file=sys.stderr)
            return

        result = subprocess.run(
            [sys.executable, daemon_path, "load", verse],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0 and result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("Error: daemon did not respond in time", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    load()

    