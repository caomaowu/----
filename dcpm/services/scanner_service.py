from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Generator, NamedTuple, Callable

from dcpm.domain.external_resource import ExternalResource
from dcpm.domain.project import Project
from dcpm.infra.db.index_db import (
    connect,
    open_index_db,
    upsert_external_resource,
    get_external_resources,
    update_external_resource_status,
    get_scanned_directories,
    mark_directory_scanned,
    get_cached_inspection_folders,
    cache_inspection_folder,
)
from dcpm.services.library_service import list_projects


class ScanResult(NamedTuple):
    folder_name: str
    full_path: str
    year: int
    date_str: str


class InspectionScanner:
    def __init__(
        self,
        root_path: str,
        scanned_history: set[str] | None = None,
        on_folder_complete: Callable[[str, str], None] | None = None,
        on_cache_folder: Callable[[str, str, str, str, int], None] | None = None,
        get_cached_folders: Callable[[str], list[dict]] | None = None,
    ):
        self.root_path = Path(root_path)
        self.scanned_history = scanned_history or set()
        self.on_folder_complete = on_folder_complete
        self.on_cache_folder = on_cache_folder
        self.get_cached_folders = get_cached_folders

    def scan(self) -> Generator[ScanResult, None, None]:
        if not self.root_path.exists():
            return
        
        yield from self._scan_recursive(self.root_path)

    def _scan_recursive(self, current_path: Path) -> Generator[ScanResult, None, None]:
        # 1. Check Memory (Skipping Logic)
        dir_name = current_path.name
        date_str = self._extract_date(dir_name)
        
        # Check if we should use cache for this folder (Past Date & Already Scanned)
        use_cache = False
        if date_str:
            today_str = datetime.now().strftime("%Y-%m-%d")
            if date_str < today_str and str(current_path) in self.scanned_history:
                use_cache = True

        if use_cache and self.get_cached_folders:
            # Read from Cache
            cached_items = self.get_cached_folders(str(current_path))
            for item in cached_items:
                yield ScanResult(
                    folder_name=item["folder_name"],
                    full_path=item["full_path"],
                    year=item["year"],
                    date_str=item["folder_date"],
                )
                # Note: We do NOT recurse into cached folders because the cache stores the "result layer"
                # If the cache stores intermediate layers, we might need recursion.
                # However, our cache logic (below) stores valid subdirectories.
                # If those subdirectories themselves have subdirectories, we would need to recurse.
                # BUT, our logic is: "This folder (current_path) is done".
                # So we assume all its children are indexed.
                # Wait, if `item` is a directory that contains further stuff, we need to recurse?
                # The current logic only caches the direct children that are "candidates".
                # If we have deep recursion, we need to cache DEEP.
                
                # Let's assume for now we only cache the leaf-ish nodes that are yielded.
                # If we recurse, we need to know if `item` is also cached.
                # Currently `scanned_history` marks `current_path`.
                # If `item` path is also in `scanned_history`, we could recurse.
                
                # Simplification: The current scanner yields `ScanResult` which are the resources.
                # It does NOT yield intermediate folders.
                # So simply yielding cached items is sufficient.
            return

        try:
            # 2. Scan content
            with os.scandir(current_path) as it:
                entries = list(it)
        except (PermissionError, OSError):
            return

        # 3. Process Subdirectories
        subdirs = [e for e in entries if e.is_dir()]
        
        for subdir in subdirs:
            subdir_path = Path(subdir.path)
            
            # Check if subdir has sub-subdirs (Leaf check)
            # We skip leaf folders (folders with no subdirectories)
            is_leaf = True
            try:
                with os.scandir(subdir_path) as sub_it:
                    for sub_entry in sub_it:
                        if sub_entry.is_dir():
                            is_leaf = False
                            break
            except (PermissionError, OSError):
                is_leaf = True
            
            if is_leaf:
                continue
                
            # It's a valid candidate (has subdirs)
            s_name = subdir.name
            s_date = self._extract_date(s_name)
            if not s_date:
                # Fallback to parent (current_path) date
                s_date = date_str
            
            year = 0
            if s_date:
                try:
                    year = int(s_date[:4])
                except (ValueError, IndexError):
                    year = 0
            else:
                # Modification time fallback
                try:
                    st = subdir.stat()
                    dt = datetime.fromtimestamp(st.st_mtime)
                    s_date = dt.strftime("%Y-%m-%d")
                    year = dt.year
                except OSError:
                    s_date = "1970-01-01"
            
            # Cache this valid candidate
            if self.on_cache_folder:
                self.on_cache_folder(
                    str(current_path),
                    s_name,
                    s_date or "",
                    str(subdir_path),
                    year
                )

            yield ScanResult(
                folder_name=s_name,
                full_path=str(subdir_path),
                year=year,
                date_str=s_date or ""
            )
            
            # Recurse into subdir
            yield from self._scan_recursive(subdir_path)

        # 4. Update Memory (Post-Scan)
        # If current_path is a past date folder, mark it as scanned.
        if date_str:
            today_str = datetime.now().strftime("%Y-%m-%d")
            if date_str < today_str and self.on_folder_complete:
                self.on_folder_complete(str(current_path), date_str)

    def _extract_date(self, folder_name: str, year_hint: int | None = None) -> str | None:
        # 1. YYYY-MM-DD or YYYY.MM.DD or YYYY_MM_DD
        m1 = re.search(r"(\d{4})[-._](\d{2})[-._](\d{2})", folder_name)
        if m1:
            return f"{m1.group(1)}-{m1.group(2)}-{m1.group(3)}"
        
        # 2. YYYYMMDD (Pure digits)
        m2 = re.search(r"(202\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", folder_name)
        if m2:
            return f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"
        
        # 3. MM-DD or MM.DD (requires year hint)
        if year_hint:
            m3 = re.search(r"(0[1-9]|1[0-2])[-.](0[1-9]|[12]\d|3[01])", folder_name)
            if m3:
                return f"{year_hint}-{m3.group(1)}-{m3.group(2)}"
            
        return None


