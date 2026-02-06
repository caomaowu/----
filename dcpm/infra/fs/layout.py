from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectLayout:
    month_dir: Path
    project_dir: Path
    metadata_path: Path


def ensure_pm_system(root: Path) -> Path:
    pm_dir = root / ".pm_system"
    pm_dir.mkdir(parents=True, exist_ok=True)
    (pm_dir / "cache").mkdir(parents=True, exist_ok=True)
    return pm_dir


def create_project_folders(project_dir: Path) -> None:
    folders = [
        "01_3D文件",
        "02_模流报告",
        "03_试模数据",
        "04_项目文件",
        "05_问题",
        "06_其它",
    ]
    for rel in folders:
        (project_dir / rel).mkdir(parents=True, exist_ok=True)


def build_layout(root: Path, month: str, project_folder_name: str) -> ProjectLayout:
    month_dir = root / month
    project_dir = month_dir / project_folder_name
    metadata_path = project_dir / ".project.json"
    return ProjectLayout(month_dir=month_dir, project_dir=project_dir, metadata_path=metadata_path)

