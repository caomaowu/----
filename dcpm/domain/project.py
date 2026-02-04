from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    customer: str
    create_time: datetime
    status: str = "ongoing"
    tags: list[str] = field(default_factory=list)
    item_tags: dict[str, list[str]] = field(default_factory=dict)
    customer_code: str | None = None
    part_number: str | None = None
    description: str | None = None
    cover_image: str | None = None
