# SPDX-License-Identifier: MIT
"""Make per-user installed fonts visible to OCCT.

On Windows, fonts installed "for current user only" (the default when
double-clicking a .ttf, and what Nerd Font installers do) live in
%LOCALAPPDATA%/Microsoft/Windows/Fonts. OCCT's Font_FontMgr only scans the
system font folder, so those fonts are missing from `available_fonts()` and
`Text()` silently falls back to another font.
"""

import os
import sys
from pathlib import Path

from OCP.Font import Font_FontMgr

FONT_SUFFIXES: tuple[str, ...] = (".ttf", ".otf", ".ttc")


def user_font_dirs() -> list[Path]:
    """Per-user font folders OCCT does not scan by itself."""
    dirs: list[Path] = []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    return [d for d in dirs if d.is_dir()]


def register_user_fonts() -> int:
    """Register all per-user font files with OCCT; returns the number added."""
    mgr = Font_FontMgr.GetInstance_s()
    count = 0
    for folder in user_font_dirs():
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() not in FONT_SUFFIXES:
                continue
            font = mgr.CheckFont(str(path))
            if font is not None and mgr.RegisterFont(font, False):
                count += 1
    return count
