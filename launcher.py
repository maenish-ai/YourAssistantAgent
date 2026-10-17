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

# Keep the v2.0.2 normal-browser/Facebook compatibility fixes. The v2.1 hotfix
# module deliberately no longer patches the AI runtime; Qwen3 owns it natively.
from yaa_lite.hotfix_v202 import apply_hotfixes
apply_hotfixes()

# v2.2: Qwen is the direct personal assistant. Normal chat is plain text;
# application capabilities are exposed through native Qwen/llama.cpp tools.
from yaa_lite.personal_assistant_v220 import apply_personal_assistant
apply_personal_assistant()

from yaa_lite.main import main


if __name__ == "__main__":
    raise SystemExit(main())
