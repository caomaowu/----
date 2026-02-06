from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Generator, NamedTuple

from dcpm.domain.project import Project
from dcpm.domain.shared_drive_file import SharedDriveFile, FileStatus
from dcpm.infra.db.index_db import (
    connect,
    open_index_db,
    upsert_shared_drive_file,
    get_shared_drive_files,
    update_shared_drive_file_status,
    delete_shared_drive_file,
    get_shared_drive_stats,
    get_shared_drive_file_types,
    clear_shared_drive_files_by_root,
)
from dcpm.services.library_service import list_projects


class ScanFileResult(NamedTuple):
    """扫描到的文件结果"""
    file_path: str       # 相对根目录的路径
    file_name: str
    file_size: int
    modified_time: datetime
    file_type: str


class SharedDriveScanner:
    """共享盘文件扫描器"""
    
    # 常用工程文件扩展名
    ENGINEERING_EXTENSIONS = {
        '.stp', '.step', '.igs', '.iges', '.stl', '.obj',
        '.dwg', '.dxf', '.pdf', '.doc', '.docx', '.xls', '.xlsx',
        '.ppt', '.pptx', '.jpg', '.jpeg', '.png', '.tif', '.tiff',
        '.zip', '.rar', '.7z', '.txt', '.csv', '.xml', '.json',
    }
    
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
    
    def scan(
        self,
        extensions: set[str] | None = None,
        min_size: int = 0,
        max_size: int | None = None,
    ) -> Generator[ScanFileResult, None, None]:
        """
        扫描共享盘中的文件
        
        Args:
            extensions: 要扫描的文件扩展名集合，None 则扫描所有 ENGINEERING_EXTENSIONS
            min_size: 最小文件大小（字节）
            max_size: 最大文件大小（字节）
        """
        if not self.root_path.exists():
            return
        
        target_extensions = extensions or self.ENGINEERING_EXTENSIONS
        
        for root, dirs, files in os.walk(self.root_path):
            # 跳过隐藏文件夹和系统文件夹
            dirs[:] = [
                d for d in dirs
                if not d.startswith('.') and d not in {'System Volume Information', '$RECYCLE.BIN'}
            ]
            
            for file_name in files:
                # 跳过隐藏文件
                if file_name.startswith('.'):
                    continue
                
                file_path = Path(root) / file_name
                
                try:
                    stat = file_path.stat()
                    file_size = stat.st_size
                    
                    # 大小过滤
                    if file_size < min_size:
                        continue
                    if max_size is not None and file_size > max_size:
                        continue
                    
                    # 扩展名过滤
                    file_ext = file_path.suffix.lower()
                    if target_extensions and file_ext not in target_extensions:
                        continue
                    
                    # 计算相对路径
                    rel_path = file_path.relative_to(self.root_path).as_posix()
                    modified_time = datetime.fromtimestamp(stat.st_mtime)
                    
                    yield ScanFileResult(
                        file_path=rel_path,
                        file_name=file_name,
                        file_size=file_size,
                        modified_time=modified_time,
                        file_type=file_ext.lstrip('.').upper() if file_ext else 'UNKNOWN',
                    )
                    
                except (OSError, PermissionError):
                    continue


class FileMatcher:
    """文件与项目的智能匹配器"""
    
    def __init__(self, project: Project):
        self.project = project
        # 构建匹配关键词
        self.keywords = []
        if project.name:
            self.keywords.extend(self._extract_keywords(project.name))
        if project.customer:
            self.keywords.extend(self._extract_keywords(project.customer))
        if project.part_number:
            self.keywords.append(project.part_number.lower())
        # 项目ID中的数字部分
        if project.id:
            # 提取 PRJ-202403-001 中的 001
            match = re.search(r'-(\d+)$', project.id)
            if match:
                self.keywords.append(match.group(1))
    
    def _extract_keywords(self, text: str) -> list[str]:
        """从文本中提取关键词"""
        # 分割并过滤短词
        words = re.split(r'[\s\-_]', text.lower())
        return [w for w in words if len(w) >= 2]
    
    def match(self, file_name: str, folder_path: str) -> int:
        """
        计算文件与项目的匹配分数
        
        Returns:
            0-100 的匹配分数
        """
        if not self.keywords:
            return 0
        
        file_lower = file_name.lower()
        folder_lower = folder_path.lower()
        combined = f"{folder_lower}/{file_lower}"
        
        score = 0
        matched_keywords = 0
        
        for keyword in self.keywords:
            # 完整匹配文件名得分高
            if keyword in file_lower:
                score += 30
                matched_keywords += 1
            # 匹配文件夹路径
            elif keyword in folder_lower:
                score += 15
                matched_keywords += 1
        
        # 根据匹配的关键词比例加分
        if self.keywords:
            coverage = matched_keywords / len(self.keywords)
            score += int(coverage * 40)
        
        # 项目ID完全匹配额外加分
        if self.project.id and self.project.id.lower() in combined:
            score += 20
        
        # 件号完全匹配额外加分
        if self.project.part_number and self.project.part_number.lower() in combined:
            score += 25
        
        return min(100, score)