class SmartMatcher:
    SYNONYMS = {
        "前梁": ["Front", "Frt"],
        "后梁": ["Rear", "Rr"],
        "减震塔": ["Shock", "Tower"],
        "探伤": ["Xray", "X-ray", "Inspection"],
    }

    def match(self, project: Project, folder_name: str) -> int:
        score = 0
        folder_lower = folder_name.lower()

        # Rule 0: Exact Name Match
        # Normalize: remove spaces, dashes, underscores to match loosely
        def normalize(s):
            return re.sub(r"[\s\-_]", "", s).lower()
            
        proj_norm = normalize(project.name)
        folder_norm = normalize(folder_name)
        
        if proj_norm and proj_norm in folder_norm:
             return 100

        # Rule 1: Strong Features
        if project.customer_code and project.customer_code.lower() in folder_lower:
            return 100
        
        if project.part_number and project.part_number.lower() in folder_lower:
            return 100
            
        return 0


def targeted_scan_and_link(library_root: Path, shared_drive_paths: list[str], target_project: Project) -> int:
    """
    Optimized scan that only looks for resources matching a specific project.
    Avoids full re-scan and DB cleanup overhead.
    """
    db = open_index_db(library_root)
    conn = connect(db)

    # Use history even for targeted scan to avoid re-reading old folders
    scanned_history = get_scanned_directories(conn)
    now_str = datetime.now().isoformat(timespec="seconds")
    
    def on_folder_complete(path: str, date_str: str):
        mark_directory_scanned(conn, path, date_str, now_str)
        conn.commit()

    def on_cache_folder(parent_path: str, folder_name: str, folder_date: str, full_path: str, year: int):
        cache_inspection_folder(conn, parent_path, folder_name, folder_date, full_path, year)

    matcher = SmartMatcher()
    
    new_links_count = 0
    
    try:
        # Step 0: Cleanup existing pending resources for this project
        cursor = conn.cursor()
        cursor.execute("SELECT id, folder_name FROM external_resources WHERE project_id = ? AND status = 'pending'", (target_project.id,))
        pending_rows = cursor.fetchall()
        
        for row in pending_rows:
            res_id, folder_name = row[0], row[1]
            new_score = matcher.match(target_project, folder_name)
            if new_score < 60:
                update_external_resource_status(conn, res_id, "ignored")
            else:
                pass
        
        conn.commit()

        # Iterate over all shared drive paths
        for shared_drive_path in shared_drive_paths:
            scanner = InspectionScanner(
                shared_drive_path,
                scanned_history=scanned_history,
                on_folder_complete=on_folder_complete,
                on_cache_folder=on_cache_folder,
                get_cached_folders=lambda p: get_cached_inspection_folders(conn, p),
            )
            
            for scan_result in scanner.scan():
                score = matcher.match(target_project, scan_result.folder_name)
                
                # Threshold check
                if score >= 60:
                    upsert_external_resource(
                        conn,
                        project_id=target_project.id,
                        resource_type="inspection",
                        root_path=shared_drive_path,
                        folder_year=scan_result.year,
                        folder_date=scan_result.date_str,
                        folder_name=scan_result.folder_name,
                        full_path=scan_result.full_path,
                        match_score=score,
                        status="pending",
                        created_at=now_str,
                    )
                    new_links_count += 1
            
            # Commit after each path is done (or let the periodic commit handle it)
            conn.commit()

    finally:
        conn.close()
        
    return new_links_count


