#!/bin/bash

arabic_text="$(cat /tmp/quran_verse.txt )"
py="${HOME}/.config/conky/quran_daemon/env/bin/python"
pys="${HOME}/.config/conky/quran_daemon/reshape_arabic.py"

reshaped_arabic_text=$( "$py" "$pys" "$arabic_text" )
for i in $(seq 7 -1 1); do
    line=$(echo "$reshaped_arabic_text" | sed -n "${i}p")
    if [[ -n "$line" ]]; then
        printf '%s\n' "$line"
    fi
done
