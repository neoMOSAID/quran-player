
#!/usr/bin/env python3
"""Reshape / RTL-normalize / wrap Arabic text for conky.

Importable:
    from reshape_arabic import reshape_and_wrap_arabic_text
    wrapped = reshape_and_wrap_arabic_text("بِسْمِ ٱللَّهِ", 100)

CLI:
    python reshape_arabic.py "بِسْمِ ٱللَّهِ"
"""
from arabic_reshaper import ArabicReshaper
from bidi.algorithm import get_display
import os
import sys

script_directory = os.path.dirname(os.path.realpath(__file__))
config_file_path = os.path.join(script_directory, 'config.ini')


def reshape_and_wrap_arabic_text(text, line_length=100):
    reshaper = ArabicReshaper(configuration_file=config_file_path)
    reshaped_text = reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)

    words = bidi_text.split()[::-1]
    lines = []
    current_line = []

    for word in words:
        prospective_line = " ".join(current_line + [word])
        if len(prospective_line) <= line_length:
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    lines = [" ".join(line.split()[::-1]) for line in lines]
    return "\n".join(lines[::-1])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: reshape_arabic.py <arabic-text>", file=sys.stderr)
        sys.exit(1)
    print(reshape_and_wrap_arabic_text(sys.argv[1], 100))
    