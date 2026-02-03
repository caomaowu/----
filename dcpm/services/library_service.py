from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dcpm.domain.project import Project
from dcpm.infra.fs.metadata import read_project_metadata


@dataclass(frozen=True)
class ProjectEntry:
    project: Project
    project_dir: Path
    pinned: bool = False
    last_open_time: datetime | None = None
    open_count: int = 0


_MONTH_DIR_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def list_projects(library_root: Path, include_archived: bool = False) -> list[ProjectEntry]:
    root = Path(library_root)
    if not root.exists() or not root.is_dir():
        return []

    entries: list[ProjectEntry] = []

    for month_dir in sorted(root.iterdir(), reverse=True):
        if not month_dir.is_dir():
            continue
        if month_dir.name == ".pm_system":
            continue
        if month_dir.name == "归档项目":
            continue
        if not _MONTH_DIR_RE.match(month_dir.name):
            continue

        for project_dir in sorted(month_dir.iterdir(), reverse=True):
            if not project_dir.is_dir():
                continue
            meta_path = project_dir / ".project.json"
            if not meta_path.exists():
                continue
            try:
                project = read_project_metadata(meta_path)
            except Exception:
                continue
            if (not include_archived) and project.status == "archived":
                continue
            entries.append(ProjectEntry(project=project, project_dir=project_dir))

    if include_archived:
        archived_root = root / "归档项目"
        if archived_root.exists() and archived_root.is_dir():
            for meta_path in archived_root.rglob(".project.json"):
                if not meta_path.is_file():
                    continue
                try:
                    project = read_project_metadata(meta_path)
                except Exception:
                    continue
                entries.append(ProjectEntry(project=project, project_dir=meta_path.parent))

    entries.sort(key=lambda x: x.project.create_time, reverse=True)
    return entries
