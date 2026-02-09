"""CLI command to start the Agentling web UI."""

import argparse
import asyncio
import webbrowser
from pathlib import Path


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Add the 'ui' subcommand parser."""
    parser = subparsers.add_parser(
        "ui",
        help="Start the Agentling web UI",
        description="Launch the visual control plane for Claude Code"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8420,
        help="Port to bind (default: 8420)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't automatically open browser"
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Run in development mode (don't serve frontend)"
    )
    return parser


async def run_server(host: str, port: int, open_browser: bool, dev_mode: bool):
    """Run the web server."""
    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn not installed. Run: pip install uvicorn")
        return 1

    from ..web.app import create_app

    app = create_app(serve_frontend=not dev_mode)

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )
    server = uvicorn.Server(config)

    # Open browser after short delay
    if open_browser:
        async def open_browser_delayed():
            await asyncio.sleep(1.0)
            url = f"http://{host}:{port}"
            print(f"\n  Opening {url} in browser...\n")
            webbrowser.open(url)

        asyncio.create_task(open_browser_delayed())

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║     🚀 Agentling Visual UI                                   ║
║                                                              ║
║     Local:   http://{host}:{port:<5}                          ║
║     API:     http://{host}:{port}/api                        ║
║     WebSocket: ws://{host}:{port}/ws                         ║
║                                                              ║
║     Press Ctrl+C to stop                                     ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)

    await server.serve()
    return 0


def run_command(args: argparse.Namespace) -> int:
    """Execute the ui command."""
    return asyncio.run(
        run_server(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            dev_mode=args.dev
        )
    )
