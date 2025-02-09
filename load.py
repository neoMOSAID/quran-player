import subprocess
import os
import sys

from PyQt5 import QtWidgets, QtCore, QtGui





def get_rtl_search_input(title="Load Surah Ayah", label="Example, 2 255, or just 2", default_text=""):
    """
    Create a dark-themed PyQt5 input dialog with RTL support for entering a search term.
    The buttons are made a bit larger and centered if possible.
    
    Args:
        title (str): The window title of the dialog.
        label (str): The prompt label text.
        default_text (str): Default text in the input field.
    
    Returns:
        str or None: The text entered by the user, or None if canceled.
    """
    # Check if there is an existing QApplication instance; if not, create one.
    app = QtWidgets.QApplication.instance()
    created_app = False
    if app is None:
        app = QtWidgets.QApplication([])
        created_app = True

    # Create the input dialog.
    input_dialog = QtWidgets.QInputDialog()
    input_dialog.setWindowTitle(title)
    input_dialog.setLabelText(label)
    input_dialog.setTextValue(default_text)
    
    # Enforce Right-To-Left layout.
    input_dialog.setLayoutDirection(QtCore.Qt.RightToLeft)
    
    # Set a custom font (for example, Amiri at size 14).
    font = QtGui.QFont("Amiri", 14)
    input_dialog.setFont(font)
    
    # Apply a dark theme style sheet with bigger buttons.
    dark_style = """
    QDialog, QWidget {
        background-color: #2e2e2e;
        color: #ffffff;
    }
    QLineEdit {
        background-color: #3e3e3e;
        border: 1px solid #555555;
        color: #ffffff;
    }
    QLabel {
        color: #ffffff;
    }
    QPushButton {
        background-color: #3e3e3e;
        border: 1px solid #555555;
        color: #ffffff;
        padding: 5px;
        min-width: 80px;
        min-height: 30px;
    }
    QPushButton:hover {
        background-color: #4e4e4e;
    }
    QPushButton:pressed {
        background-color: #1e1e1e;
    }
    """
    input_dialog.setStyleSheet(dark_style)
    
    # Optionally, set a fixed size for the dialog.
    input_dialog.resize(400, 150)
    
    # Attempt to center the dialog's buttons if available.
    button_box = input_dialog.findChild(QtWidgets.QDialogButtonBox)
    if button_box:
        button_box.setCenterButtons(True)
    
    # Execute the dialog modally.
    if input_dialog.exec_() == QtWidgets.QDialog.Accepted:
        search_term = input_dialog.textValue().strip()
    else:
        search_term = None

    # If we created the QApplication, quit it.
    if created_app:
        app.quit()
    
    return search_term





def load():
    """Load surah:ayah using the daemon"""

    # Create dialog
    try:
        args = get_rtl_search_input()
        parts = args.split()  # Split the input on whitespace
        
        # If only a single number is provided, append "0"
        if len(parts) == 1:
            parts.append("0")
            
        args = ":".join(parts)
    except Exception as e:
        return
    
    if not args:
        return

    try:
        # Get the directory of the current file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Build the full path to quran_player.py in the same directory
        daemon_path = os.path.join(current_dir, "quran_player.py")
        
        # Use the current environment's Python binary (e.g. env/bin/python)
        python_binary = sys.executable
        
        # Build the command; equivalent to:
        # env/bin/python quran_player.py load 2:255
        daemon_cmd = [python_binary, daemon_path, 'load', args]
        
        result = subprocess.run(
            daemon_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding='utf-8'
        )
        
        # Optionally process output from quran_player.py
        print(result.stdout)
    except Exception as e:
        return

if __name__ == "__main__":
    load()
