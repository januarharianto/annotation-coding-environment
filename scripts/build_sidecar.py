#!/usr/bin/env python3
"""Compile ACE server as a Nuitka onefile sidecar for Tauri.

Cross-platform: works on macOS, Windows, and Linux.
Called by Tauri's beforeBundleCommand during `cargo tauri build`.
Can also be run directly: `uv run python scripts/build_sidecar.py`
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Tauri sets these during `cargo tauri build`; fall back to host detection
PLATFORM = os.environ.get("TAURI_ENV_PLATFORM", "")
ARCH = os.environ.get("TAURI_ENV_ARCH", "")

TRIPLES = {
    ("darwin", "aarch64"): "aarch64-apple-darwin",
    ("darwin", "x86_64"): "x86_64-apple-darwin",
    ("windows", "x86_64"): "x86_64-pc-windows-msvc",
    ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
}


def get_host_triple() -> str:
    """Get the Rust target triple for the current host."""
    result = subprocess.run(
        ["rustc", "-vV"], capture_output=True, text=True, check=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("Could not determine host triple from rustc")


def main() -> None:
    # Determine target triple
    if PLATFORM and ARCH:
        triple = TRIPLES.get((PLATFORM, ARCH))
        if not triple:
            sys.exit(f"Unsupported platform: {PLATFORM}-{ARCH}")
    else:
        triple = get_host_triple()

    ext = ".exe" if "windows" in triple else ""
    binary_name = f"ace-server-{triple}{ext}"
    out_dir = Path("desktop/src-tauri/binaries")
    out_dir.mkdir(parents=True, exist_ok=True)

    build_dir = Path(tempfile.gettempdir()) / "ace-build"

    print(f"Compiling ACE for {triple}...")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src"))

    cmd = [
        sys.executable, "-m", "nuitka",
        "--onefile",
        f"--onefile-tempdir-spec={{CACHE_DIR}}/ace-coder",
        f"--output-dir={build_dir}",
        f"--output-filename={binary_name}",
        "--include-package=ace",
        "--include-data-dir=src/ace/static=ace/static",
        "--include-data-dir=src/ace/templates=ace/templates",
        "--assume-yes-for-downloads",
        str(Path("src/ace/__main__.py")),
    ]

    subprocess.run(cmd, check=True, env=env)

    binary = build_dir / binary_name
    if not binary.exists():
        sys.exit(f"ERROR: compiled binary not found at {binary}")

    dest = out_dir / binary_name
    shutil.copy2(str(binary), str(dest))
    print(f"Binary placed at {dest} ({dest.stat().st_size // (1024*1024)} MB)")


if __name__ == "__main__":
    main()
