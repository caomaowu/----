from __future__ import annotations

import sqlite3
from pathlib import Path

from dcpm.infra.db import index_db
from dcpm.infra.fs.metadata import read_project_metadata, update_project_metadata


def _split_tags(text: str) -> list[str]:
    raw = (
        text.replace("，", ",")
        .replace("；", ";")
        .replace(";", ",")
        .replace("\n", ",")
        .replace("\r", ",")
        .replace("\t", ",")
    )
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        t = part.strip()
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _normalize_rel_path(rel_path: str) -> str:
    p = str(rel_path).strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.strip("/")


class TagService:
    def __init__(self, library_root: Path):
        self.db = index_db.open_index_db(library_root)

    def load_item_tags(self, project_dir: Path) -> dict[str, list[str]]:
        meta_path = Path(project_dir) / ".project.json"
        if not meta_path.exists():
            return {}
        p = read_project_metadata(meta_path)
        return dict(p.item_tags)

    def parse_tags_text(self, text: str) -> list[str]:
        return _split_tags(text)

    def set_item_tags(self, project_dir: Path, rel_path: str, tags: list[str]) -> dict[str, list[str]]:
        project_dir = Path(project_dir)
        meta_path = project_dir / ".project.json"
        p = read_project_metadata(meta_path)

        rel = _normalize_rel_path(rel_path)
        clean = [t.strip() for t in tags if str(t).strip()]

        next_map = dict(p.item_tags)
        if not rel:
            return next_map
        if clean:
            next_map[rel] = clean
        else:
            next_map.pop(rel, None)

        update_project_metadata(meta_path, item_tags=next_map)
        self._sync_index(project_dir, p.id, next_map)
        return next_map

    def move_item(self, project_dir: Path, old_rel: str, new_rel: str) -> dict[str, list[str]]:
        project_dir = Path(project_dir)
        meta_path = project_dir / ".project.json"
        p = read_project_metadata(meta_path)

        old_key = _normalize_rel_path(old_rel)
        new_key = _normalize_rel_path(new_rel)
        if not old_key or not new_key or old_key == new_key:
            return dict(p.item_tags)

        next_map: dict[str, list[str]] = {}
        prefix = old_key + "/"
        for k, v in p.item_tags.items():
            nk = k
            if k == old_key:
                nk = new_key
            elif k.startswith(prefix):
                nk = new_key + "/" + k[len(prefix) :]
            next_map[nk] = v

        update_project_metadata(meta_path, item_tags=next_map)
        self._sync_index(project_dir, p.id, next_map)
        return next_map

    def delete_item(self, project_dir: Path, rel_path: str, is_dir: bool) -> dict[str, list[str]]:
        project_dir = Path(project_dir)
        meta_path = project_dir / ".project.json"
        p = read_project_metadata(meta_path)

        key = _normalize_rel_path(rel_path)
        if not key:
            return dict(p.item_tags)

        next_map = dict(p.item_tags)
        if is_dir:
            prefix = key + "/"
            for k in list(next_map.keys()):
                if k == key or k.startswith(prefix):
                    next_map.pop(k, None)
        else:
            next_map.pop(key, None)

        update_project_metadata(meta_path, item_tags=next_map)
        self._sync_index(project_dir, p.id, next_map)
        return next_map

    def _sync_index(self, project_dir: Path, project_id: str, item_tags: dict[str, list[str]]) -> None:
        conn = index_db.connect(self.db)
        try:
            try:
                index_db.replace_project_item_tags(
                    conn,
                    project_id=project_id,
                    project_dir=str(Path(project_dir)),
                    item_tags=item_tags,
                    fts5_enabled=self.db.fts5_enabled,
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass
        finally:
            conn.close()
