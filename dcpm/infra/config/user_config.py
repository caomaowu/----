from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UserConfig:
    library_root: str | None = None


def _config_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "dcpm"


def _config_path() -> Path:
    return _config_dir() / "config.json"


def load_user_config() -> UserConfig:
    path = _config_path()
    if not path.exists():
        return UserConfig()

    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    library_root = data.get("library_root")
    if not isinstance(library_root, str) or not library_root.strip():
        return UserConfig()
    return UserConfig(library_root=library_root)


def save_user_config(cfg: UserConfig) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"library_root": cfg.library_root}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

