from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Generator, NamedTuple

from dcpm.domain.project import Project
from dcpm.domain.shared_drive_file import SharedDriveFolder, FolderStatus
from dcpm.infra.db.index_db import (
    connect,
    open_index_db,
    upsert_shared_drive_folder,
    get_shared_drive_folders,
    update_shared_drive_folder_status,
    delete_shared_drive_folder,
    get_shared_drive_folder_stats,
    clear_shared_drive_folders_by_root,
)
from dcpm.services.library_service import list_projects


class ScanFolderResult(NamedTuple):
    """扫描到的文件夹结果"""
    folder_path: str       # 相对根目录的路径
    folder_name: str
    file_count: int        # 文件夹内文件数量
    total_size: int        # 文件夹总大小
    modified_time: datetime


class SharedDriveScanner:
    """共享盘文件夹扫描器"""
    
    # 常用工程文件扩展名（用于判断文件夹是否包含工程文件）
    ENGINEERING_EXTENSIONS = {
        '.stp', '.step', '.igs', '.iges', '.stl', '.obj',
        '.dwg', '.dxf', '.pdf', '.doc', '.docx', '.xls', '.xlsx',
        '.ppt', '.pptx', '.jpg', '.jpeg', '.png', '.tif', '.tiff',
        '.zip', '.rar', '.7z', '.txt', '.csv', '.xml', '.json',
    }
    
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
    
    def _get_folder_info(self, folder_path: Path) -> tuple[int, int, datetime]:
        """
        获取文件夹的信息：文件数量、总大小、最后修改时间
        
        Returns:
            (文件数量, 总大小, 最后修改时间)
        """
        file_count = 0
        total_size = 0
        latest_mtime = 0
        
        try:
            for root, dirs, files in os.walk(folder_path):
                # 跳过隐藏文件夹
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for file_name in files:
                    if file_name.startswith('.'):
                        continue
                    
                    file_path = Path(root) / file_name
                    try:
                        stat = file_path.stat()
                        file_count += 1
                        total_size += stat.st_size
                        latest_mtime = max(latest_mtime, stat.st_mtime)
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            pass
        
        mtime = datetime.fromtimestamp(latest_mtime) if latest_mtime > 0 else datetime.now()
        return file_count, total_size, mtime
    
    def scan(
        self,
        min_file_count: int = 1,  # 最少文件数量，过滤空文件夹
    ) -> Generator[ScanFolderResult, None, None]:
        """
        扫描共享盘中的项目文件夹
        
        Args:
            min_file_count: 文件夹内最少文件数量，用于过滤空文件夹或无效文件夹
        """
        if not self.root_path.exists():
            return
        
        # 只扫描第一层目录作为项目文件夹
        try:
            for item in self.root_path.iterdir():
                if not item.is_dir():
                    continue
                
                folder_name = item.name
                # 跳过隐藏文件夹和系统文件夹
                if folder_name.startswith('.') or folder_name in {'System Volume Information', '$RECYCLE.BIN'}:
                    continue
                
                # 获取文件夹信息
                file_count, total_size, modified_time = self._get_folder_info(item)
                
                # 过滤空文件夹
                if file_count < min_file_count:
                    continue
                
                # 计算相对路径
                rel_path = item.relative_to(self.root_path).as_posix()
                
                yield ScanFolderResult(
                    folder_path=rel_path,
                    folder_name=folder_name,
                    file_count=file_count,
                    total_size=total_size,
                    modified_time=modified_time,
                )
                
        except (OSError, PermissionError):
            return


class FolderMatcher:
    """文件夹与项目的智能匹配器"""
    
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
    
    def match(self, folder_name: str) -> int:
        """
        计算文件夹名称与项目的匹配分数
        
        Returns:
            0-100 的匹配分数
        """
        if not self.keywords:
            return 0
        
        folder_lower = folder_name.lower()
        
        score = 0
        matched_keywords = 0
        
        for keyword in self.keywords:
            # 完整匹配文件夹名得分高
            if keyword in folder_lower:
                score += 40
                matched_keywords += 1
        
        # 根据匹配的关键词比例加分
        if self.keywords:
            coverage = matched_keywords / len(self.keywords)
            score += int(coverage * 50)
        
        # 项目ID完全匹配额外加分
        if self.project.id and self.project.id.lower() in folder_lower:
            score += 30
        
        # 件号完全匹配额外加分
        if self.project.part_number and self.project.part_number.lower() in folder_lower:
            score += 35
        
        return min(100, score)


# 保持向后兼容
FileMatcher = FolderMatcher


