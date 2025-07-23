# Install the arabic_reshaper package if you haven't already
# You can install it using: pip install arabic-reshaper
# install bidi using      : pip install python-bidi

from arabic_reshaper import ArabicReshaper
from bidi.algorithm import get_display
import sys
import os

script_directory = os.path.dirname(os.path.realpath(__file__))
config_file_path = os.path.join(script_directory, 'config.ini')


def reshape_and_wrap_arabic_text(text, line_length=100):
    reshaper = ArabicReshaper(configuration_file=config_file_path)
    reshaped_text = reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)

    # Split the text into words
    #words = bidi_text.split()
    words = bidi_text.split()[::-1]  # reverse the word order


    # Initialize line buffers
    lines = []
    current_line = []

    for word in words:
        # Measure visual width (roughly, using len without diacritics)
        prospective_line = " ".join(current_line + [word])
        if len(prospective_line) <= line_length:
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    # Reverse words in each line back to normal RTL order
    lines = [ " ".join(line.split()[::-1]) for line in lines ]

    # Reverse the lines top-to-bottom for Conky stacking
    return "\n".join(lines[::-1])



arabic_text =  sys.argv[1]
wrapped_text = reshape_and_wrap_arabic_text(arabic_text, 100)
print(wrapped_text)
