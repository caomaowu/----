from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExternalResource:
    id: int | None
    project_id: str
    resource_type: str  # e.g., 'inspection'
    root_path: str
    folder_year: int
    folder_date: str
    folder_name: str
    full_path: str
    match_score: int
    status: str  # 'pending', 'confirmed', 'ignored'
    created_at: datetime
