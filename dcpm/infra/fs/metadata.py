from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dcpm.domain.project import Project


def project_to_dict(p: Project) -> dict[str, Any]:
    data = asdict(p)
    data["create_time"] = p.create_time.isoformat(timespec="seconds")
    return data


def write_project_metadata(path: Path, p: Project) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project_to_dict(p), ensure_ascii=False, indent=2), encoding="utf-8")


def read_project_metadata(path: Path) -> Project:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    create_time = datetime.fromisoformat(str(data["create_time"]))
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    return Project(
        id=str(data["id"]),
        name=str(data["name"]),
        customer=str(data["customer"]),
        customer_code=data.get("customer_code"),
        part_number=data.get("part_number"),
        create_time=create_time,
        status=str(data.get("status") or "ongoing"),
        tags=[str(x) for x in tags],
        description=data.get("description"),
    )


def update_project_metadata(
    path: Path,
    *,
    tags: list[str] | None = None,
    status: str | None = None,
    description: str | None = None,
) -> Project:
    old = read_project_metadata(path)
    new = Project(
        id=old.id,
        name=old.name,
        customer=old.customer,
        customer_code=old.customer_code,
        part_number=old.part_number,
        create_time=old.create_time,
        status=status or old.status,
        tags=tags if tags is not None else old.tags,
        description=description if description is not None else old.description,
    )
    write_project_metadata(path, new)
    return new
