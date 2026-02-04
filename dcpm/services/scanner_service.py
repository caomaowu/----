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

        # Level 1: Year (202\d)
        for year_entry in os.scandir(self.root_path):
            if not year_entry.is_dir():
                continue
            if not re.match(r"^202\d$", year_entry.name):
                continue
            
            try:
                year = int(year_entry.name)
            except ValueError:
                continue

            # Level 2: Recursively find potential resource folders
            # Strategy:
            # 1. Traverse down from Year folder
            # 2. Treat ANY folder as a potential target
            # 3. Infer date from folder name OR folder creation time
            
            for root, dirs, _ in os.walk(year_entry.path):
                # Avoid going too deep (optional optimization)
                # rel_depth = Path(root).relative_to(year_entry.path).parts
                # if len(rel_depth) > 3: continue
                
                for dir_name in dirs:
                    full_path = Path(root) / dir_name
                    
                    # Try to extract date from the folder name itself first
                    date_str = self._extract_date(dir_name, year)
                    
                    # If not in name, try to extract from parent folder name
                    if not date_str:
                        parent_name = Path(root).name
                        date_str = self._extract_date(parent_name, year)
                        
                    # If still no date, fallback to folder modification time
                    if not date_str:
                        try:
                            mtime = full_path.stat().st_mtime
                            dt = datetime.fromtimestamp(mtime)
                            if dt.year == year:
                                date_str = dt.strftime("%Y-%m-%d")
                            else:
                                # If mod time year doesn't match parent year folder, 
                                # we still use it but maybe flag it? For now just use it.
                                date_str = dt.strftime("%Y-%m-%d")
                        except OSError:
                            date_str = f"{year}-01-01" # Ultimate fallback

                    yield ScanResult(
                        folder_name=dir_name,
                        full_path=str(full_path),
                        year=year,
                        date_str=date_str,
                    )
                
                # We don't need to os.walk too deep if we treat every folder as a candidate
                # Actually, os.walk is good but might produce duplicates if we match parent AND child.
                # Let's simplify: We only care about "leaf" nodes or nodes that contain files?
                # No, a resource folder is just a folder.
                # Problem: If we have Year/Date/Package, we will yield "Date" as a package, and "Package" as a package.
                # "Date" folder (e.g. 2024-03-15) won't match any project name, so it's filtered out by Matcher (Score < 60).
                # "Package" folder (e.g. E07-HL) WILL match.
                # So it is safe to yield EVERYTHING.
                pass

    def _scan_targets(self, date_folder_path: str, year: int, date_str: str) -> Generator[ScanResult, None, None]:
        # Deprecated by the new recursive scan logic, but kept if needed or removed.
        # We replaced the logic in scan() directly.
        pass

    def _extract_date(self, folder_name: str, year: int) -> str | None:
        # 1. YYYY-MM-DD or YYYY.MM.DD or YYYY_MM_DD
        m1 = re.search(r"(\d{4})[-._](\d{2})[-._](\d{2})", folder_name)
        if m1:
            return f"{m1.group(1)}-{m1.group(2)}-{m1.group(3)}"
        
        # 2. YYYYMMDD (Pure digits, ensuring it looks like a date)
        m2 = re.search(r"(202\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", folder_name)
        if m2:
            return f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"
        
        # 3. MM-DD or MM.DD (using parent year)
        m3 = re.search(r"(0[1-9]|1[0-2])[-.](0[1-9]|[12]\d|3[01])", folder_name)
        if m3:
            return f"{year}-{m3.group(1)}-{m3.group(2)}"
            
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

        # Rule 0: Exact Name Match (New High Priority)
        # Normalize: remove spaces, dashes, underscores to match loosely
        # e.g. "Project-Name" matches "ProjectName_Inspection"
        def normalize(s):
            return re.sub(r"[\s\-_]", "", s).lower()
            
        proj_norm = normalize(project.name)
        folder_norm = normalize(folder_name)
        
        if proj_norm and proj_norm in folder_norm:
             score = 60 # Base passing score

        # Rule 1: Strong Features (50 pts)
        if project.customer_code and project.customer_code.lower() in folder_lower:
            score += 50
        
        if project.part_number and project.part_number.lower() in folder_lower:
            score += 50
            
        # Rule 2: Keywords Accumulation (Revised)
        # Split project name by common separators
        # Ignore common stop words
        STOP_WORDS = {"prj", "new", "old", "test", "2023", "2024", "2025", "project"}
        parts = re.split(r"[ _\-,]", project.name)
        
        keyword_score = 0
        matched_keywords = set()
        
        for part in parts:
            p = part.strip().lower()
            if not p or len(p) < 2 or p in STOP_WORDS:
                continue
            
            # Check if keyword matches folder name
            if p in folder_lower:
                # Avoid double counting same keyword
                if p not in matched_keywords:
                    keyword_score += 30
                    matched_keywords.add(p)
        
        score += keyword_score

        # Rule 3: Synonyms (20 pts)
        for key, values in self.SYNONYMS.items():
            if key in project.name:
                for val in values:
                    if val.lower() in folder_lower:
                        score += 20
                        break
        
        return min(score, 100)


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
