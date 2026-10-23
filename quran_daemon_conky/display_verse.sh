
#!/bin/bash
# display_verse.sh — emit the current verse as conky-aligned rows.
#
# Reads /tmp/quran_verse_reshaped.txt (written atomically by the daemon in
# bottom-to-top order), normalizes all Unicode line/paragraph separators to
# plain \n, reverses to top-to-bottom, drops empty lines, and prefixes each
# remaining line with ${alignr} so per-line RTL alignment works under
# conky's $execpi.
#
# Normalization is the important part: U+2028 and U+2029 render as line
# breaks in terminals but are NOT recognized by tac / read / head, which
# causes the whole file to be treated as one line.

set -u
MAX_LINES=6
PY="${HOME}/.quran-player/env/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -n "$PY" ] || exit 0

TMPDIR="${TMPDIR:-/tmp}"
export VERSE_FILE="$TMPDIR/quran_verse_reshaped.txt"

MAX_LINES="$MAX_LINES" "$PY" - <<'PYEOF'
import os, sys

path = os.environ['VERSE_FILE']

try:
    with open(path, encoding='utf-8') as f:
        text = f.read()
except (FileNotFoundError, OSError):
    sys.exit(0)

# Normalize every Unicode line/paragraph separator to plain \n.
text = (text
        .replace('\u2028', '\n')   # LINE SEPARATOR
        .replace('\u2029', '\n')   # PARAGRAPH SEPARATOR
        .replace('\r\n', '\n')     # CRLF
        .replace('\r', '\n'))      # CR

lines = [ln for ln in text.split('\n') if ln.strip()]
lines.reverse()                    # bottom-to-top → top-to-bottom

cap = int(os.environ.get('MAX_LINES', '6'))
for ln in lines[:cap]:
    print('${alignr}' + ln)
PYEOF
