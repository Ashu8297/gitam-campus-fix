"""Image storage. Local-disk implementation; swap save_image() for a cloud
(e.g. Cloudinary) upload in production since free hosts have ephemeral disks."""
import os
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import String, func, inspect, select
from sqlalchemy.orm import Session

from .config import settings
from .database import Base

# Real file signatures, so a renamed .exe cannot pass as an image.
SIGNATURES = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"RIFF": ".webp",
}


def save_image(file: UploadFile) -> str:
    data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Each image must be under {settings.max_upload_mb} MB.")
    ext = next((e for sig, e in SIGNATURES.items() if data.startswith(sig)), None)
    if ext == ".webp" and data[8:12] != b"WEBP":
        ext = None
    if not ext:
        raise HTTPException(415, "Only JPG, PNG or WEBP images are allowed.")
    os.makedirs(settings.upload_dir, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(settings.upload_dir, name), "wb") as f:
        f.write(data)
    return f"/uploads/{name}"


def remove_image_if_unreferenced(db: Session, url: str) -> bool:
    """Remove a local upload only after every stored URL reference is gone."""
    if not url:
        return False
    inspector = inspect(db.get_bind())
    for table_name in inspector.get_table_names():
        table = Base.metadata.tables.get(table_name)
        if table is None:
            continue
        for column in table.columns:
            if isinstance(column.type, String) and db.scalar(
                select(func.count()).select_from(table).where(column == url)
            ):
                return False

    name = url.split("?", 1)[0].split("#", 1)[0].rsplit("/", 1)[-1]
    if not name or name in {".", ".."}:
        return False
    upload_root = os.path.abspath(settings.upload_dir)
    path = os.path.abspath(os.path.join(upload_root, name))
    if os.path.commonpath([upload_root, path]) != upload_root:
        return False
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
