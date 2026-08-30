"""Atomic JSON state store backed by a directory checked out from the state branch."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from shared.json_utils import dumps


class StateStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or key.startswith(("/", "\\")) or ".." in Path(key).parts:
            raise ValueError("state key must be a safe relative path")
        path = (self.root / f"{key}.json").resolve()
        if self.root not in path.parents:
            raise ValueError("state key escapes the state root")
        return path

    def read(self, key: str, default: Any = None) -> Any:
        path = self._path(key)
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write(self, key: str, value: Any) -> bool:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered = dumps(value) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == rendered:
            return False
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return True
