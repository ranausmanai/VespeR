"""Shared UI server lifecycle helpers for browser and desktop entrypoints."""

from __future__ import annotations

import asyncio
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(slots=True)
class UIServerHandle:
    """Owns a single FastAPI/uvicorn instance."""

    host: str
    port: int
    dev_mode: bool
    server: "uvicorn.Server"
    thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/ws"

    async def serve_forever(self) -> bool:
        return await self.server.serve()

    def start_background(self) -> None:
        """Start the server in a daemon thread for desktop hosting."""
        if self.thread and self.thread.is_alive():
            return

        self.thread = threading.Thread(
            target=self._serve_in_thread,
            name="agentling-ui-server",
            daemon=True,
        )
        self.thread.start()

    def wait_until_ready(self, timeout_s: float = 15.0) -> bool:
        """Poll the health endpoint until the server is reachable."""
        deadline = time.monotonic() + timeout_s
        health_url = f"{self.url}/api/health"

        while time.monotonic() < deadline:
            if self.thread and not self.thread.is_alive():
                return False

            try:
                with urllib.request.urlopen(health_url, timeout=1.0) as response:
                    if response.status == 200:
                        return True
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                pass

            time.sleep(0.2)

        return False

    def stop(self, timeout_s: float = 5.0) -> None:
        """Request server shutdown and wait briefly for the background thread."""
        self.server.should_exit = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=timeout_s)

    def _serve_in_thread(self) -> None:
        asyncio.run(self.server.serve())


def create_ui_server(
    host: str,
    port: int,
    dev_mode: bool = False,
    *,
    log_level: str = "info",
    access_log: bool = True,
) -> UIServerHandle:
    """Create a configured uvicorn server for the VespeR UI."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is not installed") from exc

    from .web.app import create_app

    app = create_app(serve_frontend=not dev_mode)
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=log_level,
        access_log=access_log,
    )

    return UIServerHandle(
        host=host,
        port=port,
        dev_mode=dev_mode,
        server=uvicorn.Server(config),
    )
