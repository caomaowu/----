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

            # Level 2: Batch/Month
            for batch_entry in os.scandir(year_entry.path):
                if not batch_entry.is_dir():
                    continue

                # Level 3: Date (YYYY-MM-DD or MM-DD)
                # Matches: 2025-11-05, 2025.11.05, 11-05, 11.05
                for date_entry in os.scandir(batch_entry.path):
                    if not date_entry.is_dir():
                        continue
                    
                    date_str = self._extract_date(date_entry.name, year)
                    if not date_str:
                        continue

                    # Level 4: Target Folders (Inspection packages)
                    for target_entry in os.scandir(date_entry.path):
                        if not target_entry.is_dir():
                            continue
                        
                        yield ScanResult(
                            folder_name=target_entry.name,
                            full_path=target_entry.path,
                            year=year,
                            date_str=date_str,
                        )

    def _extract_date(self, folder_name: str, year: int) -> str | None:
        # Try full date: YYYY-MM-DD
        m1 = re.search(r"(\d{4})[-.](\d{2})[-.](\d{2})", folder_name)
        if m1:
            return f"{m1.group(1)}-{m1.group(2)}-{m1.group(3)}"
        
        # Try short date: MM-DD
        m2 = re.search(r"(\d{2})[-.](\d{2})", folder_name)
        if m2:
            return f"{year}-{m2.group(1)}-{m2.group(2)}"
            
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

        # Rule 1: Strong Features (50 pts)
        if project.customer_code and project.customer_code.lower() in folder_lower:
            score += 50
        
        if project.part_number and project.part_number.lower() in folder_lower:
            score += 50
            
        # Rule 2: Keywords (30 pts)
        # Split project name by common separators
        parts = re.split(r"[ _\-,]", project.name)
        for part in parts:
            if not part:
                continue
            if part.lower() in folder_lower:
                score += 30
                break # Count only once for name match

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
