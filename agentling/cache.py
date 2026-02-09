from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ResultCache:
    def __init__(self, root: str = ".agentling-cache") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def get(self, key: str) -> str | None:
        target = self._path_for(key)
        if not target.exists():
            return None
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            return payload.get("output")
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, output: str) -> None:
        target = self._path_for(key)
        target.write_text(json.dumps({"output": output}, ensure_ascii=True), encoding="utf-8")
