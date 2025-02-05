# Quran Player 

![Project Logo](https://raw.githubusercontent.com/neoMOSAID/quran-player/main/icon.png)


A cross-platform Quran playback system with synchronized visual display

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-green)](https://python.org)

## Features

- Verse-by-verse audio playback with auto-advance
- Arabic text display with proper shaping and rendering
- Persistent playback state across sessions
- System tray GUI controller
- Cross-platform support (Linux/macOS/Windows)
- Configurable through user-friendly interface
- Multiple audio file support
- Interactive verse searching

## Installation

### Linux
```bash
git clone https://github.com/neoMOSAID/quran-player.git
cd quran-player
./install.sh
```

### Windows/macOS (not tested)
1. Install Python 3.8+
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run:
   ```bash
   python quran_gui.py
   ```

## Usage

### Daemon Control
```bash
quran-daemon start    # Start the background service
quran-daemon load 2:255  # Load Al-Baqarah 255
quran-daemon next     # Play next verse
quran-daemon pause    # Pause playback
```

### GUI Control
```bash
quran-gui   # Launch system tray controller
```

### Key Features
- Right-click tray icon for quick controls
- Auto-saves last played position
- Configurable display settings
- Support for multiple reciters

## Configuration

Edit `~/.config/quran-player/config.ini` to customize:
- Audio file locations
- Text display settings
- Font preferences
- Image rendering options

Example configuration:
```ini
[image]
ENABLE = yes
FONT_SIZE = 48
TEXT_COLOR = 255,255,255,255
```

**Important Note on Audio Files:** The Quran Player Daemon requires Quranic audio files named in the specific format `XXXYYY.mp3`, where `XXX` is the 3-digit surah number and `YYY` is the 3-digit ayah number (e.g., `002001.mp3` for Surah 2, Ayah 1). While basic sample files are included, **full functionality requires downloading complete verse-by-verse audio collections** from sources like [EveryAyah.com](https://everyayah.com/recitations_ayat.html), which offers recitations in this standardized format. After downloading, place the files in the `~/.config/quran-player/sample/` directory (or your configured `FILES_DIRECTORY`). Ensure all files follow this naming scheme for seamless playback across all 114 surahs.


---

### **System Requirements & Dependencies**

The Quran Player requires the following dependencies to function properly:

#### **Core Dependencies (All Platforms)**  
- **Python 3.8+**: The application is built using Python.  
- **Python Libraries**: Install via `pip install -r requirements.txt`:  
  - `pygame` (audio playback)  
  - `pystray` (system tray GUI)  
  - `pillow` (image rendering)  
  - `arabic-reshaper` and `python-bidi` (Arabic text shaping and rendering)  

#### **Platform-Specific Requirements**  
- **Linux/macOS**:  
  - `feh` (image viewer for displaying Arabic text)  
  - PulseAudio  (audio backend)  
  - Arabic font support (ensure system fonts are installed)  
- **Windows**:  
  - Manual font installation (copy `arabic-font.ttf` to `C:\Windows\Fonts`)  

#### **Audio Files**  
The Quran Player requires Quranic audio files named in the format `XXXYYY.mp3`, where:  
- `XXX` is the 3-digit surah number (e.g., `002` for Surah Al-Baqarah)  
- `YYY` is the 3-digit ayah number (e.g., `001` for the first ayah)  

**Example**: `002001.mp3` for Surah 2, Ayah 1.  

You can download these files from sources like [EveryAyah.com](https://everyayah.com/recitations_ayat.html). Place the files in the `~/.config/quran-player/sample/` directory (or the configured `FILES_DIRECTORY` in `config.ini`).  

---

### **Windows Compatibility Notes**  
While the Quran Player is designed to work on Windows, there are some platform-specific considerations:  
1. **Config Paths**: The default configuration directory (`~/.config/quran-player`) translates to `%LOCALAPPDATA%\quran-player` on Windows (e.g., `C:\Users\USERNAME\AppData\Local\quran-player`).  
2. **Image Display**: The Linux-specific `feh` image viewer is unavailable on Windows. The application will use the default image viewer, but functionality may be limited.  
3. **Arabic Input**: Ensure Arabic fonts are installed and configured correctly for proper text rendering.  



## Contributing

Contributions welcome! Please see:
- [Contributing Guidelines](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Project Wiki](https://github.com/neoMOSAID/quran-player/wiki)

## License

GNU General Public License v3.0 - See [LICENSE](LICENSE)

## Support

For help and support:
- [Documentation Wiki](https://github.com/neoMOSAID/quran-player/wiki)
- [Issues Tracker](https://github.com/neoMOSAID/quran-player/issues)
- Email: mail@mosaid.xyz
