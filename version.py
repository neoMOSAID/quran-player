
"""Single source of truth for the version — reads the VERSION file.

On install, `install.py` copies both `VERSION` and `version.py` to
`~/.quran-player/`, so `__file__`-relative lookup works in both source
and installed contexts.
"""

import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_VERSION_FILE = os.path.join(_SCRIPT_DIR, "VERSION")


def _read_version() -> str:
    try:
        with open(_VERSION_FILE, "r", encoding="utf-8") as f:
            v = f.read().strip()
        return v or "0.0.0"
    except OSError:
        return "0.0.0"


VERSION = _read_version()
__version__ = VERSION