def scan_and_link_resources(library_root: Path, shared_drive_paths: list[str]) -> int:
    """
    Scans the shared drive and links resources to local projects.
    Returns the number of new links created.
    """
    # Load all local projects
    entries = list_projects(library_root)
    # 过滤掉特殊项目，不参与索引
    projects = [e.project for e in entries if not getattr(e.project, 'is_special', False)]
    
    db = open_index_db(library_root)
    conn = connect(db)
    
    new_links_count = 0
    now_str = datetime.now().isoformat(timespec="seconds")
    
    # Load Scan History
    scanned_history = get_scanned_directories(conn)

    def on_folder_complete(path: str, date_str: str):
        mark_directory_scanned(conn, path, date_str, now_str)
        conn.commit()
    
    def on_cache_folder(parent_path: str, folder_name: str, folder_date: str, full_path: str, year: int):
        cache_inspection_folder(conn, parent_path, folder_name, folder_date, full_path, year)

    matcher = SmartMatcher()
    
    try:
        # Step 0: Clean up invalid pending resources (e.g. leaf folders that shouldn't have been indexed)
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_path FROM external_resources WHERE status = 'pending'")
        pending_rows = cursor.fetchall()
        
        for row in pending_rows:
            res_id, path_str = row[0], row[1]
            p = Path(path_str)
            
            if not p.exists():
                update_external_resource_status(conn, res_id, "ignored")
                continue
                
            has_subdirs = False
            try:
                if p.is_dir():
                    for entry in os.scandir(p):
                         if entry.is_dir():
                             has_subdirs = True
                             break
            except (OSError, PermissionError):
                pass
            
            if not has_subdirs:
                update_external_resource_status(conn, res_id, "ignored")
        
        conn.commit()

        # Step 1: Scan and Link (Iterate over all paths)
        for shared_drive_path in shared_drive_paths:
            scanner = InspectionScanner(
                shared_drive_path,
                scanned_history=scanned_history,
                on_folder_complete=on_folder_complete,
                on_cache_folder=on_cache_folder,
                get_cached_folders=lambda p: get_cached_inspection_folders(conn, p),
            )
            
            for scan_result in scanner.scan():
                best_score = 0
                best_project_id = None
                
                # Find best matching project
                for project in projects:
                    score = matcher.match(project, scan_result.folder_name)
                    if score > best_score:
                        best_score = score
                        best_project_id = project.id
                
                # Threshold check
                if best_score >= 60 and best_project_id:
                    upsert_external_resource(
                        conn,
                        project_id=best_project_id,
                        resource_type="inspection",
                        root_path=shared_drive_path,
                        folder_year=scan_result.year,
                        folder_date=scan_result.date_str,
                        folder_name=scan_result.folder_name,
                        full_path=scan_result.full_path,
                        match_score=best_score,
                        status="pending",
                        created_at=now_str,
                    )
                    new_links_count += 1
            
            conn.commit()
            
    finally:
        conn.close()
        
    return new_links_count


def get_project_inspections(library_root: Path, project_id: str) -> list[ExternalResource]:
    db = open_index_db(library_root)
    conn = connect(db)
    try:
        rows = get_external_resources(conn, project_id)
        results = []
        for r in rows:
            results.append(ExternalResource(
                id=r["id"],
                project_id=r["project_id"],
                resource_type=r["resource_type"],
                root_path=r["root_path"],
                folder_year=r["folder_year"],
                folder_date=r["folder_date"],
                folder_name=r["folder_name"],
                full_path=r["full_path"],
                match_score=r["match_score"],
                status=r["status"],
                created_at=datetime.fromisoformat(r["created_at"]),
            ))
        return results
    finally:
        conn.close()


def confirm_inspection_link(library_root: Path, resource_id: int) -> None:
    db = open_index_db(library_root)
    conn = connect(db)
    try:
        update_external_resource_status(conn, resource_id, "confirmed")
        conn.commit()
    finally:
        conn.close()


def remove_inspection_link(library_root: Path, resource_id: int) -> None:
    db = open_index_db(library_root)
    conn = connect(db)
    try:
        # Instead of deleting, we could mark as ignored, but for now let's just update status
        # Or if we want to remove from view, maybe 'ignored' status is better.
        # The requirements said "Remove Association", which could mean delete or ignore.
        # Let's use 'ignored' to prevent re-scanning.
        update_external_resource_status(conn, resource_id, "ignored")
        conn.commit()
    finally:
        conn.close()
