import sys
import os
import subprocess
import tkinter as tk
from tkinter import simpledialog

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
USER_CONFIG_DIR = os.path.expanduser("~/.config/quran-player")
SIMPLIFIED_OUT_FILE = os.path.join(USER_CONFIG_DIR, "search_result_simplified.txt") 
UTHMANI_OUT_FILE = os.path.join(USER_CONFIG_DIR, "search_result_uthmani.txt") 


def read_chapters(filename):
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
            
        uthmani_text, uthmani_full = uthmani[key]
        simplified_text, _ = simplified[key]
        chapter_name = chapters[surah - 1] if surah <= len(chapters) else 'Unknown'
        
        # Collect for file output
        uthmani_output.append(f"{uthmani_text} ({chapter_name} {ayah_num})")
        simplified_output.append(f"{simplified_text} ({chapter_name} {ayah_num})")
    
    # Write to both files
    if uthmani_output:
        with open(UTHMANI_OUT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(uthmani_output))
    
    if simplified_output:
        with open(SIMPLIFIED_OUT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(simplified_output))

    return f"{uthmani_text} ({chapter_name} {ayah_num})"

def interactive_mode(uthmani, simplified, chapters):
    original_layout = get_current_layout()
    
    # Create GUI dialog
    root = tk.Tk()
    root.withdraw()
    
    try:
        set_layout('ara')
        search_term = simpledialog.askstring("Quran Search", "Enter Arabic search term:")
    finally:
        if original_layout:
            set_layout(original_layout)
        root.destroy()

    if not search_term:
        print("No search term entered.")
        return

    matches = []
    for key in simplified:
        parts = simplified[key].split('|')
        if len(parts) < 3:
            continue
        text = '|'.join(parts[2:])
        if search_term in text:
            matches.append(key)
    
    matches.sort(key=lambda x: (x[0], x[1]))
    
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
    print(f"Error: Missing file {e.filename}", file=sys.stderr)
    sys.exit(1)


def main():
    if len(sys.argv) > 1:
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