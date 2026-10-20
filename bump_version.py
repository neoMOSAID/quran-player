
#!/usr/bin/env python3
"""
Update version strings in documentation files from the VERSION file.

Only updates three specific patterns:
  • README.md   : **Version:** vX.Y.Z
  • manual.txt  : Version: vX.Y.Z     (start of line)
  • quran-daemon.1 : .TH QURAN-DAEMON 1 "..." "vX.Y.Z" "..."

Code files (daemon.py, quran_gui.py) do NOT need updating — they read
VERSION at runtime via version.py.

Usage:
    python bump_version.py           # apply
    python bump_version.py --check   # verify (non-zero exit if out of sync)
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "VERSION"

if not VERSION_FILE.exists():
    print(f"Error: {VERSION_FILE} not found", file=sys.stderr)
    sys.exit(1)

VERSION = VERSION_FILE.read_text(encoding="utf-8").strip()
if not re.fullmatch(r"\d+\.\d+\.\d+", VERSION):
    print(f"Error: VERSION contains '{VERSION}', expected MAJOR.MINOR.PATCH", file=sys.stderr)
    sys.exit(1)

# (path, compiled regex, replacement template)
# Each regex captures the *prefix* (with `\g<N>` backreference in the
# replacement) so only the version number changes.
TARGETS = [
    (
        ROOT / "README.md",
        re.compile(r"(\*\*Version:\*\* v)\d+\.\d+\.\d+"),
        r"\g<1>" + VERSION,
    ),
    (
        ROOT / "manual.txt",
        re.compile(r"^(Version: v)\d+\.\d+\.\d+$", re.MULTILINE),
        r"\g<1>" + VERSION,
    ),
    (
        ROOT / "quran-daemon.1",
        re.compile(r'(\.TH QURAN-DAEMON 1 "[^"]*" ")v\d+\.\d+\.\d+'),
        r"\g<1>v" + VERSION,
    ),
]


def main() -> int:
    check_only = "--check" in sys.argv[1:]
    stale = []

    for path, pattern, replacement in TARGETS:
        if not path.exists():
            print(f"⚠  skipping missing file: {path.name}")
            continue
        original = path.read_text(encoding="utf-8")
        updated, n = pattern.subn(replacement, original)
        if n == 0:
            print(f"⚠  no match in {path.name} (already {VERSION}?)")
            continue
        if original == updated:
            print(f"   {path.name}: already at {VERSION}")
            continue
        stale.append(path.name)
        if not check_only:
            path.write_text(updated, encoding="utf-8")
            print(f"   {path.name}: updated {n} match(es) → {VERSION}")

    if check_only and stale:
        print(f"✗ out of sync: {', '.join(stale)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

    