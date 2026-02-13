from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from dcpm.infra.fs.metadata import read_project_metadata
from dcpm.infra.db.index_db import (
    IndexDb,
    connect,
    fetch_projects_by_ids,
    get_month_counts,
    get_popular_tags,
    get_recent_activity_raw,
    get_stats,
    mark_project_opened,
    open_index_db,
    replace_project_item_tags,
    replace_project_files,
    search_project_ids,
    set_project_pinned,
    upsert_project,
    delete_project,
)
from dcpm.services.library_service import ProjectEntry, list_projects


@dataclass(frozen=True)
class SearchResult:
    entries: list[ProjectEntry]
    fts5_enabled: bool


@dataclass(frozen=True)
class DashboardStats:
    total_projects: int
    processing_count: int
    completed_count: int
    new_this_month: int
    popular_tags: list[tuple[str, int]]
    month_counts: list[tuple[str, int]]


def delete_project_index(library_root: Path, project_id: str) -> None:
    db = open_index_db(library_root)
    conn = connect(db)
    try:
        delete_project(conn, project_id)
    finally:
        conn.close()


def get_dashboard_stats(library_root: Path) -> DashboardStats:
    db = open_index_db(library_root)
    conn = connect(db)
    try:
        stats = get_stats(conn)
        tags = get_popular_tags(conn, limit=10)
        months = get_month_counts(conn)
    finally:
        conn.close()

    return DashboardStats(
        total_projects=stats["total"],
        processing_count=stats["processing"],
        completed_count=stats["completed"],
        new_this_month=stats["new_this_month"],
        popular_tags=tags,
        month_counts=months,
    )


def get_recent_activity(library_root: Path, limit: int = 10) -> list[dict[str, str]]:
    db = open_index_db(library_root)
    conn = connect(db)
    try:
        raw = get_recent_activity_raw(conn, limit)
    finally:
        conn.close()

    result = []
    for r in raw:
        # Determine "action" based on last_open_time vs create_time
        # Simplified logic: if last_open_time is recent, say "Opened", else "Created"
        # For now, just return basic info
        result.append(
            {
                "id": str(r["id"]),
                "name": str(r["name"]),
                "customer": str(r["customer"]),
                "status": str(r["status"]),
                "time": str(r.get("last_open_time") or r["create_time"]),
            }
        )
    return result


def ensure_index(library_root: Path) -> IndexDb:
    return open_index_db(library_root)


def rebuild_index(
    library_root: Path, 
    include_archived: bool = False,
    progress_callback: callable | None = None,
) -> IndexDb:
    """
    重建索引
    
    Args:
        progress_callback: 可选的进度回调函数，接收 (当前项目数, 总项目数) 参数
    """
    db = open_index_db(library_root)
    entries = list_projects(Path(library_root), include_archived=include_archived)
    total = len(entries)

    conn = connect(db)
    try:
        for i, entry in enumerate(entries, 1):
            upsert_project(
                conn,
                project_id=entry.project.id,
                customer=entry.project.customer,
                name=entry.project.name,
                tags=entry.project.tags,
                status=entry.project.status,
                create_time=entry.project.create_time.isoformat(timespec="seconds"),
                month=entry.project.create_time.strftime("%Y-%m"),
                project_dir=str(entry.project_dir),
                description=entry.project.description,
                part_number=entry.project.part_number,
                fts5_enabled=db.fts5_enabled,
            )
            replace_project_files(
                conn,
                project_id=entry.project.id,
                files=_scan_files(entry.project_dir),
                fts5_enabled=db.fts5_enabled,
            )
            replace_project_item_tags(
                conn,
                project_id=entry.project.id,
                project_dir=str(entry.project_dir),
                item_tags=entry.project.item_tags,
                fts5_enabled=db.fts5_enabled,
            )
            # 每 10 个项目提交一次，避免长时间锁定
            if i % 10 == 0:
                conn.commit()
            if progress_callback:
                progress_callback(i, total)
        conn.commit()
    finally:
        conn.close()

    return db


