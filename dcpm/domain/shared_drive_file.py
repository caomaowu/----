from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class FolderStatus(str, Enum):
    """共享盘文件夹状态"""
    INDEXED = "indexed"      # 已索引
    CONFIRMED = "confirmed"  # 已确认关联
    IGNORED = "ignored"      # 已忽略


@dataclass(frozen=True)
class SharedDriveFolder:
    """共享盘文件夹索引记录"""
    id: int | None
    project_id: str
    root_path: str           # 共享盘根目录路径
    folder_path: str         # 相对共享盘根目录的文件夹路径
    folder_name: str         # 文件夹名称
    file_count: int          # 文件夹内文件数量
    total_size: int          # 文件夹总大小（字节）
    modified_time: datetime  # 最后修改时间
    status: FolderStatus
    match_score: int         # 匹配分数（0-100）
    created_at: datetime
    
    @property
    def size_human(self) -> str:
        """返回人类可读的文件大小"""
        size = self.total_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    @property
    def file_count_display(self) -> str:
        """返回文件数量显示文本"""
        return f"{self.file_count} 个文件"


# 保持向后兼容的别名
FileStatus = FolderStatus
SharedDriveFile = SharedDriveFolder
