

# Quran Player

![Project Logo](https://raw.githubusercontent.com/neoMOSAID/quran-player/main/icon.png)


A cross-platform Quran playback system with synchronized visual display

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-green)](https://python.org)
[![Website](https://img.shields.io/badge/Website-mosaid.xyz-blue)]( https://mosaid.xyz/quran-player)


**Version:** v1.3.0  
**License:** GPLv3  
**Website:** [https://mosaid.xyz/quran-player](https://mosaid.xyz/quran-player)  
**GitHub:** [https://github.com/neoMOSAID/quran-player](https://github.com/neoMOSAID/quran-player)

---

## Overview

Quran Player is a cross-platform application for Quranic verse playback with synchronized visual display and Arabic text rendering. It comprises several components:

- **quran_player.py**  
  The daemon that handles audio playback, state management, and command processing (play, pause, next, previous, load, repeat, etc.).

- **quran_gui.py**  
  A PyQt5-based graphical user interface with dark-mode styling, system tray support, and keyboard shortcuts for controlling playback.

- **quran_search.py**  
  A versatile Quran search tool supporting both command-line and interactive modes (with RTL input).

- **arabic_topng.py**  
  A utility that renders Arabic text to PNG images using customizable configuration parameters.

- **Installation Scripts**  
  - **Windows:** A Python setup script (`setup.py` or similar) that creates a virtual environment, copies application files, installs dependencies, creates CLI wrappers, and sets up a desktop shortcut.  
  - **Linux:** A Bash script (`install-quran-player.sh`) that installs system dependencies, creates a virtual environment, copies files, generates CLI wrappers in `/usr/local/bin`, creates a desktop entry, and installs the man page.

- **Manual**  
  A comprehensive manual is provided both as a man page (for Linux) and as `manual.txt` (for Windows users).

---

## Features

- **Cross-Platform Support:**  
  Designed for Windows, Linux, and (with minor adjustments) macOS.

- **Audio Playback:**  
  Verse-by-verse playback with auto-advance, repeat functionality, and persistent playback state.

- **Graphical User Interface:**  
  A modern, dark-themed UI with native system tray integration, keyboard shortcuts, and a responsive design.

- **Interactive Search:**  
  Command-line and interactive modes (with RTL support) for searching Quranic verses.

- **Image Rendering:**  
  Render Quranic verses to images with customizable fonts, sizes, colors, and wrapping options.

- **Configurable:**  
  Fully customizable via an INI file (with separate sections for daemon and image settings) and overridable via environment variables.

- **Easy Installation:**  
  Separate, tailored installation scripts for Windows and Linux.

---

## Installation

### Windows

1. **Requirements:**  
   - Windows 7 or later  
   - Python (pre-installed or installed via the setup script)  
   - Administrator privileges (for some operations)

2. **Setup Script:**  
   Run the provided Windows setup script (e.g., `setup.py`):

   ```bat
   python setup.py
   ```

   This script will:
   - Create a virtual environment under `%APPDATA%\quran-player`
   - Copy application files and assets
   - Install required dependencies (including `pywin32` and `winshell`)
   - Create CLI wrappers in `%APPDATA%\quran-player\bin`
   - Create a desktop shortcut for launching the GUI

3. **Logs:**  
   Check `install.log` (generated in the current directory) for details and troubleshooting.

---

### Linux

1. **Requirements:**  
   - A modern Linux distribution (Ubuntu, Debian, Arch, etc.)
   - Bash shell, Python3, and sudo privileges for certain installation steps

2. **Make Script Executable:**  
   ```bash
   chmod +x install.sh
   ```

3. **Run the Installer:**  
   ```bash
   ./install.sh
   ```

   The script will:
   - Install system dependencies (e.g., `python3-venv`, `feh`, `pulseaudio-utils`)
   - Copy application files and assets to `~/.quran-player`
   - Create a virtual environment and install Python dependencies
   - Create CLI wrappers in `/usr/local/bin`
   - Generate a desktop entry in `~/.local/share/applications`
   - Install the man page for `quran-daemon`
   
4. **Uninstallation:**  
   To uninstall, run:
   ```bash
   ./install.sh --uninstall
   ```

---

## Usage

### Daemon Commands

The daemon is controlled via CLI commands. Use the generated wrappers:

- **Start the Daemon:**  
  ```bash
  quran-daemon start
  ```
- **Stop the Daemon:**  
  ```bash
  quran-daemon stop
  ```
- **Playback Control:**  
  ```bash
  quran-daemon play     # Resume playback
  quran-daemon pause    # Pause playback
  quran-daemon toggle   # Toggle between play and pause
  quran-daemon next     # Advance to the next verse
  quran-daemon prev     # Go back to the previous verse
  ```
- **Load a Specific Verse:**  
  ```bash
  quran-daemon load 2:255
  ```
- **Repeat a Range of Verses:**  
  ```bash
  quran-daemon repeat 10:15
  ```
- **Display Status:**  
  ```bash
  quran-daemon status
  ```
- **Generate Configuration File:**  
  ```bash
  quran-daemon config
  ```
- **Display Detailed Information:**  
  ```bash
  quran-daemon info
  ```
- **Help / About:**  
  ```bash
  quran-daemon help
  quran-daemon about
  ```

### GUI Controller

Launch the GUI using the desktop shortcut (Windows) or via the CLI wrapper:

```bash
quran-gui
```

The GUI features:
- Dark theme with a custom Fusion palette
- System tray integration and context menu
- Keyboard shortcuts: Space (play/pause), Left (previous), Right (next), Esc (minimize)

### Search Tool

Run the search tool with:

```bash
quran-search <surah> <start_ayah> [end_ayah]
```

If no arguments are provided, the tool launches an interactive dialog (YAD on Linux, or a PyQt5-based alternative).

### Image Rendering

The script `arabic_topng.py` renders Arabic text to a PNG image with options for wrapping, padding, and color customization. This is used internally by the player for displaying verses.


#### **Audio Files**
The Quran Player requires Quranic audio files named in the format `XXXYYY.mp3`, where:
- `XXX` is the 3-digit surah number (e.g., `002` for Surah Al-Baqarah)
- `YYY` is the 3-digit ayah number (e.g., `001` for the first ayah)

**Example**: `002001.mp3` for Surah 2, Ayah 1.

You can download these files from sources like [EveryAyah.com](https://everyayah.com/recitations_ayat.html). Place the files in the `~/.config/quran-player/sample/` directory (or the configured `FILES_DIRECTORY` in `config.ini`).

---

## Configuration

The application is configured via an INI file. By default:

- **Linux/macOS:** `~/.config/quran-player/config.ini`
- **Windows:** `%APPDATA%\quran-player\config.ini`

### [daemon] Section

- **MAX_LOG_SIZE:**  
  Maximum log file size in bytes (default: 1000000).

- **LOG_LEVEL:**  
  Log verbosity. Options: `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`, `DISABLED` (default: `INFO`).

- **FILES_DIRECTORY:**  
  Directory where audio files are stored.

### [image] Section

- **ENABLE:**  
  Enable image display (`yes`/`no`). (Default: `yes` on Linux, `no` on other platforms)

- **DEFAULT_RESOLUTION:**  
  Resolution for the generated image (e.g., `1240x170`).

- **FONT_FILE:**  
  Path to the Arabic font file (default: `arabic-font.ttf`).

- **FONT_SIZE:**  
  Font size for rendering (default: `48`).

- **IMAGE_WIDTH:**  
  Width of the image in pixels (default: `1240`).

- **WRAP_WIDTH:**  
  Maximum number of characters per line (default: `170`).

- **VERTICAL_PADDING:**  
  Padding in pixels (default: `20`).

- **BG_COLOR:**  
  Background color (RGBA, e.g., `0,0,0,0`).

- **TEXT_COLOR:**  
  Text color (RGBA, e.g., `255,255,255,255`).

- **HIGHLIGHT_COLOR:**  
  Highlight color (RGBA, e.g., `255,0,0,255`).

---

**Important Note on Audio Files:** The Quran Player Daemon requires Quranic audio files named in the specific format `XXXYYY.mp3`, where `XXX` is the 3-digit surah number and `YYY` is the 3-digit ayah number (e.g., `002001.mp3` for Surah 2, Ayah 1). While basic sample files are included, **full functionality requires downloading complete verse-by-verse audio collections** from sources like [EveryAyah.com](https://everyayah.com/recitations_ayat.html), which offers recitations in this standardized format. After downloading, place the files in the `~/.config/quran-player/sample/` directory (or your configured `FILES_DIRECTORY`). Ensure all files follow this naming scheme for seamless playback across all 114 surahs.



## Manual

Below is the full manual, which is also available as a man page (`quran-daemon.1`):

```
===================================================================
                       Quran Player Daemon Manual
                            Version: v1.3.0
                           Date: Feb 2025
===================================================================

NAME
    quran-daemon - Quran Player Daemon

SYNOPSIS
    quran-daemon [COMMAND] [ARGUMENTS]...

DESCRIPTION
    The Quran Player Daemon is a background service that provides Quranic verse
    playback with synchronized visual display and Arabic text rendering. It supports
    verse-by-verse playback with auto-advance, persistent playback state across
    sessions, repeat functionality, and an optional system tray GUI controller.

COMMANDS
    start
        Start the daemon. This initializes the service, binds the control socket, and
        begins listening for client commands.

    stop
        Stop the daemon. This causes the daemon to shut down gracefully, releasing all
        resources and cleaning up socket and PID files.

    play
        Resume audio playback.

    pause
        Pause the current playback.

    toggle
        Toggle between play and pause.

    next
        Advance to the next verse.

    prev
        Return to the previous verse.

    load
        Load a specific verse. The command expects an argument in the format
        surah:ayah (for example, "2:255").

    repeat
        Repeat a range of verses. Provide the range in the format
        start:end (for example, "10:15"). Note that issuing a play or load command
        cancels repeat mode.

    status
        Display the current playback status, including the surah and ayah numbers and
        playback state.

    config
        Generate the default configuration file in the user configuration directory.

    cleanup
        Remove orphaned runtime files (e.g., stale PID or socket files).

    info
        Display detailed information about daemon status, configuration settings,
        file integrity, and system information.

    help
        Display a help message with a summary of available commands.

    about
        Display program information, including version, project links, and license details.

CONFIGURATION
    The daemon uses an INI-style configuration file. On Linux/macOS, the file is typically
    located at:
        ~/.config/quran-player/config.ini
    On Windows, it is stored in the APPDATA folder.

    The configuration file is divided into two main sections: [daemon] and [image].

    -----------------------------------------------------------------
    [daemon] Section
    -----------------------------------------------------------------
    MAX_LOG_SIZE
        Maximum size (in bytes) of the log file before rotation occurs.
        Default: 1000000.

    LOG_LEVEL
        Log verbosity level. Possible values are:
        CRITICAL, ERROR, WARNING, INFO, DEBUG, or DISABLED.
        Default: INFO.

    FILES_DIRECTORY
        The directory where the audio files are stored. If not specified, a default directory
        (e.g., within the user configuration directory) is used.

    -----------------------------------------------------------------
    [image] Section
    -----------------------------------------------------------------
    ENABLE
        Enable or disable image display. Accepts "yes" or "no". Default is "yes" on Linux
        and "no" on other platforms.

    DEFAULT_RESOLUTION
        Default resolution for the generated image in the format WIDTHxHEIGHT (e.g., "1240x170").

    FONT_FILE
        Path to the Arabic font file used for rendering. By default, the "arabic-font.ttf"
        in the script or user configuration directory is used.

    FONT_SIZE
        Font size for rendering the text. Default: 48.

    IMAGE_WIDTH
        Width of the generated image in pixels. Default: 1240.

    WRAP_WIDTH
        Maximum number of characters per line before wrapping. Default: 170.

    VERTICAL_PADDING
        Vertical padding (in pixels) added to the top and bottom of the image. Default: 20.

    BG_COLOR
        Background color as a comma-separated RGBA string (for example, "0,0,0,0").
        Default: 0,0,0,0.

    TEXT_COLOR
        Text color as a comma-separated RGBA string (for example, "255,255,255,255").
        Default: 255,255,255,255.

    HIGHLIGHT_COLOR
        Highlight color for indicating a specific line, as a comma-separated RGBA string
        (for example, "255,0,0,255").
        Default: 255,0,0,255.

FILES
    quran_player.py
        The main daemon script.
    default_config.ini
        Default configuration file shipped with the daemon.
    config.ini
        User configuration file. Typically located in ~/.config/quran-player/ (Linux/macOS)
        or in the APPDATA folder (Windows).
    daemon.sock or \\.\pipe\quran-daemon (Windows)
        The control socket used for inter-process communication.
    daemon.pid
        File storing the daemon's process ID.
    daemon.log
        Log file for daemon events.

USAGE EXAMPLES
    Start the daemon:
        quran-daemon start

    Stop the daemon:
        quran-daemon stop

    Toggle playback:
        quran-daemon toggle

    Load a specific verse:
        quran-daemon load 2:255

    Repeat a range of verses:
        quran-daemon repeat 10:15

    Display status:
        quran-daemon status

    Generate a new configuration file:
        quran-daemon config

    Display help:
        quran-daemon help

ENVIRONMENT VARIABLES
    The following environment variables can override default configuration values:
    PYTHON_IMAGE_WIDTH
        Overrides the default image width.
    PYTHON_IMAGE_WRAP_WIDTH
        Overrides the default wrap width.
    PYTHON_IMAGE_FONT_SIZE
        Overrides the default font size.
    PYTHON_IMAGE_FONT
        Overrides the default font family.
    PYTHON_IMAGE_BG_COLOR
        Overrides the default background color.
    PYTHON_IMAGE_TEXT_COLOR
        Overrides the default text color.
    PYTHON_IMAGE_HIGHLIGHT_COLOR
        Overrides the default highlight color.
    PYTHON_IMAGE_VERTICAL_PADDING
        Overrides the default vertical padding.

BUGS
    Report bugs and issues via the project's GitHub issue tracker:
        https://github.com/neoMOSAID/quran-player/issues

AUTHOR
    Developed by neoMOSAID.

COPYRIGHT
    This software is released under the GPLv3 License.

===================================================================
```

---

## Contributing

Contributions, bug reports, and feature requests are welcome! Please open an issue or submit a pull request on [GitHub](https://github.com/neoMOSAID/quran-player).

---

## License

This project is licensed under the terms of the [GPLv3 License](https://www.gnu.org/licenses/gpl-3.0.en.html).

---

## Support

For help and support:
- Website: [mosaid.xyz]( https://mosaid.xyz/quran-player)
- Email: mail@mosaid.xyz
- [Documentation Wiki](https://github.com/neoMOSAID/quran-player/wiki)
- [Issues Tracker](https://github.com/neoMOSAID/quran-player/issues)


```

