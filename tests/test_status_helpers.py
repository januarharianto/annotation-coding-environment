"""Static checks for bridge.js status helpers (Task 2 of notification redesign).

These tests scan the JS source for the expected public API rather than exercising
the IIFE at runtime. Full behavioural verification happens manually in-browser
and via the Playwright pass in Task 8.
"""
from pathlib import Path


BRIDGE = Path(__file__).resolve().parent.parent / "src" / "ace" / "static" / "js" / "bridge.js"


def test_bridge_exposes_set_status():
    src = BRIDGE.read_text(encoding="utf-8")
    assert "window._setStatus" in src, "missing _setStatus export"


def test_bridge_has_assertive_announce_branch():
    src = BRIDGE.read_text(encoding="utf-8")
    assert "ace-live-region-assertive" in src, "missing assertive live region handling"
