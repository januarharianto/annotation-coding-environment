"""Detect if a file path is inside a cloud-sync directory."""

from pathlib import Path

_CLOUD_MARKERS = [
    "dropbox",
    "onedrive",
    "google drive",
    "mobile documents",
    "icloud",
]


def is_cloud_sync_path(path: Path) -> bool:
    parts_lower = str(path.resolve()).lower()
    return any(marker in parts_lower for marker in _CLOUD_MARKERS)
