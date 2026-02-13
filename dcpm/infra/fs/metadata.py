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
    item_tags_raw = data.get("item_tags") or {}
    item_tags: dict[str, list[str]] = {}
    if isinstance(item_tags_raw, dict):
        for k, v in item_tags_raw.items():
            if not isinstance(k, str):
                continue
            if not isinstance(v, list):
                continue
            cleaned = [str(x).strip() for x in v if str(x).strip()]
            if cleaned:
                item_tags[k.strip().replace("\\", "/")] = cleaned
    cover_image = data.get("cover_image")
    if cover_image is not None:
        cover_image = str(cover_image).strip() or None
    return Project(
        id=str(data["id"]),
        name=str(data["name"]),
        customer=str(data["customer"]),
        customer_code=data.get("customer_code"),
        part_number=data.get("part_number"),
        create_time=create_time,
        status=str(data.get("status") or "ongoing"),
        tags=[str(x) for x in tags],
        item_tags=item_tags,
        description=data.get("description"),
        cover_image=cover_image,
        is_special=bool(data.get("is_special", False)),
    )


def update_project_metadata(
    path: Path,
    *,
    name: str | None = None,
    tags: list[str] | None = None,
    item_tags: dict[str, list[str]] | None = None,
    status: str | None = None,
    description: str | None = None,
    cover_image: str | None = None,
    part_number: str | None = None,
    is_special: bool | None = None,
) -> Project:
    old = read_project_metadata(path)
    cover_value = old.cover_image
    if cover_image is not None:
        cover_value = str(cover_image).strip() or None
    new = Project(
        id=old.id,
        name=name if name is not None else old.name,
        customer=old.customer,
        customer_code=old.customer_code,
        part_number=part_number if part_number is not None else old.part_number,
        create_time=old.create_time,
        status=status or old.status,
        tags=tags if tags is not None else old.tags,
        item_tags=item_tags if item_tags is not None else old.item_tags,
        description=description if description is not None else old.description,
        cover_image=cover_value,
        is_special=is_special if is_special is not None else old.is_special,
    )
    write_project_metadata(path, new)
    return new


def load_project(library_root: Path, project_id: str) -> Project | None:
    """
    通过项目 ID 加载项目对象。
    使用索引数据库查找项目物理路径，然后读取元数据。
    """
    from dcpm.infra.db.index_db import open_index_db, connect, fetch_projects_by_ids
    
    db = open_index_db(library_root)
    conn = connect(db)
    try:
        rows = fetch_projects_by_ids(conn, [project_id])
        if not rows:
            return None
        
        project_dir = Path(rows[0]["project_dir"])
        meta_path = project_dir / ".project.json"
        if not meta_path.exists():
            return None
            
        return read_project_metadata(meta_path)
    except Exception:
        return None
    finally:
        conn.close()
