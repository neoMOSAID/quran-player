
"""Argparse setup for the daemon CLI. Pure function — no Daemon dependency."""

import argparse


def build_parser():
    fmt = argparse.RawDescriptionHelpFormatter

    parser = argparse.ArgumentParser(
        description='Quran Player Daemon — Linux-native with Conky display',
        epilog=(
            "Run 'quran-daemon <command> --help' for detailed help and examples.\n"
            "© 2026 Quran Player Project - GPLv3 License"
        ),
        formatter_class=fmt,
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    def _add(name, help_text, description, epilog=None):
        return subparsers.add_parser(
            name,
            help=help_text,
            description=description,
            epilog=epilog,
            formatter_class=fmt,
        )

    _add('start', 'Start the daemon',
         'Start the quran-player daemon in the current terminal.',
         "examples:\n"
         "  quran-daemon start            # run in foreground (Ctrl-C to quit)\n"
         "  quran-daemon start &          # run in the background\n")
    _add('stop', 'Stop the daemon',
         'Ask the running daemon to shut down gracefully.',
         "examples:\n  quran-daemon stop\n")
    _add('play', 'Resume audio',
         'Resume playback from the last saved verse (or start the current verse).')
    _add('pause', 'Pause audio',
         'Pause the current verse, keeping the playback position.')
    _add('toggle', 'Toggle play/pause',
         'Toggle between playing and paused.')
    _add('prev', 'Previous verse',
         'Jump to the previous ayah (wraps across surah boundaries).')
    _add('next', 'Next verse',
         'Jump to the next ayah (wraps across surah boundaries).')
    _add('ns', 'Next surah',
         'Load the next surah from its beginning (skips bismillah for Surah 9).',
         "examples:\n  quran-daemon ns               # 1 → 2, 2 → 3, … 114 → 1\n")
    _add('ps', 'Previous surah',
         'Load the previous surah from its beginning.',
         "examples:\n  quran-daemon ps               # 2 → 1, 1 → 114\n")
    _add('repeat_off', 'Exit repeat mode',
         'Turn off repeat mode if it is active.')
    _add('conky_on', 'Enable Conky display',
         'Start the Conky desktop verse display.')
    _add('conky_off', 'Disable Conky display',
         'Stop the Conky desktop verse display.')
    _add('conky_toggle', 'Toggle Conky display',
         'Toggle the Conky desktop verse display on/off.')

    goto_parser = _add(
        'goto', 'Jump to ayah in current surah',
        'Jump to a specific ayah within the current surah.',
        "notes:\n"
        "  • If repeat mode is active, the ayah must be inside the repeat range.\n"
        "  • Use 'load <surah>:<ayah>' to change surah too.\n\n"
        "examples:\n"
        "  quran-daemon goto 255         # Surah 2 → ayah 255 (Ayat al-Kursi)\n"
        "  quran-daemon goto 0           # bismillah of current surah (if audio exists)\n")
    goto_parser.add_argument('ayah', type=int, help='Ayah number within the current surah')

    load_parser = _add(
        'load', 'Load surah or verse',
        'Load a surah or a specific verse and start playing it.',
        "format:\n"
        "  <surah>            load surah from its beginning\n"
        "  <surah>:<ayah>     load a specific ayah\n\n"
        "notes:\n"
        "  • Surahs normally start at ayah 0 (bismillah); if no bismillah\n"
        "    audio exists, playback starts at ayah 1.\n"
        "  • Surah 9 (At-Tawbah) has no bismillah and always starts at ayah 1.\n"
        "  • Loading a verse clears any active repeat range.\n\n"
        "examples:\n"
        "  quran-daemon load 5           # Surah 5 (Al-Ma'idah) from the top\n"
        "  quran-daemon load 5:3         # Surah 5, ayah 3\n"
        "  quran-daemon load 2:255       # Ayat al-Kursi\n")
    load_parser.add_argument(
        'verse', nargs='?', default='1:0',
        help="'<surah>' or '<surah>:<ayah>' (default: 1:0)")

    repeat_parser = _add(
        'repeat', 'Repeat range',
        'Repeat a single surah, a range in the current surah, or a range in a named surah.',
        "forms:\n"
        "  <surah>               repeat the entire surah (from bismillah or ayah 1)\n"
        "  <start>:<end>         repeat a range within the current surah\n"
        "  <surah>:<start>:<end> repeat a range in the named surah\n"
        "  off                   turn repeat mode off (also the default)\n\n"
        "examples:\n"
        "  quran-daemon repeat 5          # repeat all of Surah 5\n"
        "  quran-daemon repeat 2:255      # repeat Surah 2, ayah 255 only\n"
        "  quran-daemon repeat 2:1:20     # repeat Surah 2, ayat 1 through 20\n"
        "  quran-daemon repeat 1:7        # current surah, ayat 1 through 7\n"
        "  quran-daemon repeat off        # stop repeating\n")
    repeat_parser.add_argument(
        'range', nargs='?', default='off',
        help="'<surah>', '<start>:<end>', '<surah>:<start>:<end>', or 'off' (default: off)")

    dir_parser = _add(
        'dir', 'Change audio directory',
        'Switch the daemon to a different folder of audio files.',
        "notes:\n"
        "  • The directory must contain files named SSSAAA.mp3\n"
        "    (SSS = surah, AAA = ayah, e.g. 002255.mp3).\n"
        "  • Current playback is reloaded from the new directory.\n"
        "  • The new path is saved to config.ini.\n\n"
        "examples:\n"
        "  quran-daemon dir ~/quran-audio/full\n"
        "  quran-daemon dir /mnt/usb/quran\n")
    dir_parser.add_argument('path', help='Path to a directory of SSSAAA.mp3 files')

    _add('status', 'Playback status',
         'Print a JSON snapshot of the daemon state.',
         "output fields:\n"
         "  playing, paused       current playback state\n"
         "  surah, ayah           current verse\n"
         "  repeat                true if a repeat range is active\n"
         "  repeat_start/_end     the repeat range (if active)\n"
         "  conky_enabled         user preference\n"
         "  conky_running         whether conky is actually running\n"
         "  daemon_running        always true while the daemon is up\n\n"
         "examples:\n"
         "  quran-daemon status\n"
         "  quran-daemon status | jq .ayah\n")
    _add('cleanup', 'Remove stale runtime files',
         'Delete leftover daemon.pid / daemon.sock when no daemon is running.')
    _add('info', 'Diagnostic dump',
         'Print a detailed diagnostic report (paths, logs, audio files, system).',
         "examples:\n  quran-daemon info             # works with or without the daemon running\n")
    _add('about', 'About',
         'Show project info, links, and the full command reference.')
    _add('help', 'Help', "Alias for 'about'.")
    _add('config', 'Regenerate config',
         'Write a fresh default config.ini to ~/.config/quran-player/.',
         "notes:\n"
         "  • Overwrites any existing config.ini with the defaults.\n"
         "  • Target path: ~/.config/quran-player/config.ini\n")

    return parser


    