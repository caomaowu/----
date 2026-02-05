from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Generator, NamedTuple

from dcpm.domain.external_resource import ExternalResource
from dcpm.domain.project import Project
from dcpm.infra.db.index_db import (
    connect,
    open_index_db,
    upsert_external_resource,
    get_external_resources,
    update_external_resource_status,
)
from dcpm.services.library_service import list_projects


class ScanResult(NamedTuple):
    folder_name: str
    full_path: str
    year: int
    date_str: str


class InspectionScanner:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def scan(self) -> Generator[ScanResult, None, None]:
        if not self.root_path.exists():
            return

        # Direct recursive scan from root, no top-level year assumption
        for root, dirs, _ in os.walk(self.root_path):
            # Optimize: Skip leaf folders (folders that contain no sub-folders)
            # This is based on the user request to "avoid scanning the last layer"
            # But wait, os.walk yields (root, dirs, files). 
            # If we are iterating 'dirs', we are looking at children of 'root'.
            # If a child 'dir_name' has no children of its own, it is a leaf (conceptually).
            # But os.walk goes top-down. We don't know if 'dir_name' has children until we walk into it.
            
            # Alternative interpretation: The user wants to scan folders that CONTAIN files, but not scan inside the folders that are just "containers of files" if they are the last layer?
            # Or maybe they mean: "If a folder has subfolders, it's a category (like Year/Month), NOT a resource package. If a folder has NO subfolders (only files), it IS a resource package."
            # Actually, "avoid scanning the last layer" usually means: "The resource is the PARENT of the files. Don't go deeper."
            
            # Let's refine the logic:
            # A "Resource Package" usually contains files (images, reports).
            # We want to yield folders that ARE the packages.
            # If a folder contains ONLY files and NO subdirectories, it is a Leaf Folder.
            # If the user says "avoid scanning the last layer", maybe they mean they don't want to match the sub-folders inside a resource package (e.g. "Report/Images").
            
            # Let's assume the standard structure: Year -> Project -> [Files] or [Images/Reports]
            # If we scan "Project", that's good.
            # If we scan "Images" inside "Project", that's bad (last layer).
            
            # So, we should only yield folders that we consider "Projects".
            # How to distinguish?
            # 1. Project folder usually has a date or specific naming.
            # 2. Project folder usually contains files directly OR contains specific subfolders.
            
            # Let's implement a check: If we are deep in the tree, checking if the CURRENT folder being yielded (dir_name) is a "leaf" is expensive without checking its content.
            # But os.walk allows us to see 'dirs' of the CURRENT 'root'.
            # If 'dirs' is empty, then 'root' is a leaf.
            # But we are iterating 'dirs' inside the loop.
            
            # Let's change strategy:
            # We only yield 'dir_name' if it satisfies our criteria.
            # New Criteria: A folder is a candidate ONLY if it has subdirectories? 
            # No, usually the resource folder IS the leaf (containing files).
            # Wait, "Avoid scanning last layer" -> "Don't scan the folder that is at the bottom".
            # If I have: Root -> A -> B -> [files]
            # Is B the resource? Or A?
            # Usually B is the resource (e.g. "Project-001").
            # If B contains a folder "img", then "img" is the last layer.
            # User might mean: "Don't scan 'img'".
            # So, if a folder is PURELY structural (only files, no meaning), maybe skip?
            # But 'img' folder has no subfolders.
            
            # Interpretation: "Skip folders that are leaves (have no subfolders)".
            # Let's try to verify if 'full_path' has subdirectories.
            # If it has subdirectories -> It might be a Year/Category folder OR a Project folder with subfolders.
            # If it has NO subdirectories -> It is a leaf. User says "avoid last layer". So skip leaves?
            # This seems counter-intuitive for "Resource Scanning" where the resource IS the leaf.
            
            # Re-reading: "avoid scanning the last layer" (避免扫最后一层的文件夹).
            # Context: Maybe the NAS has: ProjectA / [Report.pdf, Image.jpg]
            # And: ProjectA / SubFolder / [MoreFiles]
            # If we scan "SubFolder", it might match "ProjectA" partially or be garbage.
            # If we scan "ProjectA", it matches.
            
            # Let's implement: If a folder is a LEAF (no subdirs), DO NOT scan it?
            # Or: If a folder contains ONLY files, skip it?
            # Let's look at the `dirs` list in os.walk.
            # `dirs` contains the subdirectories of `root`.
            # If we are in `root`, we are iterating `dirs`.
            # For each `d` in `dirs`:
            #    We want to know if `d` is a leaf.
            #    We can check `os.listdir(d)` for directories.
            
            for dir_name in dirs:
                full_path = Path(root) / dir_name
                
                # Check if this folder has subdirectories
                # If it does NOT have subdirectories, it is a "last layer" folder.
                # User wants to AVOID scanning it?
                # Let's verify this assumption with a safe check.
                
                has_subdirs = False
                try:
                    # Quick check for at least one directory
                    with os.scandir(full_path) as it:
                        for entry in it:
                            if entry.is_dir():
                                has_subdirs = True
                                break
                except PermissionError:
                    continue # Skip if no permission
                
                # Logic: If it is a leaf (no subdirs), SKIP it.
                if not has_subdirs:
                    continue

                # ... existing logic ...
                
                # Try to extract date from folder name or parent
                # Without year context, we use a dummy year (e.g. current year) for _extract_date 
                # or modify _extract_date to handle missing year better.
                # However, let's just use 0 or None context if possible, but _extract_date expects int.
                # We will update _extract_date later or handle it here.
                # Actually, let's rely on modification time if name doesn't have full date.
                
                date_str = self._extract_date(dir_name)
                
                if not date_str:
                    parent_name = Path(root).name
                    date_str = self._extract_date(parent_name)
                    
                year = 0
                if not date_str:
                    try:
                        mtime = full_path.stat().st_mtime
                        dt = datetime.fromtimestamp(mtime)
                        date_str = dt.strftime("%Y-%m-%d")
                        year = dt.year
                    except OSError:
                        date_str = "1970-01-01"
                        year = 1970
                else:
                    # Try to parse year from date_str
                    try:
                        dt = datetime.strptime(date_str, "%Y-%m-%d")
                        year = dt.year
                    except ValueError:
                        year = 0 # Should not happen if regex matches

                yield ScanResult(
                    folder_name=dir_name,
                    full_path=str(full_path),
                    year=year,
                    date_str=date_str,
                )

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


