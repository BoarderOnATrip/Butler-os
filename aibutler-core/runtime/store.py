#!/usr/bin/env python3
"""
aiButler runtime store.

Simple local JSON / JSONL persistence for the open-source Butler runtime.
"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None


class RuntimeStore:
    """Filesystem-backed persistence for Butler runtime state."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir).expanduser()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, relative: str) -> Path:
        return self.base_dir / relative

    def _lock_path(self, relative: str) -> Path:
        path = self._path(relative)
        return path.parent / f"{path.name}.lock"

    @contextmanager
    def _locked(self, relative: str, *, exclusive: bool):
        lock_path = self._lock_path(relative)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(lock_file.fileno(), lock_type)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_json_unlocked(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return default
        return json.loads(raw)

    def _is_mergeable_dict_list(self, value: Any) -> bool:
        if not isinstance(value, list):
            return False
        if not value:
            return True
        return all(isinstance(item, dict) and "id" in item for item in value)

    def _merge_json_values(self, current: Any, incoming: Any) -> Any:
        if isinstance(current, dict) and isinstance(incoming, dict):
            merged = dict(current)
            for key, value in incoming.items():
                if key in merged:
                    merged[key] = self._merge_json_values(merged[key], value)
                else:
                    merged[key] = value
            return merged

        if self._is_mergeable_dict_list(current) and self._is_mergeable_dict_list(incoming):
            merged_by_id = {item["id"]: dict(item) for item in current}
            order = [item["id"] for item in current]
            for item in incoming:
                item_id = item["id"]
                if item_id not in merged_by_id:
                    order.append(item_id)
                merged_by_id[item_id] = self._merge_json_values(merged_by_id.get(item_id, {}), item)
            return [merged_by_id[item_id] for item_id in order]

        return incoming

    def _atomic_write_text(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
        return path

    def load_json(self, relative: str, default: Any) -> Any:
        path = self._path(relative)
        with self._locked(relative, exclusive=False):
            return self._read_json_unlocked(path, default)

    def save_json(self, relative: str, data: Any) -> Path:
        path = self._path(relative)
        with self._locked(relative, exclusive=True):
            current = self._read_json_unlocked(path, None)
            payload = self._merge_json_values(current, data) if current is not None else data
            text = json.dumps(payload, indent=2, default=str)
            return self._atomic_write_text(path, text)

    def append_jsonl(self, relative: str, data: Any) -> Path:
        path = self._path(relative)
        with self._locked(relative, exclusive=True):
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(data, default=str) + "\n"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            return path

    def load_jsonl(self, relative: str, limit: int | None = None) -> list[dict[str, Any]]:
        path = self._path(relative)
        with self._locked(relative, exclusive=False):
            if not path.exists():
                return []

            rows: list[dict[str, Any]] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rows.append(json.loads(line))

            if limit is not None:
                return rows[-limit:]
            return rows
