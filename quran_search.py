"""
Quran Search and Display Tool

This script provides both command-line and interactive modes to search and display Quranic verses.
It supports two text versions (Uthmani and Simplified) and handles Arabic text input with right-to-left layout.

Features:
- Dark theme for interactive mode
- RTL text input support
- Cross-version search capabilities
- Keyboard layout auto-switching for Arabic input

Usage:
    Command-line mode: python script.py <surah> <start_ayah> [end_ayah]
    Interactive mode: python script.py
"""

import sys
import os
import re
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui

def get_config_dir():
    if sys.platform.startswith("win"):
        # On Windows, use the APPDATA folder.
        base_dir = os.environ.get("APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming"))
        userconfdir = os.path.join(base_dir, "quran-player")
    elif sys.platform == "darwin":
        # On macOS, configuration files are often stored in Application Support.
        userconfdir = os.path.expanduser("~/Library/Application Support/quran-player")
    else:
        # On Linux and other Unix-like OSes, use the .config directory.
        userconfdir = os.path.expanduser("~/.config/quran-player")
    return userconfdir


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
USER_CONFIG_DIR = get_config_dir()
SIMPLIFIED_OUT_FILE = os.path.join(USER_CONFIG_DIR, "search_result_simplified.txt") 
UTHMANI_OUT_FILE = os.path.join(USER_CONFIG_DIR, "search_result_uthmani.txt") 
 
def read_chapters(filename):
    if not os.path.exists(filename):
        print(f"Warning: Missing file {filename}", file=sys.stderr)
        return []

    with open(filename, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f]


def read_uthmani(filename):
    uthmani = {}
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 3:
                continue
            surah = int(parts[0])
            ayah = int(parts[1])
            text = '|'.join(parts[2:])
            uthmani[(surah, ayah)] = (text, line.strip())
    return uthmani

def read_simplified(filename):
    simplified = {}
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 3:
                continue
            surah = int(parts[0])
            ayah = int(parts[1])
            text = '|'.join(parts[2:])
            simplified[(surah, ayah)] = (text, line.strip())
    return simplified

def get_current_layout():
    try:
        result = subprocess.run(['setxkbmap', '-query'], capture_output=True, text=True, check=True)
        lines = result.stdout.split('\n')
        for line in lines:
            if line.startswith('layout:'):
                return line.split(':')[1].strip().split(',')[0]
        return None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def set_layout(layout):
    if sys.platform.startswith("win"):
        return  # Windows doesn't use `setxkbmap`

    try:
        subprocess.run(['setxkbmap', layout], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


def get_chapter_name(chapters,surah):
    return chapters[surah - 1] if surah <= len(chapters) else 'Surah'

def command_line_mode(surah, start_ayah, end_ayah, uthmani, simplified, chapters):
    uthmani_output = []
    simplified_output = []
    
    for ayah_num in range(start_ayah, end_ayah + 1):
        key = (surah, ayah_num)
        if key not in uthmani or key not in simplified:
            print(f"Warning: Ayah {surah}:{ayah_num} not found.", file=sys.stderr)
            continue
            
        uthmani_text, _ = uthmani[key]
        simplified_text, _ = simplified[key]
        chapter_name = chapters[surah - 1] if surah <= len(chapters) else 'Unknown'
        
        # Collect for file output
        uthmani_output.append(f"{uthmani_text} ({chapter_name} {ayah_num})")
        simplified_output.append(f"{simplified_text} ({chapter_name} {ayah_num})")
    
    # Write to both files
    if uthmani_output:
        try:
            with open(UTHMANI_OUT_FILE, 'w', encoding='utf-8') as f:
                f.write('\n'.join(uthmani_output))
        except IOError as e:
            print(f"Error writing to {UTHMANI_OUT_FILE}: {e}", file=sys.stderr)

        
    if simplified_output:
        try:
            with open(SIMPLIFIED_OUT_FILE, 'w', encoding='utf-8') as f:
                f.write('\n'.join(simplified_output))
        except IOError as e:
            print(f"Error writing to {SIMPLIFIED_OUT_FILE}: {e}", file=sys.stderr)

    return '\n'.join(uthmani_output)



def get_rtl_search_input(title="بحث في القرآن", label="أدخل كلمة البحث:", default_text=""):
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



def remove_diacritics(text):
    arabic_diacritics = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")  # Arabic diacritic range
    return arabic_diacritics.sub("", text)

def normalize_hamza(text):
    """Normalize Hamza variations so إله and اله are equivalent."""
    text = text.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا").replace("ء", "")
    return text

def normalize_text(text):
    """Remove diacritics and normalize spaces."""
    text = remove_diacritics(text)  # Remove diacritics
    text = normalize_hamza(text) 
    text = re.sub(r"\s+", " ", text).strip()  # Normalize spaces
    return text

def interactive_mode(uthmani, simplified, chapters):
    """Handle interactive mode using yad dialogs"""
    original_layout = get_current_layout()
    
    try:
        set_layout('ara')
        search_term = get_rtl_search_input()
        
    finally:
        if original_layout:
            set_layout(original_layout)

    if not search_term:
        return

    # Perform search
    matches = []
    normalized_search_term = normalize_text(search_term)
    for key in simplified:
        simplified_text, _ = simplified[key]
        normalized_text = normalize_text(simplified_text)

        if normalized_search_term in normalized_text:
            matches.append(key)
    
    #matches.sort(key=lambda x: (x[0], x[1]))
    
    if not matches:
        print("No results found.")
        return
    
    uthmani_results = []
    simplified_results = []
    
    for key in matches:
        surah, ayah = key
        if key not in uthmani:
            continue
        uthmani_text, uthmani_full = uthmani[key]
        simplified_text, _ = simplified[key]
        chapter_name = chapters[surah - 1] if surah <= len(chapters) else 'Unknown'
        print(f"{uthmani_text} ({chapter_name} {ayah})")
        uthmani_results.append(uthmani_full)
        simplified_results.append(simplified_text)
    
    # Write to separate files
    if uthmani_results:
        with open(UTHMANI_OUT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(uthmani_results))
    
    if simplified_results:
        with open(SIMPLIFIED_OUT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(simplified_results))


try:
    chapters = read_chapters(os.path.join(SCRIPT_DIR, "quran-text/chapters.txt"))
    uthmani = read_uthmani(os.path.join(SCRIPT_DIR, "quran-text/uthmani.txt"))
    simplified = read_simplified(os.path.join(SCRIPT_DIR, "quran-text/simplified.txt"))
except FileNotFoundError as e:
    print(f"Error: Required file missing: {e}", file=sys.stderr)
    sys.exit(1)


def main():
    if len(sys.argv) > 1:
        if len(sys.argv) == 2:
            surah = int(sys.argv[1])
            print(get_chapter_name(chapters,surah))
        else:
            if len(sys.argv) < 3:
                print("Usage: script.py surah_number ayah_number [end_ayah]")
                sys.exit(1)
            try:
                surah = int(sys.argv[1])
                start_ayah = int(sys.argv[2])
                end_ayah = start_ayah
                if len(sys.argv) > 3:
                    end_ayah = int(sys.argv[3])
                quran_text = command_line_mode(surah, start_ayah, end_ayah, uthmani, simplified, chapters)
                print(quran_text)
            except Exception as e:
                print(f"Invalid arguments. Please provide numbers for surah and ayah   {str(e)}.")
                sys.exit(1)
    else:
        interactive_mode(uthmani, simplified, chapters)

if __name__ == "__main__":
    main()