def targeted_scan_and_link(library_root: Path, shared_drive_path: str, target_project: Project) -> int:
    """
    Optimized scan that only looks for resources matching a specific project.
    Avoids full re-scan and DB cleanup overhead.
    """
    scanner = InspectionScanner(shared_drive_path)
    matcher = SmartMatcher()
    
    db = open_index_db(library_root)
    conn = connect(db)
    
    new_links_count = 0
    now_str = datetime.now().isoformat(timespec="seconds")
    
    try:
        # We still need to iterate folders, but we only check match against ONE project.
        # This is O(N) where N is number of folders.
        # Previously it was O(N * M) where M is number of projects.
        
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
        
        conn.commit()
    finally:
        conn.close()
        
    return new_links_count


def scan_and_link_resources(library_root: Path, shared_drive_path: str) -> int:
    """
    Scans the shared drive and links resources to local projects.
    Returns the number of new links created.
    """
    scanner = InspectionScanner(shared_drive_path)
    matcher = SmartMatcher()
    
    # Load all local projects
    entries = list_projects(library_root)
    projects = [e.project for e in entries]
    
    db = open_index_db(library_root)
    conn = connect(db)
    
    new_links_count = 0
    now_str = datetime.now().isoformat(timespec="seconds")
    
    try:
        # Step 0: Clean up invalid pending resources (e.g. leaf folders that shouldn't have been indexed)
        # We fetch all 'pending' resources and check if they are valid under current rules.
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_path FROM external_resources WHERE status = 'pending'")
        pending_rows = cursor.fetchall()
        
        for row in pending_rows:
            res_id, path_str = row[0], row[1]
            p = Path(path_str)
            
            # Check validity:
            # 1. Path must exist
            # 2. Path must NOT be a leaf (must have subdirs)
            
            if not p.exists():
                # Path doesn't exist -> remove or ignore
                update_external_resource_status(conn, res_id, "ignored")
                continue
                
            has_subdirs = False
            try:
                # Use Path.iterdir() might be safer if scandir context manager fails weirdly? No, scandir is standard.
                # But let's debug if scandir is actually finding things.
                if p.is_dir():
                    for entry in os.scandir(p):
                         if entry.is_dir():
                             has_subdirs = True
                             break
            except (OSError, PermissionError):
                pass
            
            if not has_subdirs:
                # It is a leaf -> Invalid under new rules -> Ignore
                update_external_resource_status(conn, res_id, "ignored")
        
        # Commit cleanup changes immediately before scanning
        conn.commit()

        # Step 1: Scan and Link
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
