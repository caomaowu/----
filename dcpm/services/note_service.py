from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from dcpm.infra.db import index_db


class NoteService:
    def __init__(self, library_root: Path):
        self.db = index_db.open_index_db(library_root)

    def get_note(self, file_path: Path | str) -> str | None:
        path_str = str(Path(file_path).resolve())
        conn = index_db.connect(self.db)
        try:
            row = conn.execute("SELECT content FROM file_notes WHERE file_path = ?;", (path_str,)).fetchone()
            return row["content"] if row else None
        finally:
            conn.close()

    def save_note(self, file_path: Path | str, content: str) -> None:
        path_str = str(Path(file_path).resolve())
        now_str = datetime.now().isoformat()
        
        conn = index_db.connect(self.db)
        try:
            if not content.strip():
                # If content is empty, delete the note
                conn.execute("DELETE FROM file_notes WHERE file_path = ?;", (path_str,))
            else:
                conn.execute(
                    """
                    INSERT INTO file_notes(file_path, content, create_time, update_time)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(file_path) DO UPDATE SET
                        content=excluded.content,
                        update_time=excluded.update_time;
                    """,
                    (path_str, content, now_str, now_str)
                )
            conn.commit()
        finally:
            conn.close()
