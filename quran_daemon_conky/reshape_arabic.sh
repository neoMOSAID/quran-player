
#!/bin/bash
# Reshape / RTL-normalize the current verse for Conky.
# Reads /tmp/quran_verse.txt (written by daemon) and emits up to 7 lines (bottom-up).

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
VENV_PY="${HOME}/.quran-player/env/bin/python"

arabic_text="$(cat /tmp/quran_verse.txt 2>/dev/null)"
[ -z "$arabic_text" ] && exit 0

[ -x "$VENV_PY" ] || { echo "reshape_arabic: missing venv python at $VENV_PY" >&2; exit 1; }
[ -f "$SCRIPT_DIR/reshape_arabic.py" ] || { echo "reshape_arabic: missing script" >&2; exit 1; }

reshaped=$("$VENV_PY" "$SCRIPT_DIR/reshape_arabic.py" "$arabic_text")
for i in $(seq 7 -1 1); do
    line=$(echo "$reshaped" | sed -n "${i}p")
    if [[ -n "$line" ]]; then
        printf '%s\n' "$line"
    fi
done
