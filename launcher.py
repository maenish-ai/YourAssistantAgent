"""Stable PyInstaller entry point for Your Assistant Agent."""
from __future__ import annotations

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    src = Path(__file__).resolve().parent / "src"
    if src.exists():
        sys.path.insert(0, str(src))

from yaa_lite.hotfix_v202 import apply_hotfixes
apply_hotfixes()
from yaa_lite.personal_assistant_v220 import apply_personal_assistant
apply_personal_assistant()
from yaa_lite.cloud_voice_v240 import apply_cloud_voice_v240
apply_cloud_voice_v240()
from yaa_lite.fast_stream_v250 import apply_stream_v250
apply_stream_v250()
from yaa_lite.fast_live_v250 import apply_fast_live_v250
apply_fast_live_v250()
from yaa_lite.stability_v260 import apply_stability_v260
apply_stability_v260()
from yaa_lite.review_voice_v270 import apply_review_voice_v270
apply_review_voice_v270()
from yaa_lite.repair_v280 import apply_repair_v280
apply_repair_v280()
from yaa_lite.lightweight_v290 import apply_lightweight_v290
apply_lightweight_v290()
from yaa_lite.text_first_v300 import apply_text_first_v300
apply_text_first_v300()

# v4.1: on-demand Windows discovery and explicit background/exit choice.
from yaa_lite.v410_ui import apply_v410_ui
apply_v410_ui()

from yaa_lite.v420_ui import apply_v420_ui
apply_v420_ui()

from yaa_lite.main import main
if __name__ == '__main__':
    raise SystemExit(main())
