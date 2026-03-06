"""Tests for cloud-sync directory detection."""

from pathlib import Path

from ace.services.cloud_detect import is_cloud_sync_path


def test_dropbox_detected():
    assert is_cloud_sync_path(Path("/Users/alice/Dropbox/project.ace"))


def test_onedrive_detected():
    assert is_cloud_sync_path(Path("/Users/alice/OneDrive/work/project.ace"))


def test_icloud_detected():
    assert is_cloud_sync_path(
        Path("/Users/alice/Library/Mobile Documents/com~apple~CloudDocs/project.ace")
    )


def test_google_drive_detected():
    assert is_cloud_sync_path(Path("/Users/alice/Google Drive/project.ace"))


def test_normal_path_not_detected():
    assert not is_cloud_sync_path(Path("/Users/alice/Documents/project.ace"))


def test_home_directory_not_detected():
    assert not is_cloud_sync_path(Path("/Users/alice/project.ace"))


def test_case_insensitive_dropbox():
    assert is_cloud_sync_path(Path("/Users/alice/dropbox/project.ace"))