def upsert_one_project(library_root: Path, entry: ProjectEntry) -> IndexDb:
    db = open_index_db(library_root)
    conn = connect(db)
    try:
        upsert_project(
            conn,
            project_id=entry.project.id,
            customer=entry.project.customer,
            name=entry.project.name,
            tags=entry.project.tags,
            status=entry.project.status,
            create_time=entry.project.create_time.isoformat(timespec="seconds"),
            month=entry.project.create_time.strftime("%Y-%m"),
            project_dir=str(entry.project_dir),
            description=entry.project.description,
            part_number=entry.project.part_number,
            fts5_enabled=db.fts5_enabled,
        )
        replace_project_files(
            conn,
            project_id=entry.project.id,
            files=_scan_files(entry.project_dir),
            fts5_enabled=db.fts5_enabled,
        )
        replace_project_item_tags(
            conn,
            project_id=entry.project.id,
            project_dir=str(entry.project_dir),
            item_tags=entry.project.item_tags,
            fts5_enabled=db.fts5_enabled,
        )
        conn.commit()
    finally:
        conn.close()
    return db


def toggle_pinned(library_root: Path, project_id: str, pinned: bool) -> None:
    db = open_index_db(library_root)
    conn = connect(db)
    try:
        set_project_pinned(conn, project_id, pinned)
        conn.commit()
    finally:
        conn.close()


def mark_opened_now(library_root: Path, project_id: str) -> None:
    db = open_index_db(library_root)
    conn = connect(db)
    try:
        mark_project_opened(conn, project_id, datetime.now().isoformat(timespec="seconds"))
        conn.commit()
    finally:
        conn.close()


def search(library_root: Path, query: str, limit: int = 200, include_archived: bool = False) -> SearchResult:
    db = open_index_db(library_root)
    conn = connect(db)
    try:
        ids = search_project_ids(conn, query, limit, db.fts5_enabled, include_archived=include_archived)
        rows = fetch_projects_by_ids(conn, ids)
        stale_ids: list[str] = []
        kept_rows: list[dict] = []
        for row in rows:
            project_dir = Path(str(row["project_dir"]))
            meta_path = project_dir / ".project.json"
            if (not project_dir.exists()) or (not meta_path.exists()):
                stale_ids.append(str(row["id"]))
                continue
            kept_rows.append(row)

        if stale_ids:
            for project_id in stale_ids:
                delete_project(conn, project_id)
            rows = kept_rows
    finally:
        conn.close()

    entries: list[ProjectEntry] = []
    for row in rows:
        try:
            tags = json.loads(row["tags_json"]) if row.get("tags_json") else []
            if not isinstance(tags, list):
                tags = []
        except Exception:
            tags = []
        try:
            create_time = datetime.fromisoformat(str(row["create_time"]))
        except Exception:
            create_time = datetime.now()

        last_open_time = None
        last_open_raw = row.get("last_open_time")
        if last_open_raw:
            try:
                last_open_time = datetime.fromisoformat(str(last_open_raw))
            except Exception:
                last_open_time = None
        project_dir = Path(str(row["project_dir"]))
        meta_path = project_dir / ".project.json"
        try:
            p = read_project_metadata(meta_path)
        except Exception:
            from dcpm.domain.project import Project

            p = Project(
                id=str(row["id"]),
                name=str(row["name"]),
                customer=str(row["customer"]),
                create_time=create_time,
                status=str(row["status"]),
                tags=[str(t) for t in tags],
                description=row.get("description"),
            )
        entries.append(
            ProjectEntry(
                project=p,
                project_dir=project_dir,
                pinned=bool(row.get("pinned") or 0),
                last_open_time=last_open_time,
                open_count=int(row.get("open_count") or 0),
            )
        )
    return SearchResult(entries=entries, fts5_enabled=db.fts5_enabled)


# 索引时跳过的目录（缓存、临时文件等）
_SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".svn", ".hg",
    ".venv", "venv", ".env", "env",
    "dist", "build", "target", ".idea", ".vscode",
    ".pytest_cache", ".mypy_cache", ".tox",
    ".pm_cover",  # 项目封面缓存
}


def _scan_files(project_dir: Path) -> Iterable[tuple[str, str]]:
    base = Path(project_dir)
    for path in base.rglob("*"):
        if path.is_dir():
            if path.name.startswith(".") or path.name in _SKIP_DIRS:
                continue
            continue
        if path.name.startswith("."):
            continue
        # 跳过位于缓存目录中的文件
        try:
            rel = path.relative_to(base)
            # 检查路径中是否包含需要跳过的目录
            if any(part in _SKIP_DIRS for part in rel.parts[:-1]):
                continue
            rel_str = rel.as_posix()
        except Exception:
            continue
        yield rel_str, path.name
