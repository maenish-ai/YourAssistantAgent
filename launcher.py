"""Stable PyInstaller entry point for Your Assistant Agent.

This file deliberately imports the application by its absolute package name.
Building src/yaa_lite/main.py directly makes Python treat that file as a loose
script, which breaks its relative imports in a frozen EXE.
"""
from __future__ import annotations

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    src = Path(__file__).resolve().parent / "src"
    if src.exists():
        sys.path.insert(0, str(src))

from yaa_lite.main import main


if __name__ == "__main__":
    raise SystemExit(main())
