"""Standalone entrypoint for the packaged VespeR macOS app."""

from __future__ import annotations

import argparse

from agentling.commands.desktop import launch_desktop


def main() -> int:
    return launch_desktop(
        argparse.Namespace(
            host="127.0.0.1",
            port=8420,
            width=1440,
            height=960,
            min_width=1100,
            min_height=760,
            title="VespeR",
            dev=False,
            frontend_url="http://127.0.0.1:5173",
            debug=False,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
