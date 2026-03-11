"""Helpers for locating app resources across source and packaged builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable


def iter_resource_roots() -> Iterable[Path]:
    """Yield plausible resource roots for source, CLI, and packaged app runs."""
    env_root = os.getenv("VESPER_RESOURCE_DIR")
    if env_root:
        yield Path(env_root).expanduser().resolve()

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            yield Path(meipass).resolve()

        executable = Path(sys.executable).resolve()
        yield executable.parent
        yield executable.parent.parent / "Resources"

    project_root = Path(__file__).resolve().parent.parent
    yield project_root


def find_frontend_dist() -> Path | None:
    """Locate the bundled frontend build output if it exists."""
    candidates: list[Path] = []
    for root in iter_resource_roots():
        candidates.extend(
            [
                root / "frontend" / "dist",
                root / "resources" / "frontend" / "dist",
                root / "frontend-dist",
            ]
        )

    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate

    return None
