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
        "01_工程数据",
        "02_技术文档",
        "03_项目管理",
        "04_试模现场",
        "05_交付物",
        "06_其它",
    ]
    for rel in folders:
        (project_dir / rel).mkdir(parents=True, exist_ok=True)


def build_layout(root: Path, month: str, project_folder_name: str) -> ProjectLayout:
    month_dir = root / month
    project_dir = month_dir / project_folder_name
    metadata_path = project_dir / ".project.json"
    return ProjectLayout(month_dir=month_dir, project_dir=project_dir, metadata_path=metadata_path)

