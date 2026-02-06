from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class FileStatus(str, Enum):
    """共享盘文件状态"""
    INDEXED = "indexed"      # 已索引
    CONFIRMED = "confirmed"  # 已确认关联
    IGNORED = "ignored"      # 已忽略


@dataclass(frozen=True)
class SharedDriveFile:
    """共享盘文件索引记录"""
    id: int | None
    project_id: str
    file_path: str           # 相对共享盘根目录的路径
    file_name: str
    file_size: int           # 文件大小（字节）
    modified_time: datetime  # 修改时间
    file_hash: str | None    # 文件哈希（用于去重和增量更新）
    file_type: str           # 文件类型（扩展名）
    status: FileStatus
    match_score: int         # 匹配分数（0-100）
    created_at: datetime
    
    @property
    def size_human(self) -> str:
        """返回人类可读的文件大小"""
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