class SharedDriveService:
    """共享盘文件索引服务"""
    
    def __init__(self, library_root: Path):
        self.library_root = library_root
    
    def scan_and_index(
        self,
        shared_drive_path: str,
        target_project: Project | None = None,
        extensions: set[str] | None = None,
    ) -> int:
        """
        扫描共享盘并建立索引
        
        Args:
            shared_drive_path: 共享盘根路径
            target_project: 如果指定，只索引匹配该项目的文件；否则索引所有项目
            extensions: 要索引的文件扩展名
            
        Returns:
            新增/更新的索引数量
        """
        scanner = SharedDriveScanner(shared_drive_path)
        
        db = open_index_db(self.library_root)
        conn = connect(db)
        
        indexed_count = 0
        now_str = datetime.now().isoformat(timespec="seconds")
        
        try:
            if target_project:
                # 单项目模式：只为指定项目索引匹配的文件
                matcher = FileMatcher(target_project)
                
                for scan_result in scanner.scan(extensions=extensions):
                    score = matcher.match(scan_result.file_name, str(Path(scan_result.file_path).parent))
                    
                    # 只索引匹配度 >= 30 的文件
                    if score >= 30:
                        upsert_shared_drive_file(
                            conn,
                            project_id=target_project.id,
                            root_path=shared_drive_path,
                            file_path=scan_result.file_path,
                            file_name=scan_result.file_name,
                            file_size=scan_result.file_size,
                            modified_time=scan_result.modified_time.isoformat(),
                            file_hash=None,  # 可后续添加哈希计算
                            file_type=scan_result.file_type,
                            status="indexed",
                            match_score=score,
                            created_at=now_str,
                        )
                        indexed_count += 1
            else:
                # 全库模式：为所有项目索引文件
                entries = list_projects(self.library_root)
                projects = [e.project for e in entries]
                matchers = {p.id: FileMatcher(p) for p in projects}
                
                for scan_result in scanner.scan(extensions=extensions):
                    best_score = 0
                    best_project_id = None
                    
                    # 找到最匹配的项目
                    for project in projects:
                        score = matchers[project.id].match(
                            scan_result.file_name,
                            str(Path(scan_result.file_path).parent)
                        )
                        if score > best_score:
                            best_score = score
                            best_project_id = project.id
                    
                    # 只索引匹配度 >= 30 的文件
                    if best_score >= 30 and best_project_id:
                        upsert_shared_drive_file(
                            conn,
                            project_id=best_project_id,
                            root_path=shared_drive_path,
                            file_path=scan_result.file_path,
                            file_name=scan_result.file_name,
                            file_size=scan_result.file_size,
                            modified_time=scan_result.modified_time.isoformat(),
                            file_hash=None,
                            file_type=scan_result.file_type,
                            status="indexed",
                            match_score=best_score,
                            created_at=now_str,
                        )
                        indexed_count += 1
            
            conn.commit()
        finally:
            conn.close()
        
        return indexed_count
    
    def get_project_files(
        self,
        project_id: str,
        status: str | None = None,
        file_type: str | None = None,
    ) -> list[SharedDriveFile]:
        """获取项目的共享盘文件列表"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        
        try:
            rows = get_shared_drive_files(conn, project_id, status, file_type)
            return [
                SharedDriveFile(
                    id=r["id"],
                    project_id=r["project_id"],
                    file_path=r["file_path"],
                    file_name=r["file_name"],
                    file_size=r["file_size"],
                    modified_time=datetime.fromisoformat(r["modified_time"]),
                    file_hash=r["file_hash"],
                    file_type=r["file_type"],
                    status=FileStatus(r["status"]),
                    match_score=r["match_score"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                )
                for r in rows
            ]
        finally:
            conn.close()
    
    def confirm_file(self, file_id: int) -> None:
        """确认文件关联"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            update_shared_drive_file_status(conn, file_id, FileStatus.CONFIRMED.value)
            conn.commit()
        finally:
            conn.close()
    
    def ignore_file(self, file_id: int) -> None:
        """忽略文件"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            update_shared_drive_file_status(conn, file_id, FileStatus.IGNORED.value)
            conn.commit()
        finally:
            conn.close()
    
    def delete_file_index(self, file_id: int) -> None:
        """删除文件索引"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            delete_shared_drive_file(conn, file_id)
            conn.commit()
        finally:
            conn.close()
    
    def get_stats(self, project_id: str) -> dict[str, int]:
        """获取项目共享盘文件统计"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            return get_shared_drive_stats(conn, project_id)
        finally:
            conn.close()
    
    def get_file_types(self, project_id: str) -> list[str]:
        """获取项目的文件类型列表"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            return get_shared_drive_file_types(conn, project_id)
        finally:
            conn.close()
    
    def clear_index(self, root_path: str) -> None:
        """清除指定根路径的索引"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            clear_shared_drive_files_by_root(conn, root_path)
            conn.commit()
        finally:
            conn.close()


def quick_scan_project(
    library_root: Path,
    shared_drive_path: str,
    project: Project,
) -> int:
    """
    快速扫描并索引单个项目的共享盘文件
    
    这是一个便捷函数，用于在项目中快速建立共享盘索引
    """
    service = SharedDriveService(library_root)
    return service.scan_and_index(shared_drive_path, target_project=project)
