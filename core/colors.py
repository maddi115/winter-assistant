"""Neon highlights in the terminal.

  neon pink  = pulled from a memory vessel (memory.txt / system.txt)
  neon green = your own words from imported chat data

Colors only show in a real terminal; saved history and files stay plain text.
"""
import re
import sys

PINK = "\033[1;38;2;255;16;240m"    # #FF10F0
GREEN = "\033[1;38;2;57;255;20m"    # #39FF14
DIM = "\033[2m"
RESET = "\033[0m"
ENABLED = sys.stdout.isatty()


def pink(s: str) -> str:
    return f"{PINK}{s}{RESET}" if ENABLED else s


def green(s: str) -> str:
    return f"{GREEN}{s}{RESET}" if ENABLED else s


def dim(s: str) -> str:
    return f"{DIM}{s}{RESET}" if ENABLED else s


def strip(s: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", s)
