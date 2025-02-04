#!/bin/bash

# Activate virtual environment
source "$(dirname "$0")/env/bin/activate"

# Start GUI controller
python3 "$(dirname "$0")/quran_gui.py" $@
