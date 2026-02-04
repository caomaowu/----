from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dcpm.domain.project import Project
from dcpm.domain.rules import ProjectId, month_dir_from_project_id, parse_month, sanitize_folder_component
from dcpm.infra.fs.layout import build_layout, create_project_folders, ensure_pm_system
from dcpm.infra.fs.metadata import read_project_metadata, update_project_metadata, write_project_metadata


@dataclass(frozen=True)
class CreateProjectRequest:
    month: str
    customer: str
    name: str
    tags: list[str]
    customer_code: str | None = None
    part_number: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class CreateProjectResult:
    project: Project
    project_dir: Path


_ID_RE = re.compile(r"^PRJ-(\d{6})-(\d{3})")


def _next_seq(month_dir: Path, year: int, month: int) -> int:
    prefix = f"PRJ-{year:04d}{month:02d}-"
    max_seq = 0
    if month_dir.exists():
        for child in month_dir.iterdir():
            if not child.is_dir():
                continue
            if not child.name.startswith(prefix):
                continue
            m = _ID_RE.match(child.name)
            if not m:
                continue
            try:
                seq = int(m.group(2))
            except ValueError:
                continue
            if seq > max_seq:
                max_seq = seq
    return max_seq + 1


def create_project(library_root: Path, req: CreateProjectRequest) -> CreateProjectResult:
    root = Path(library_root)
    if not root.exists() or not root.is_dir():
        raise ValueError("项目库根目录无效，请先选择项目库位置")

    year, month = parse_month(req.month)
    month_dir = root / req.month
    seq = _next_seq(month_dir, year, month)
    project_id = ProjectId(year=year, month=month, seq=seq).format()

    customer = sanitize_folder_component(req.customer)
    name = sanitize_folder_component(req.name)
    folder_name = f"{project_id}_{customer}_{name}"

    layout = build_layout(root, req.month, folder_name)
    if layout.project_dir.exists():
        for i in range(1, 1000):
            alt_id = ProjectId(year=year, month=month, seq=seq + i).format()
            alt_folder_name = f"{alt_id}_{customer}_{name}"
            alt_layout = build_layout(root, req.month, alt_folder_name)
            if not alt_layout.project_dir.exists():
                project_id = alt_id
                layout = alt_layout
                break
        else:
            raise FileExistsError("无法生成唯一的项目目录名称")

    ensure_pm_system(root)
    layout.month_dir.mkdir(parents=True, exist_ok=True)
    layout.project_dir.mkdir(parents=True, exist_ok=False)
    create_project_folders(layout.project_dir)

    # Calculate create_time based on req.month
    # If req.month is current month, use now() to preserve time
    # If req.month is past/future, use that month's date (with current time or default)
    now = datetime.now()
    if now.strftime("%Y-%m") == req.month:
        create_time = now
    else:
        # Use the 1st day of the requested month, but keep current time
        # Or just use the 1st day at 09:00? Let's use current time but on that month's 1st day
        # to ensure file system sorting or just being safe.
        # Actually, let's just make sure year/month match.
        try:
            target_date = datetime(year, month, 1, now.hour, now.minute, now.second)
            # If target day doesn't exist (e.g. 31st), datetime handles it? No, we use day=1.
            create_time = target_date
        except ValueError:
            create_time = datetime(year, month, 1)

    project = Project(
        id=project_id,
        name=req.name.strip(),
        customer=req.customer.strip(),
        customer_code=req.customer_code.strip() if req.customer_code else None,
        part_number=req.part_number.strip() if req.part_number else None,
        create_time=create_time,
        status="ongoing",
        tags=[t for t in (x.strip() for x in req.tags) if t],
        description=req.description.strip() if req.description else None,
    )
    write_project_metadata(layout.metadata_path, project)
    return CreateProjectResult(project=project, project_dir=layout.project_dir)


def edit_project_metadata(
    project_dir: Path,
    *,
    tags: list[str] | None = None,
    status: str | None = None,
    description: str | None = None,
) -> Project:
    meta_path = Path(project_dir) / ".project.json"
    if not meta_path.exists():
        raise FileNotFoundError(".project.json 不存在")
    if tags is not None:
        tags = [t for t in (x.strip() for x in tags) if t]
    return update_project_metadata(meta_path, tags=tags, status=status, description=description)


def set_project_cover(project_dir: Path, source_image_path: Path | str) -> Project:
    project_dir = Path(project_dir)
    meta_path = project_dir / ".project.json"
    if not meta_path.exists():
        raise FileNotFoundError(".project.json 不存在")

    src = Path(source_image_path)
    if not src.exists() or not src.is_file():
        raise FileNotFoundError("封面图片文件不存在")

    ext = src.suffix.lower()
    allowed = {".png", ".jpg", ".jpeg", ".webp"}
    if ext not in allowed:
        raise ValueError("封面仅支持 png/jpg/jpeg/webp")

    cover_dir = project_dir / ".pm_cover"
    cover_dir.mkdir(parents=True, exist_ok=True)

    for old in cover_dir.glob("cover.*"):
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass

    dest = cover_dir / f"cover{ext}"
    shutil.copy2(str(src), str(dest))

    rel = Path(".pm_cover") / dest.name
    return update_project_metadata(meta_path, cover_image=rel.as_posix())


def clear_project_cover(project_dir: Path) -> Project:
    project_dir = Path(project_dir)
    meta_path = project_dir / ".project.json"
    if not meta_path.exists():
        raise FileNotFoundError(".project.json 不存在")

    old = read_project_metadata(meta_path)
    if old.cover_image:
        path = Path(old.cover_image)
        if not path.is_absolute():
            path = project_dir / path
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    cover_dir = project_dir / ".pm_cover"
    try:
        if cover_dir.exists() and cover_dir.is_dir():
            for p in cover_dir.glob("*"):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
            cover_dir.rmdir()
    except Exception:
        pass

    return update_project_metadata(meta_path, cover_image="")


def archive_project(library_root: Path, project_dir: Path) -> CreateProjectResult:
    root = Path(library_root)
    src = Path(project_dir)
    meta_path = src / ".project.json"
    project = read_project_metadata(meta_path)

    dest_root = root / "归档项目"
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / src.name
    if dest.exists():
        for i in range(1, 1000):
            alt = dest_root / f"{src.name}_{i}"
            if not alt.exists():
                dest = alt
                break
        else:
            raise FileExistsError("归档目录下存在大量同名项目，无法归档")

    shutil.move(str(src), str(dest))
    project = edit_project_metadata(dest, status="archived")
    return CreateProjectResult(project=project, project_dir=dest)


def unarchive_project(library_root: Path, project_dir: Path, status: str = "ongoing") -> CreateProjectResult:
    root = Path(library_root)
    src = Path(project_dir)
    meta_path = src / ".project.json"
    project = read_project_metadata(meta_path)
    month_dir = month_dir_from_project_id(project.id)

    dest_root = root / month_dir
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / src.name
    if dest.exists():
        for i in range(1, 1000):
            alt = dest_root / f"{src.name}_{i}"
            if not alt.exists():
                dest = alt
                break
        else:
            raise FileExistsError("目标月份目录下存在大量同名项目，无法取消归档")

    shutil.move(str(src), str(dest))
    project = edit_project_metadata(dest, status=status)
    return CreateProjectResult(project=project, project_dir=dest)


def delete_project_physically(project_dir: Path) -> None:
    """物理删除项目文件夹"""
    path = Path(project_dir)
    if not path.exists():
        return
    # shutil.rmtree handles non-empty directories
    shutil.rmtree(str(path))
