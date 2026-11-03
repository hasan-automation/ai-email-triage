#!/usr/bin/env python3
"""Sort an inbox with Claude.  Try it without a key:  python triage.py --demo"""
import sys

from email_triage.cli import main

if __name__ == "__main__":
    sys.exit(main())
