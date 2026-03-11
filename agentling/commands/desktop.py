"""CLI command to launch the VespeR native desktop shell on macOS."""

from __future__ import annotations

import argparse
import sys

from ..ui_server import create_ui_server


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Add the `desktop` subcommand parser."""
    parser = subparsers.add_parser(
        "desktop",
        help="Launch the native macOS desktop app",
        description="Run VespeR in a native macOS window instead of a browser",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the local API server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8420,
        help="Port to bind the local API server (default: 8420)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1440,
        help="Initial window width in pixels (default: 1440)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=960,
        help="Initial window height in pixels (default: 960)",
    )
    parser.add_argument(
        "--min-width",
        type=int,
        default=1100,
        help="Minimum window width in pixels (default: 1100)",
    )
    parser.add_argument(
        "--min-height",
        type=int,
        default=760,
        help="Minimum window height in pixels (default: 760)",
    )
    parser.add_argument(
        "--title",
        default="VespeR",
        help="Window title (default: VespeR)",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Use an external frontend dev server instead of bundled assets",
    )
    parser.add_argument(
        "--frontend-url",
        default="http://127.0.0.1:5173",
        help="Frontend URL to load in --dev mode (default: http://127.0.0.1:5173)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable pywebview debug mode",
    )
    return parser


def launch_desktop(args: argparse.Namespace) -> int:
    """Launch the native desktop shell."""
    if sys.platform != "darwin":
        print("Error: `vesper desktop` currently targets macOS. Use `vesper ui` on other platforms.")
        return 1

    try:
        import webview
    except ImportError:
        print("Error: pywebview is not installed. Run: pip install 'agentling[desktop]'")
        return 1

    try:
        server = create_ui_server(
            host=args.host,
            port=args.port,
            dev_mode=args.dev,
            log_level="warning" if not args.debug else "info",
            access_log=False,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}. Run: pip install uvicorn")
        return 1

    server.start_background()

    if not server.wait_until_ready():
        server.stop()
        print(f"Error: VespeR backend did not start on {server.url}")
        return 1

    target_url = args.frontend_url if args.dev else server.url

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║     🖥️  VespeR Desktop                                       ║
║                                                              ║
║     Window:  {target_url:<47}║
║     API:     {server.url + '/api':<47}║
║     WebSocket:{server.ws_url:<47}║
║                                                              ║
║     Close the window to stop                                 ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)

    try:
        webview.create_window(
            args.title,
            target_url,
            width=args.width,
            height=args.height,
            min_size=(args.min_width, args.min_height),
            resizable=True,
        )
        webview.start(debug=args.debug)
        return 0
    finally:
        server.stop()


def run_command(args: argparse.Namespace) -> int:
    """Execute the desktop command."""
    return launch_desktop(args)
