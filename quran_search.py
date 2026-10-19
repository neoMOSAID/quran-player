
"""
Quran Search and Display Tool
"""

import sys
import os
import re
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

USER_CONFIG_DIR = os.path.expanduser("~/.config/quran-player")
SIMPLIFIED_OUT_FILE = os.path.join(USER_CONFIG_DIR, "search_result_simplified.txt")
UTHMANI_OUT_FILE = os.path.join(USER_CONFIG_DIR, "search_result_uthmani.txt")


chapters = []
uthmani = {}
simplified = {}
_data_loaded = False


def _data_paths():
    return (
        os.path.join(SCRIPT_DIR, "quran-text", "chapters.txt"),
        os.path.join(SCRIPT_DIR, "quran-text", "uthmani.txt"),
        os.path.join(SCRIPT_DIR, "quran-text", "simplified.txt"),
    )


def read_chapters(filename):
    if not os.path.exists(filename):
        print(f"Warning: Missing file {filename}", file=sys.stderr)
        return []
    with open(filename, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f]


def read_uthmani(filename):
    result = {}
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 3:
                continue
            surah, ayah = int(parts[0]), int(parts[1])
            result[(surah, ayah)] = ('|'.join(parts[2:]), line.strip())
    return result


def read_simplified(filename):
    result = {}
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 3:
                continue
            surah, ayah = int(parts[0]), int(parts[1])
            result[(surah, ayah)] = ('|'.join(parts[2:]), line.strip())
    return result


def ensure_data_loaded():
    global chapters, uthmani, simplified, _data_loaded
    if _data_loaded:
        return True
    cpath, upath, spath = _data_paths()
    try:
        chapters = read_chapters(cpath)
        uthmani = read_uthmani(upath)
        simplified = read_simplified(spath)
        _data_loaded = True
        return True
    except FileNotFoundError as e:
        print(f"Error: Required file missing: {e}", file=sys.stderr)
        return False


def get_verse_text(surah, ayah):
    if not _data_loaded and not ensure_data_loaded():
        return ""
    key = (surah, ayah)
    if key not in uthmani:
        return ""
    text, _ = uthmani[key]
    chapter_name = chapters[surah - 1] if 1 <= surah <= len(chapters) else 'Unknown'
    return f"{text} ({chapter_name} {ayah})"


def get_chapter_name(chapters_list, surah):
    return chapters_list[surah - 1] if surah <= len(chapters_list) else 'Surah'


def command_line_mode(surah, start_ayah, end_ayah, uthmani_dict, simplified_dict, chapters_list,
                      write_files=True):
    uthmani_output = []
    simplified_output = []

    for ayah_num in range(start_ayah, end_ayah + 1):
        key = (surah, ayah_num)
        if key not in uthmani_dict or key not in simplified_dict:
            print(f"Warning: Ayah {surah}:{ayah_num} not found.", file=sys.stderr)
            continue
        uthmani_text, _ = uthmani_dict[key]
        simplified_text, _ = simplified_dict[key]
        chapter_name = chapters_list[surah - 1] if surah <= len(chapters_list) else 'Unknown'
        uthmani_output.append(f"{uthmani_text} ({chapter_name} {ayah_num})")
        simplified_output.append(f"{simplified_text} ({chapter_name} {ayah_num})")

    if write_files:
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


def get_current_layout():
    if os.environ.get("WAYLAND_DISPLAY"):
        return None
    try:
        result = subprocess.run(['setxkbmap', '-query'], capture_output=True, text=True, check=True)
        for line in result.stdout.split('\n'):
            if line.startswith('layout:'):
                return line.split(':')[1].strip().split(',')[0]
        return None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def set_layout(layout):
    if os.environ.get("WAYLAND_DISPLAY"):
        return
    try:
        subprocess.run(['setxkbmap', layout], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


def get_rtl_search_input(title="بحث في القرآن", label="أدخل كلمة البحث:", default_text=""):
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


def remove_diacritics(text):
    return re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]").sub("", text)


def normalize_hamza(text):
    text = text.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا").replace("ء", "")
    text = text.replace("ئ", "ي").replace("ؤ", "و").replace("ى", "ي")
    return text


def normalize_text(text):
    return re.sub(r"\s+", " ", normalize_hamza(remove_diacritics(text))).strip()


def interactive_mode(uthmani_dict, simplified_dict, chapters_list):
    original_layout = get_current_layout()
    try:
        set_layout('ara')
        search_term = get_rtl_search_input()
    finally:
        if original_layout:
            set_layout(original_layout)

    if not search_term:
        return

    matches = []
    normalized_search_term = normalize_text(search_term)
    for key in simplified_dict:
        text, _ = simplified_dict[key]
        if normalized_search_term in normalize_text(text):
            matches.append(key)
    matches.sort(key=lambda x: (x[0], x[1]))

    if not matches:
        print("No results found.")
        return

    uthmani_results = []
    simplified_results = []

    for key in matches:
        surah, ayah = key
        if key not in uthmani_dict:
            continue
        uthmani_text, uthmani_full = uthmani_dict[key]
        simplified_text, _ = simplified_dict[key]
        chapter_name = chapters_list[surah - 1] if surah <= len(chapters_list) else 'Unknown'
        print(f"{uthmani_text} ({chapter_name} {ayah})")
        uthmani_results.append(uthmani_full)
        simplified_results.append(simplified_text)

    if uthmani_results:
        with open(UTHMANI_OUT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(uthmani_results))
    if simplified_results:
        with open(SIMPLIFIED_OUT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(simplified_results))


def main():
    if not ensure_data_loaded():
        sys.exit(1)

    if len(sys.argv) > 1:
        if len(sys.argv) == 2:
            try:
                surah = int(sys.argv[1])
            except ValueError:
                print("Usage: quran_search.py <surah> [start_ayah] [end_ayah]", file=sys.stderr)
                sys.exit(1)
            print(get_chapter_name(chapters, surah))
        else:
            try:
                surah = int(sys.argv[1])
                start_ayah = int(sys.argv[2])
                end_ayah = start_ayah
                if len(sys.argv) > 3:
                    end_ayah = int(sys.argv[3])
                print(command_line_mode(surah, start_ayah, end_ayah,
                                        uthmani, simplified, chapters))
            except Exception as e:
                print(f"Invalid arguments: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        interactive_mode(uthmani, simplified, chapters)


if __name__ == "__main__":
    main()
    