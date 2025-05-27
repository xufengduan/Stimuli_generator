#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Quickly start the Stimulus Generator script
"""

import sys
from stimulus_generator.cli import main

if __name__ == "__main__":
    # if no argument is provided, default to starting the web interface
    if len(sys.argv) == 1:
        sys.argv.append("webui")
    main() 