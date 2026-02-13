from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UserConfig:
    library_root: str | None = None
    shared_drive_paths: list[str] = field(default_factory=list)
    index_root_paths: list[str] = field(default_factory=list)
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
    shared_drive_paths = data.get("shared_drive_paths")
    index_root_paths = data.get("index_root_paths")
    preset_tags = data.get("preset_tags")
    
    # 迁移逻辑：如果存在旧的 shared_drive_path，将其迁移到 list
    old_single_path = data.get("shared_drive_path")
    if shared_drive_paths is None:
        if old_single_path and isinstance(old_single_path, str):
            shared_drive_paths = [old_single_path]
        else:
            shared_drive_paths = []

    if library_root and not isinstance(library_root, str):
        library_root = None
    
    if index_root_paths is None:
        # 迁移：如果存在旧的 shared_drive_path 且 index_root_paths 为空，将其作为初始索引路径
        if old_single_path and isinstance(old_single_path, str):
             index_root_paths = [old_single_path]
        else:
             index_root_paths = []
            
    if preset_tags is None or not isinstance(preset_tags, list):
        preset_tags = [
            "#第一版", "#第二版", "#模具", "#铸件渣包流道", 
            "#产品", "#模流报告", "#压铸参数计算", "#压射参数"
        ]
        
    return UserConfig(
        library_root=library_root, 
        shared_drive_paths=shared_drive_paths,
        index_root_paths=index_root_paths,
        preset_tags=preset_tags
    )


def save_user_config(cfg: UserConfig) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "library_root": cfg.library_root,
        "shared_drive_paths": cfg.shared_drive_paths,
        "index_root_paths": cfg.index_root_paths,
        "preset_tags": cfg.preset_tags,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
