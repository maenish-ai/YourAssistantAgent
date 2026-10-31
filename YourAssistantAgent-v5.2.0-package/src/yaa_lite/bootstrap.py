"""Shared application initialization for source, console and packaged entrypoints.

Importing the module has no side effects. The patch order is kept in one place
because later UI/controller layers intentionally wrap earlier ones.
"""
from __future__ import annotations

_CONFIGURED = False


def configure_application() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    from .hotfix_v202 import apply_hotfixes
    apply_hotfixes()
    from .personal_assistant_v220 import apply_personal_assistant
    apply_personal_assistant()
    from .cloud_voice_v240 import apply_cloud_voice_v240
    apply_cloud_voice_v240()
    from .fast_stream_v250 import apply_stream_v250
    apply_stream_v250()
    from .fast_live_v250 import apply_fast_live_v250
    apply_fast_live_v250()
    from .stability_v260 import apply_stability_v260
    apply_stability_v260()
    from .review_voice_v270 import apply_review_voice_v270
    apply_review_voice_v270()
    from .repair_v280 import apply_repair_v280
    apply_repair_v280()
    from .lightweight_v290 import apply_lightweight_v290
    apply_lightweight_v290()
    from .text_first_v300 import apply_text_first_v300
    apply_text_first_v300()

    # v4.1: on-demand Windows discovery and explicit background/exit choice.
    from .v410_ui import apply_v410_ui
    apply_v410_ui()

    from .v420_ui import apply_v420_ui
    apply_v420_ui()

    # v4.3: reviewed, approved ZIP-to-GitHub publishing via local Git checkout.
    from .github_upload_v430 import apply_v430_ui
    apply_v430_ui()
    from .workflow_v490 import apply_workflow_v490
    apply_workflow_v490()
    _CONFIGURED = True
