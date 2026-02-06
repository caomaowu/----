from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class IndexDb:
    path: Path
    fts5_enabled: bool


def open_index_db(library_root: Path) -> IndexDb:
    root = Path(library_root)
    pm_dir = root / ".pm_system"
    pm_dir.mkdir(parents=True, exist_ok=True)
    (pm_dir / "cache").mkdir(parents=True, exist_ok=True)
    db_path = pm_dir / "index.sqlite"

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        _ensure_schema(conn)
        fts5_enabled = _try_enable_fts5(conn)
        conn.execute("PRAGMA user_version=2;")
        conn.commit()
    finally:
        conn.close()

    return IndexDb(path=db_path, fts5_enabled=fts5_enabled)


def connect(db: IndexDb) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db.path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects(
            id TEXT PRIMARY KEY,
            customer TEXT NOT NULL,
            name TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            status TEXT NOT NULL,
            create_time TEXT NOT NULL,
            month TEXT NOT NULL,
            project_dir TEXT NOT NULL,
            description TEXT,
            part_number TEXT,
            pinned INTEGER NOT NULL DEFAULT 0,
            last_open_time TEXT,
            open_count INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files(
            project_id TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            PRIMARY KEY(project_id, rel_path),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_notes(
            file_path TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            create_time TEXT NOT NULL,
            update_time TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS item_tags(
            project_id TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            tag TEXT NOT NULL,
            is_dir INTEGER NOT NULL,
            PRIMARY KEY(project_id, rel_path, tag),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_project_id ON files(project_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_tags_project_id ON item_tags(project_id);")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS external_resources(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            root_path TEXT NOT NULL,
            folder_year INTEGER NOT NULL,
            folder_date TEXT NOT NULL,
            folder_name TEXT NOT NULL,
            full_path TEXT NOT NULL UNIQUE,
            match_score INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ext_res_project_id ON external_resources(project_id);")
    
    # 共享盘文件夹索引表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shared_drive_folders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            root_path TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            folder_name TEXT NOT NULL,
            file_count INTEGER NOT NULL DEFAULT 0,
            total_size INTEGER NOT NULL DEFAULT 0,
            modified_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'indexed',
            match_score INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(root_path, folder_path)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shared_folders_project_id ON shared_drive_folders(project_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shared_folders_status ON shared_drive_folders(status);")
    
    _ensure_project_columns(conn)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_part_number ON projects(part_number) WHERE part_number IS NOT NULL AND part_number != '';"
    )


def _ensure_project_columns(conn: sqlite3.Connection) -> None:
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(projects);").fetchall()}
    if "pinned" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;")
    if "last_open_time" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN last_open_time TEXT;")
    if "open_count" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN open_count INTEGER NOT NULL DEFAULT 0;")
    if "part_number" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN part_number TEXT;")


def _try_enable_fts5(conn: sqlite3.Connection) -> bool:
    try:
        # Check if project_fts table exists and has part_number column
        # PRAGMA table_info returns list of tuples (cid, name, type, notnull, dflt_value, pk)
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(project_fts);").fetchall()}
        
        # If table exists but part_number is missing, we must recreate it because FTS5 tables don't support ALTER TABLE properly
        if "project_fts" in {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}:
             if "part_number" not in cols:
                 conn.execute("DROP TABLE project_fts;")

        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS project_fts USING fts5(
                id UNINDEXED,
                customer,
                name,
                part_number,
                tags,
                dir_name,
                description,
                tokenize = 'unicode61'
            );
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS file_fts USING fts5(
                project_id UNINDEXED,
                rel_path,
                file_name,
                tokenize = 'unicode61'
            );
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS item_tag_fts USING fts5(
                project_id UNINDEXED,
                rel_path,
                tag,
                tokenize = 'unicode61'
            );
            """
        )
        return True
    except sqlite3.OperationalError:
        return False


def upsert_project(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    customer: str,
    name: str,
    tags: list[str],
    status: str,
    create_time: str,
    month: str,
    project_dir: str,
    description: str | None,
    part_number: str | None,
    fts5_enabled: bool,
) -> None:
    conn.execute(
        """
        INSERT INTO projects(id, customer, name, tags_json, status, create_time, month, project_dir, description, part_number)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            customer=excluded.customer,
            name=excluded.name,
            tags_json=excluded.tags_json,
            status=excluded.status,
            create_time=excluded.create_time,
            month=excluded.month,
            project_dir=excluded.project_dir,
            description=excluded.description,
            part_number=excluded.part_number;
        """,
        (project_id, customer, name, json.dumps(tags, ensure_ascii=False), status, create_time, month, project_dir, description, part_number),
    )

    if not fts5_enabled:
        return

    tags_text = " ".join(tags)
    dir_name = Path(project_dir).name
    conn.execute("DELETE FROM project_fts WHERE id = ?;", (project_id,))
    conn.execute(
        "INSERT INTO project_fts(id, customer, name, part_number, tags, dir_name, description) VALUES(?, ?, ?, ?, ?, ?, ?);",
        (project_id, customer, name, part_number or "", tags_text, dir_name, description or ""),
    )


def replace_project_files(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    files: Iterable[tuple[str, str]],
    fts5_enabled: bool,
) -> None:
    files_list = list(files)
    conn.execute("DELETE FROM files WHERE project_id = ?;", (project_id,))
    conn.executemany(
        "INSERT INTO files(project_id, rel_path, file_name) VALUES(?, ?, ?);",
        ((project_id, rel_path, file_name) for rel_path, file_name in files_list),
    )

    if not fts5_enabled:
        return

    conn.execute("DELETE FROM file_fts WHERE project_id = ?;", (project_id,))
    conn.executemany(
        "INSERT INTO file_fts(project_id, rel_path, file_name) VALUES(?, ?, ?);",
        ((project_id, rel_path, file_name) for rel_path, file_name in files_list),
    )


def replace_project_item_tags(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    project_dir: str,
    item_tags: dict[str, list[str]],
    fts5_enabled: bool,
) -> None:
    conn.execute("DELETE FROM item_tags WHERE project_id = ?;", (project_id,))
    rows: list[tuple[str, str, str, int]] = []
    base = Path(project_dir)
    for rel_path, tags in item_tags.items():
        rel = str(rel_path).strip().replace("\\", "/").strip("/")
        if not rel:
            continue
        is_dir = 1 if (base / rel).is_dir() else 0
        for t in tags:
            tag = str(t).strip()
            if not tag:
                continue
            rows.append((project_id, rel, tag, is_dir))

    if rows:
        conn.executemany(
            "INSERT INTO item_tags(project_id, rel_path, tag, is_dir) VALUES(?, ?, ?, ?);",
            rows,
        )

    if not fts5_enabled:
        return

    conn.execute("DELETE FROM item_tag_fts WHERE project_id = ?;", (project_id,))
    if rows:
        conn.executemany(
            "INSERT INTO item_tag_fts(project_id, rel_path, tag) VALUES(?, ?, ?);",
            ((pid, rel, tag) for pid, rel, tag, _ in rows),
        )


def set_project_pinned(conn: sqlite3.Connection, project_id: str, pinned: bool) -> None:
    conn.execute("UPDATE projects SET pinned = ? WHERE id = ?;", (1 if pinned else 0, project_id))


def mark_project_opened(conn: sqlite3.Connection, project_id: str, open_time: str) -> None:
    conn.execute(
        """
        UPDATE projects
        SET last_open_time = ?, open_count = open_count + 1
        WHERE id = ?;
        """,
        (open_time, project_id),
    )


def search_project_ids(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    fts5_enabled: bool,
    include_archived: bool = False,
) -> list[str]:
    q = query.strip()
    if not q:
        rows = conn.execute(
            """
            SELECT id
            FROM projects
            WHERE (? = 1) OR status != 'archived'
            ORDER BY
                pinned DESC,
                datetime(COALESCE(last_open_time, create_time)) DESC
            LIMIT ?;
            """,
            (1 if include_archived else 0, limit),
        ).fetchall()
        return [str(r["id"]) for r in rows]

    if fts5_enabled:
        rows = conn.execute(
            """
            WITH hits AS (
                SELECT id AS project_id, bm25(project_fts) AS score
                FROM project_fts
                WHERE project_fts MATCH ?
                UNION ALL
                SELECT project_id, bm25(file_fts) AS score
                FROM file_fts
                WHERE file_fts MATCH ?
                UNION ALL
                SELECT project_id, bm25(item_tag_fts) AS score
                FROM item_tag_fts
                WHERE item_tag_fts MATCH ?
            ),
            best AS (
                SELECT project_id, MIN(score) AS score
                FROM hits
                GROUP BY project_id
            )
            SELECT project_id
            FROM best
            JOIN projects p ON p.id = best.project_id
            WHERE (? = 1) OR p.status != 'archived'
            ORDER BY
                p.pinned DESC,
                best.score ASC,
                datetime(COALESCE(p.last_open_time, p.create_time)) DESC
            LIMIT ?;
            """,
            (_fts_query(q), _fts_query(q), _fts_query(q), 1 if include_archived else 0, limit),
        ).fetchall()
        return [str(r["project_id"]) for r in rows]

    like = f"%{q}%"
    rows = conn.execute(
        """
        SELECT p.id
        FROM projects p
        LEFT JOIN files f ON f.project_id = p.id
        LEFT JOIN item_tags it ON it.project_id = p.id
        WHERE
            ((? = 1) OR p.status != 'archived')
            AND (
            p.id LIKE ?
            OR p.customer LIKE ?
            OR p.name LIKE ?
            OR p.tags_json LIKE ?
            OR p.project_dir LIKE ?
            OR COALESCE(p.description, '') LIKE ?
            OR f.file_name LIKE ?
            OR f.rel_path LIKE ?
            OR it.tag LIKE ?
            OR it.rel_path LIKE ?
            )
        GROUP BY p.id
        ORDER BY
            p.pinned DESC,
            datetime(COALESCE(p.last_open_time, p.create_time)) DESC
        LIMIT ?;
        """,
        (1 if include_archived else 0, like, like, like, like, like, like, like, like, like, like, limit),
    ).fetchall()
    return [str(r["id"]) for r in rows]


def fetch_projects_by_ids(conn: sqlite3.Connection, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT * FROM projects WHERE id IN ({placeholders});",
        tuple(ids),
    ).fetchall()
    by_id = {str(r["id"]): dict(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def get_stats(conn: sqlite3.Connection) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'archived' THEN 1 ELSE 0 END) as archived,
            SUM(CASE WHEN strftime('%Y-%m', create_time) = strftime('%Y-%m', 'now') THEN 1 ELSE 0 END) as new_this_month
        FROM projects;
        """
    ).fetchone()
    return dict(row) if row else {"total": 0, "processing": 0, "completed": 0, "archived": 0, "new_this_month": 0}


def get_popular_tags(conn: sqlite3.Connection, limit: int) -> list[tuple[str, int]]:
    # Since tags are stored as JSON array string, we might need a recursive CTE or just simple parsing if possible.
    # SQLite's json_each is perfect for this.
    try:
        rows = conn.execute(
            """
            SELECT value as tag, COUNT(*) as count
            FROM projects, json_each(projects.tags_json)
            GROUP BY tag
            ORDER BY count DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()
        return [(str(r["tag"]), int(r["count"])) for r in rows]
    except sqlite3.OperationalError:
        # Fallback if JSON extension not available or some other issue
        return []


def get_month_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    rows = conn.execute(
        """
        SELECT month, COUNT(*) as count
        FROM projects
        GROUP BY month
        ORDER BY month DESC;
        """
    ).fetchall()
    return [(str(r["month"]), int(r["count"])) for r in rows]


def delete_project(conn: sqlite3.Connection, project_id: str) -> None:
    conn.execute("DELETE FROM projects WHERE id = ?;", (project_id,))
    conn.execute("DELETE FROM files WHERE project_id = ?;", (project_id,))
    # FTS tables are virtual, usually managed via triggers or manual delete if content=external.
    # But here we are using standard FTS5, so we should delete from it too.
    # Assuming 'projects_fts' is the FTS table name.
    # However, if 'projects_fts' is contentless or external, syntax differs.
    # Looking at create_tables (not shown but assumed), let's assume standard delete works or triggers handle it.
    # If using 'content' option, we need to delete from FTS table explicitly if triggers aren't set.
    # For safety, let's just delete from main table. If FTS is set up with triggers (common), it will update.
    # If not, we might leave ghosts. But 'rebuild_index' can fix it.
    # Let's try explicit delete from FTS just in case it's decoupled.
    try:
        conn.execute("DELETE FROM project_fts WHERE id = ?;", (project_id,))
        conn.execute("DELETE FROM file_fts WHERE project_id = ?;", (project_id,))
        conn.execute("DELETE FROM item_tag_fts WHERE project_id = ?;", (project_id,))
    except sqlite3.OperationalError:
        pass # Table might not exist or other config
    conn.commit()


def get_recent_activity_raw(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, name, customer, status, last_open_time, create_time
        FROM projects
        ORDER BY datetime(COALESCE(last_open_time, create_time)) DESC
        LIMIT ?;
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _fts_query(q: str) -> str:
    tokens = []
    for raw in q.replace("'", " ").replace('"', " ").split():
        t = raw.strip()
        if not t:
            continue
        tokens.append(f'"{t}"*')
    return " AND ".join(tokens) if tokens else q


def upsert_external_resource(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    resource_type: str,
    root_path: str,
    folder_year: int,
    folder_date: str,
    folder_name: str,
    full_path: str,
    match_score: int,
    status: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO external_resources(
            project_id, resource_type, root_path, folder_year, folder_date,
            folder_name, full_path, match_score, status, created_at
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(full_path) DO UPDATE SET
            project_id=excluded.project_id,
            match_score=excluded.match_score,
            status=excluded.status;
        """,
        (
            project_id, resource_type, root_path, folder_year, folder_date,
            folder_name, full_path, match_score, status, created_at
        ),
    )


def get_external_resources(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM external_resources
        WHERE project_id = ?
        ORDER BY folder_date DESC;
        """,
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_external_resource_status(conn: sqlite3.Connection, resource_id: int, status: str) -> None:
    conn.execute(
        "UPDATE external_resources SET status = ? WHERE id = ?;",
        (status, resource_id),
    )


def delete_external_resource(conn: sqlite3.Connection, resource_id: int) -> None:
    conn.execute("DELETE FROM external_resources WHERE id = ?;", (resource_id,))


def check_part_number_unique(conn: sqlite3.Connection, part_number: str, exclude_id: str | None = None) -> bool:
    """Check if a part number is unique. Returns True if unique (or empty), False if duplicate."""
    pn = part_number.strip()
    if not pn:
        return True

    if exclude_id:
        count = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE part_number = ? AND id != ?;", (pn, exclude_id)
        ).fetchone()[0]
    else:
        count = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE part_number = ?;", (pn,)
        ).fetchone()[0]

    return count == 0


# --- Shared Drive Folders ---

def upsert_shared_drive_folder(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    root_path: str,
    folder_path: str,
    folder_name: str,
    file_count: int,
    total_size: int,
    modified_time: str,
    status: str,
    match_score: int,
    created_at: str,
) -> None:
    """插入或更新共享盘文件夹索引"""
    conn.execute(
        """
        INSERT INTO shared_drive_folders(
            project_id, root_path, folder_path, folder_name, file_count,
            total_size, modified_time, status, match_score, created_at
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(root_path, folder_path) DO UPDATE SET
            project_id=excluded.project_id,
            file_count=excluded.file_count,
            total_size=excluded.total_size,
            modified_time=excluded.modified_time,
            status=excluded.status,
            match_score=excluded.match_score;
        """,
        (
            project_id, root_path, folder_path, folder_name, file_count,
            total_size, modified_time, status, match_score, created_at
        ),
    )


def get_shared_drive_folders(
    conn: sqlite3.Connection,
    project_id: str,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """获取项目的共享盘文件夹列表"""
    query = "SELECT * FROM shared_drive_folders WHERE project_id = ?"
    params: list[Any] = [project_id]
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    query += " ORDER BY modified_time DESC;"
    
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_shared_drive_folder_status(
    conn: sqlite3.Connection,
    folder_id: int,
    status: str,
) -> None:
    """更新共享盘文件夹状态"""
    conn.execute(
        "UPDATE shared_drive_folders SET status = ? WHERE id = ?;",
        (status, folder_id),
    )


def delete_shared_drive_folder(conn: sqlite3.Connection, folder_id: int) -> None:
    """删除共享盘文件夹索引"""
    conn.execute("DELETE FROM shared_drive_folders WHERE id = ?;", (folder_id,))


def clear_shared_drive_folders_by_root(conn: sqlite3.Connection, root_path: str) -> None:
    """清除指定根路径下的所有文件夹索引（用于重新扫描）"""
    conn.execute(
        "DELETE FROM shared_drive_folders WHERE root_path = ?;",
        (root_path,),
    )


def get_shared_drive_folder_stats(conn: sqlite3.Connection, project_id: str) -> dict[str, int]:
    """获取共享盘文件夹统计信息"""
    row = conn.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'indexed' THEN 1 ELSE 0 END) as indexed,
            SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) as confirmed,
            SUM(CASE WHEN status = 'ignored' THEN 1 ELSE 0 END) as ignored,
            SUM(total_size) as total_size
        FROM shared_drive_folders
        WHERE project_id = ?;
        """,
        (project_id,),
    ).fetchone()
    return {
        "total": row["total"] or 0,
        "indexed": row["indexed"] or 0,
        "confirmed": row["confirmed"] or 0,
        "ignored": row["ignored"] or 0,
        "total_size": row["total_size"] or 0,
    }


# --- 向后兼容的别名 ---
upsert_shared_drive_file = upsert_shared_drive_folder
get_shared_drive_files = get_shared_drive_folders
update_shared_drive_file_status = update_shared_drive_folder_status
delete_shared_drive_file = delete_shared_drive_folder
clear_shared_drive_files_by_root = clear_shared_drive_folders_by_root
get_shared_drive_stats = get_shared_drive_folder_stats
get_shared_drive_file_types = lambda conn, project_id: []  # 文件夹模式下无文件类型