class SharedDriveService:
    """共享盘文件夹索引服务"""
    
    def __init__(self, library_root: Path):
        self.library_root = library_root
    
    def scan_and_index(
        self,
        shared_drive_path: str,
        target_project: Project | None = None,
        min_match_score: int = 30,  # 最小匹配分数
    ) -> int:
        """
        扫描共享盘并建立文件夹索引
        
        Args:
            shared_drive_path: 共享盘根路径
            target_project: 如果指定，只索引匹配该项目的文件夹；否则索引所有项目
            min_match_score: 最小匹配分数，低于此值的文件夹不会被索引
            
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
                # 单项目模式：只为指定项目索引匹配的文件夹
                matcher = FolderMatcher(target_project)
                
                for scan_result in scanner.scan():
                    score = matcher.match(scan_result.folder_name)
                    
                    # 只索引匹配度 >= min_match_score 的文件夹
                    if score >= min_match_score:
                        upsert_shared_drive_folder(
                            conn,
                            project_id=target_project.id,
                            root_path=shared_drive_path,
                            folder_path=scan_result.folder_path,
                            folder_name=scan_result.folder_name,
                            file_count=scan_result.file_count,
                            total_size=scan_result.total_size,
                            modified_time=scan_result.modified_time.isoformat(),
                            status="indexed",
                            match_score=score,
                            created_at=now_str,
                        )
                        indexed_count += 1
            else:
                # 全库模式：为所有项目索引文件夹
                entries = list_projects(self.library_root)
                projects = [e.project for e in entries]
                matchers = {p.id: FolderMatcher(p) for p in projects}
                
                for scan_result in scanner.scan():
                    best_score = 0
                    best_project_id = None
                    
                    # 找到最匹配的项目
                    for project in projects:
                        score = matchers[project.id].match(scan_result.folder_name)
                        if score > best_score:
                            best_score = score
                            best_project_id = project.id
                    
                    # 只索引匹配度 >= min_match_score 的文件夹
                    if best_score >= min_match_score and best_project_id:
                        upsert_shared_drive_folder(
                            conn,
                            project_id=best_project_id,
                            root_path=shared_drive_path,
                            folder_path=scan_result.folder_path,
                            folder_name=scan_result.folder_name,
                            file_count=scan_result.file_count,
                            total_size=scan_result.total_size,
                            modified_time=scan_result.modified_time.isoformat(),
                            status="indexed",
                            match_score=best_score,
                            created_at=now_str,
                        )
                        indexed_count += 1
            
            conn.commit()
        finally:
            conn.close()
        
        return indexed_count
    
    def get_project_folders(
        self,
        project_id: str,
        status: str | None = None,
    ) -> list[SharedDriveFolder]:
        """获取项目的共享盘文件夹列表"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        
        try:
            rows = get_shared_drive_folders(conn, project_id, status)
            return [
                SharedDriveFolder(
                    id=r["id"],
                    project_id=r["project_id"],
                    root_path=r["root_path"],
                    folder_path=r["folder_path"],
                    folder_name=r["folder_name"],
                    file_count=r["file_count"],
                    total_size=r["total_size"],
                    modified_time=datetime.fromisoformat(r["modified_time"]),
                    status=FolderStatus(r["status"]),
                    match_score=r["match_score"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                )
                for r in rows
            ]
        finally:
            conn.close()
    
    # 保持向后兼容的方法名
    get_project_files = get_project_folders
    
    def confirm_folder(self, folder_id: int) -> None:
        """确认文件夹关联"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            update_shared_drive_folder_status(conn, folder_id, FolderStatus.CONFIRMED.value)
            conn.commit()
        finally:
            conn.close()
    
    confirm_file = confirm_folder
    
    def unconfirm_folder(self, folder_id: int) -> None:
        """取消确认文件夹关联"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            update_shared_drive_folder_status(conn, folder_id, FolderStatus.INDEXED.value)
            conn.commit()
        finally:
            conn.close()
    
    def ignore_folder(self, folder_id: int) -> None:
        """忽略文件夹"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            update_shared_drive_folder_status(conn, folder_id, FolderStatus.IGNORED.value)
            conn.commit()
        finally:
            conn.close()
    
    ignore_file = ignore_folder
    
    def delete_folder_index(self, folder_id: int) -> None:
        """删除文件夹索引"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            delete_shared_drive_folder(conn, folder_id)
            conn.commit()
        finally:
            conn.close()
    
    delete_file_index = delete_folder_index
    
    def get_stats(self, project_id: str) -> dict[str, int]:
        """获取项目共享盘文件夹统计"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            return get_shared_drive_folder_stats(conn, project_id)
        finally:
            conn.close()
    
    def get_file_types(self, project_id: str) -> list[str]:
        """获取项目的文件类型列表（文件夹模式下返回空列表）"""
        return []
    
    def clear_index(self, root_path: str) -> None:
        """清除指定根路径的索引"""
        db = open_index_db(self.library_root)
        conn = connect(db)
        try:
            clear_shared_drive_folders_by_root(conn, root_path)
            conn.commit()
        finally:
            conn.close()


def quick_scan_project(
    library_root: Path,
    shared_drive_path: str,
    project: Project,
) -> int:
    """
    快速扫描并索引单个项目的共享盘文件夹
    
    这是一个便捷函数，用于在项目中快速建立共享盘索引
    """
    service = SharedDriveService(library_root)
    return service.scan_and_index(shared_drive_path, target_project=project)
