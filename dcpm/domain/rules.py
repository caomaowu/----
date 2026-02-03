from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectId:
    year: int
    month: int
    seq: int

    def format(self) -> str:
        return f"PRJ-{self.year:04d}{self.month:02d}-{self.seq:03d}"


_MONTH_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")
_PROJECT_ID_RE = re.compile(r"^PRJ-(?P<year>\d{4})(?P<month>0[1-9]|1[0-2])-(?P<seq>\d{3})$")


def parse_month(value: str) -> tuple[int, int]:
    m = _MONTH_RE.match(value.strip())
    if not m:
        raise ValueError("月份格式应为 YYYY-MM")
    return int(m.group("year")), int(m.group("month"))


def sanitize_folder_component(value: str) -> str:
    text = value.strip()
    text = re.sub(r"[\\/:*?\"<>|]", "_", text)
    text = re.sub(r"\s+", " ", text)
    return text


def month_dir_from_project_id(project_id: str) -> str:
    m = _PROJECT_ID_RE.match(project_id.strip())
    if not m:
        raise ValueError("项目编号格式应为 PRJ-YYYYMM-NNN")
    return f"{m.group('year')}-{m.group('month')}"
