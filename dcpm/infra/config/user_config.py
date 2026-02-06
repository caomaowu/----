from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UserConfig:
    library_root: str | None = None
    shared_drive_path: str | None = None
    preset_tags: list[str] = field(default_factory=lambda: [
        "#第一版", "#第二版", "#模具", "#铸件渣包流道", 
        "#产品", "#模流报告", "#压铸参数计算", "#压射参数"
    ])


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
    shared_drive_path = data.get("shared_drive_path")
    preset_tags = data.get("preset_tags")
    
    if library_root and not isinstance(library_root, str):
        library_root = None
    if shared_drive_path and not isinstance(shared_drive_path, str):
        shared_drive_path = None
    if preset_tags is None or not isinstance(preset_tags, list):
        preset_tags = [
            "#第一版", "#第二版", "#模具", "#铸件渣包流道", 
            "#产品", "#模流报告", "#压铸参数计算", "#压射参数"
        ]
        
    return UserConfig(
        library_root=library_root, 
        shared_drive_path=shared_drive_path,
        preset_tags=preset_tags
    )


def save_user_config(cfg: UserConfig) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "library_root": cfg.library_root,
        "shared_drive_path": cfg.shared_drive_path,
        "preset_tags": cfg.preset_tags,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
