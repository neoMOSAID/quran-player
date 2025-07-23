#!/bin/bash
# run conky silently
nohup conky -c "$(dirname "$0" )/conky_quran" </dev/null >/dev/null 2>&1 &

