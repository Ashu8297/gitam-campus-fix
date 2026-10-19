import logging
import hashlib
import json
import os
import re
import threading
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, delete, func, inspect as sqlalchemy_inspect, select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .models import (
    CleanupLog,
    Issue,
    IssueFeedback,
    IssueImage,
    IssueTimeline,
    IssueVote,
    Notification,
    SystemSetting,
)

logger = logging.getLogger(__name__)
RETENTION_KEY = "complaint_retention_days"
DEFAULT_RETENTION_DAYS = 7
ALLOWED_RETENTION_DAYS = {1, 7, 30}
_cleanup_lock = threading.Lock()
_cleanup_thread = None
_cleanup_started = False


def utcnow():
    return datetime.now(timezone.utc)


def _validate_retention_days(days: int) -> int:
    try:
        days = int(days)
    except (TypeError, ValueError) as exc:
        raise ValueError("Retention period must be an integer number of days.") from exc
    if days not in ALLOWED_RETENTION_DAYS:
        raise ValueError("Retention period must be one of: 1, 7, 30 days.")
    return days


def get_retention_days(db: Session | None = None) -> int:
    close_db = db is None
    if db is None:
        db = SessionLocal()
    try:
        row = db.get(SystemSetting, RETENTION_KEY)
        if row is None:
            return DEFAULT_RETENTION_DAYS
        try:
            return _validate_retention_days(row.value)
        except ValueError:
            return DEFAULT_RETENTION_DAYS
    finally:
        if close_db:
            db.close()


def set_retention_days(days: int, db: Session | None = None) -> int:
    days = _validate_retention_days(days)
    close_db = db is None
    if db is None:
        db = SessionLocal()
    try:
        row = db.get(SystemSetting, RETENTION_KEY)
        if row is None:
            row = SystemSetting(key=RETENTION_KEY, value=str(days))
            db.add(row)
        else:
            row.value = str(days)
        db.commit()
        return days
    finally:
        if close_db:
            db.close()


def _local_upload_path(url: str | None) -> str | None:
    if not url:
        return None
    cleaned = url.split("?", 1)[0].split("#", 1)[0].strip()
    if not cleaned:
        return None
    match = re.search(r"(?:^|/)uploads/([^/]+)$", cleaned)
    if not match:
        return None
    upload_root = os.path.abspath(settings.upload_dir)
    file_path = os.path.abspath(os.path.join(upload_root, match.group(1)))
    if os.path.commonpath([upload_root, file_path]) != upload_root:
        return None
    return file_path


def _issue_related_rows(db: Session, issue_ids: list[int]):
    if not issue_ids:
        return {
            "issues": [],
            "images": [],
            "timeline": [],
            "votes": [],
            "feedback": [],
            "notifications": [],
        }

    related_models = {
        "issues": Issue,
        "images": IssueImage,
        "timeline": IssueTimeline,
        "votes": IssueVote,
        "feedback": IssueFeedback,
        "notifications": Notification,
    }
    return {
        key: [
            {column.name: _json_value(getattr(row, column.name)) for column in model.__table__.columns}
            for row in db.scalars(select(model).where(model.issue_id.in_(issue_ids))).all()
        ] if key != "issues" else [
            {column.name: _json_value(getattr(row, column.name)) for column in model.__table__.columns}
            for row in db.scalars(select(model).where(model.id.in_(issue_ids))).all()
        ]
        for key, model in related_models.items()
    }


def _json_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def _file_is_referenced_elsewhere(db: Session, url: str) -> bool:
    image_refs = db.scalar(
        select(func.count(IssueImage.id)).where(IssueImage.url == url)
    ) or 0
    if image_refs > 0:
        return True

    inspector = sqlalchemy_inspect(db.get_bind())
    for table_name in inspector.get_table_names():
        if table_name == IssueImage.__tablename__:
            continue
        for column in inspector.get_columns(table_name):
            if not isinstance(column["type"], String):
                continue
            table = IssueImage.__table__.metadata.tables[table_name]
            if db.scalar(select(func.count()).select_from(table).where(table.c[column["name"]] == url)):
                return True
    return False


def _write_verified_complaint_backup(db: Session, issues: list[Issue]) -> str:
    os.makedirs(settings.backup_dir, exist_ok=True)
    issue_ids = [issue.id for issue in issues]
    rows = _issue_related_rows(db, issue_ids)
    attachment_manifest = []
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"complaints-before-delete-all-{stamp}-{uuid.uuid4().hex[:8]}.zip"
    final_path = os.path.join(settings.backup_dir, backup_name)
    temp_path = final_path + ".tmp"

    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archived_files = set()
            for image_row in rows["images"]:
                url = image_row.get("url")
                path = _local_upload_path(url)
                if not path or not os.path.isfile(path):
                    attachment_manifest.append({
                        "image_id": image_row["id"],
                        "url": url,
                        "backup_file": None,
                        "sha256": None,
                        "source_missing_or_external": True,
                    })
                    continue
                digest = hashlib.sha256()
                with open(path, "rb") as source:
                    content = source.read()
                digest.update(content)
                backup_file = f"attachments/{digest.hexdigest()}.bin"
                if backup_file not in archived_files:
                    archive.writestr(backup_file, content)
                    archived_files.add(backup_file)
                attachment_manifest.append({
                    "image_id": image_row["id"],
                    "url": url,
                    "backup_file": backup_file,
                    "sha256": digest.hexdigest(),
                    "source_missing_or_external": False,
                })

            manifest = {
                "created_at": utcnow().isoformat(),
                "complaint_count": len(rows["issues"]),
                "attachment_count": len(rows["images"]),
                "records": rows,
                "attachments": attachment_manifest,
            }
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        with zipfile.ZipFile(temp_path, "r") as archive:
            if archive.testzip() is not None:
                raise OSError("Backup archive verification failed.")
            verified = json.loads(archive.read("manifest.json"))
            if (
                verified["complaint_count"] != len(issues)
                or verified["attachment_count"] != len(rows["images"])
            ):
                raise OSError("Backup record-count verification failed.")
            for item in verified["attachments"]:
                if item["backup_file"] is None:
                    continue
                payload = archive.read(item["backup_file"])
                if hashlib.sha256(payload).hexdigest() != item["sha256"]:
                    raise OSError("Backup attachment verification failed.")
        os.replace(temp_path, final_path)
        return backup_name
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                logger.exception("Could not remove incomplete complaint backup archive")
        raise


def preview_delete_all(db: Session | None = None):
    close_db = db is None
    if db is None:
        db = SessionLocal()
    try:
        issues = db.scalars(select(Issue).order_by(Issue.created_at.asc())).all()
        attachments = sum(len(issue.images) for issue in issues)
        return {
            "complaint_count": len(issues),
            "attachment_count": attachments,
        }
    finally:
        if close_db:
            db.close()


def delete_all_complaints(
    db: Session | None = None,
    expected_complaints: int | None = None,
    expected_attachments: int | None = None,
):
    close_db = db is None
    if db is None:
        db = SessionLocal()
    started_at = utcnow()
    if not _cleanup_lock.acquire(blocking=False):
        if close_db:
            db.close()
        return {"status": "busy", "complaint_count": 0, "attachment_count": 0}
    try:
        issues = db.scalars(select(Issue).order_by(Issue.created_at.asc())).all()
        issue_ids = [issue.id for issue in issues]
        attachment_count = sum(len(issue.images) for issue in issues)
        if (
            expected_complaints is not None
            and expected_attachments is not None
            and (
                len(issue_ids) != expected_complaints
                or attachment_count != expected_attachments
            )
        ):
            return {
                "status": "stale",
                "complaint_count": len(issue_ids),
                "attachment_count": attachment_count,
            }
        if not issues:
            db.add(CleanupLog(
                started_at=started_at,
                completed_at=utcnow(),
                retention_days=0,
                complaint_count=0,
                attachment_count=0,
                mode="manual_delete_all",
                status="no_action",
                message="Delete-all requested; no complaint records existed.",
            ))
            db.commit()
            return {
                "status": "no_action",
                "complaint_count": 0,
                "attachment_count": 0,
                "file_errors": 0,
                "backup": None,
            }

        backup_name = _write_verified_complaint_backup(db, issues)
        attachment_urls = {
            image.url
            for issue in issues
            for image in issue.images
            if image.url
        }

        try:
            db.execute(delete(Notification).where(Notification.issue_id.in_(issue_ids)))
            db.execute(delete(IssueTimeline).where(IssueTimeline.issue_id.in_(issue_ids)))
            db.execute(delete(IssueVote).where(IssueVote.issue_id.in_(issue_ids)))
            db.execute(delete(IssueFeedback).where(IssueFeedback.issue_id.in_(issue_ids)))
            db.execute(delete(IssueImage).where(IssueImage.issue_id.in_(issue_ids)))
            db.execute(delete(Issue).where(Issue.id.in_(issue_ids)))
            log_entry = CleanupLog(
                started_at=started_at,
                completed_at=utcnow(),
                retention_days=0,
                complaint_count=len(issue_ids),
                attachment_count=attachment_count,
                mode="manual_delete_all",
                status="completed",
                message=f"Deleted all complaints. Verified backup: {backup_name}.",
            )
            db.add(log_entry)
            db.commit()
        except Exception:
            db.rollback()
            raise

        file_errors = 0
        for url in attachment_urls:
            try:
                if _file_is_referenced_elsewhere(db, url):
                    continue
                file_path = _local_upload_path(url)
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                logger.exception("Could not safely remove complaint attachment after database commit")
                file_errors += 1
        if file_errors:
            logger.error("Delete-all completed with %s attachment file deletion failures", file_errors)
            try:
                log_entry.file_errors = file_errors
                log_entry.status = "completed_with_file_errors"
                log_entry.message = (
                    f"Deleted all complaints. Verified backup: {backup_name}. "
                    f"{file_errors} attachment files could not be removed."
                )
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Could not update delete-all cleanup log with file errors")
        return {
            "status": "completed",
            "complaint_count": len(issue_ids),
            "attachment_count": attachment_count,
            "file_errors": file_errors,
            "backup": backup_name,
        }
    except Exception:
        db.rollback()
        logger.exception("Delete-all complaints failed before database deletion completed")
        failure = CleanupLog(
            started_at=started_at,
            completed_at=utcnow(),
            retention_days=0,
            complaint_count=0,
            attachment_count=0,
            mode="manual_delete_all",
            status="failed",
            message="Delete-all failed before database deletion completed.",
        )
        db.add(failure)
        db.commit()
        return {
            "status": "failed",
            "complaint_count": 0,
            "attachment_count": 0,
            "file_errors": 0,
        }
    finally:
        _cleanup_lock.release()
        if close_db:
            db.close()


def _build_cleanup_preview(db: Session, retention_days: int):
    cutoff = utcnow() - timedelta(days=retention_days)
    issues = db.scalars(
        select(Issue)
        .where(Issue.created_at < cutoff)
        .order_by(Issue.created_at.asc())
    ).all()
    preview = []
    total_attachments = 0
    for issue in issues:
        attachment_count = len(issue.images)
        total_attachments += attachment_count
        preview.append({
            "id": issue.id,
            "issue_number": issue.issue_number,
            "created_at": issue.created_at.isoformat(),
            "attachment_count": attachment_count,
        })
    return {
        "retention_days": retention_days,
        "cutoff": cutoff.isoformat(),
        "complaint_count": len(issues),
        "attachment_count": total_attachments,
        "issues": preview,
    }


def preview_cleanup(db: Session | None = None, retention_days: int | None = None):
    close_db = db is None
    if db is None:
        db = SessionLocal()
    try:
        days = get_retention_days(db) if retention_days is None else _validate_retention_days(retention_days)
        return _build_cleanup_preview(db, days)
    finally:
        if close_db:
            db.close()


def _delete_issue_files(db: Session, issue: Issue):
    file_errors = 0
    own_image_ids = [image.id for image in issue.images]
    for image in list(issue.images):
        if not image.url:
            continue
        shared_count = db.scalar(
            select(func.count(IssueImage.id)).where(
                IssueImage.url == image.url,
                IssueImage.id.not_in(own_image_ids),
            )
        ) or 0
        if shared_count > 0:
            continue
        used_elsewhere = False
        for table_name in sqlalchemy_inspect(db.get_bind()).get_table_names():
            if table_name == IssueImage.__tablename__:
                continue
            table = IssueImage.__table__.metadata.tables.get(table_name)
            if table is None:
                continue
            for column in table.columns:
                if isinstance(column.type, String) and db.scalar(
                    select(func.count()).select_from(table).where(column == image.url)
                ):
                    used_elsewhere = True
                    break
            if used_elsewhere:
                break
        if used_elsewhere:
            continue
        file_path = _local_upload_path(image.url)
        if not file_path:
            continue
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError as exc:
            logger.warning("Failed to delete cleanup file %s: %s", file_path, exc)
            file_errors += 1
    return file_errors


def run_cleanup(
    dry_run: bool = False,
    retention_days: int | None = None,
    mode: str = "manual",
    db: Session | None = None,
):
    close_db = db is None
    if db is None:
        db = SessionLocal()
    started_at = utcnow()
    busy_days = retention_days if retention_days is not None else get_retention_days(db)
    if not _cleanup_lock.acquire(blocking=False):
        if close_db:
            db.close()
        return {
            "dry_run": bool(dry_run),
            "retention_days": busy_days,
            "complaint_count": 0,
            "attachment_count": 0,
            "file_errors": 0,
            "status": "busy",
        }
    try:
        days = get_retention_days(db) if retention_days is None else _validate_retention_days(retention_days)
        preview = _build_cleanup_preview(db, days)
        complaint_count = preview["complaint_count"]
        attachment_count = preview["attachment_count"]
        if dry_run:
            log_entry = CleanupLog(
                started_at=started_at,
                completed_at=utcnow(),
                retention_days=days,
                complaint_count=complaint_count,
                attachment_count=attachment_count,
                mode=mode,
                status="dry_run",
                message=f"Dry run for {complaint_count} complaints older than {days} days.",
            )
            db.add(log_entry)
            db.commit()
            return {
                "dry_run": True,
                "retention_days": days,
                "complaint_count": complaint_count,
                "attachment_count": attachment_count,
                "issues": preview["issues"],
                "status": "dry_run",
            }

        if complaint_count == 0:
            log_entry = CleanupLog(
                started_at=started_at,
                completed_at=utcnow(),
                retention_days=days,
                complaint_count=0,
                attachment_count=0,
                mode=mode,
                status="no_action",
                message="No complaint records met the retention threshold.",
            )
            db.add(log_entry)
            db.commit()
            return {
                "dry_run": False,
                "retention_days": days,
                "complaint_count": 0,
                "attachment_count": 0,
                "file_errors": 0,
                "status": "no_action",
            }

        eligible = db.scalars(
            select(Issue)
            .where(Issue.created_at < (utcnow() - timedelta(days=days)))
            .order_by(Issue.created_at.asc())
        ).all()

        file_errors = 0
        for issue in eligible:
            file_errors += _delete_issue_files(db, issue)
            db.execute(delete(Notification).where(Notification.issue_id == issue.id))
            db.execute(delete(IssueTimeline).where(IssueTimeline.issue_id == issue.id))
            db.execute(delete(IssueVote).where(IssueVote.issue_id == issue.id))
            db.execute(delete(IssueFeedback).where(IssueFeedback.issue_id == issue.id))
            for image in list(issue.images):
                db.delete(image)
            db.delete(issue)
        db.commit()

        log_entry = CleanupLog(
            started_at=started_at,
            completed_at=utcnow(),
            retention_days=days,
            complaint_count=len(eligible),
            attachment_count=sum(len(issue.images) for issue in eligible),
            file_errors=file_errors,
            mode=mode,
            status="completed",
            message=f"Deleted {len(eligible)} complaints older than {days} days.",
        )
        db.add(log_entry)
        db.commit()
        return {
            "dry_run": False,
            "retention_days": days,
            "complaint_count": len(eligible),
            "attachment_count": sum(len(issue.images) for issue in eligible),
            "file_errors": file_errors,
            "status": "completed",
        }
    except Exception as exc:
        db.rollback()
        logger.exception("Complaint cleanup failed")
        log_entry = CleanupLog(
            started_at=started_at,
            completed_at=utcnow(),
            retention_days=days if "days" in locals() else DEFAULT_RETENTION_DAYS,
            complaint_count=0,
            attachment_count=0,
            mode=mode,
            status="failed",
            message=str(exc),
        )
        db.add(log_entry)
        db.commit()
        return {
            "dry_run": bool(dry_run),
            "retention_days": days if "days" in locals() else DEFAULT_RETENTION_DAYS,
            "complaint_count": 0,
            "attachment_count": 0,
            "file_errors": 0,
            "status": "failed",
            "error": str(exc),
        }
    finally:
        _cleanup_lock.release()
        if close_db:
            db.close()


def _cleanup_worker():
    while True:
        time.sleep(60)
        try:
            with SessionLocal() as db:
                current_days = get_retention_days(db)
                if current_days <= 0:
                    continue
                preview = _build_cleanup_preview(db, current_days)
                if preview["complaint_count"] == 0:
                    continue
                run_cleanup(dry_run=False, retention_days=current_days, mode="scheduled", db=db)
        except Exception:
            logger.exception("Scheduled complaint cleanup failed")


def start_cleanup_scheduler():
    global _cleanup_thread, _cleanup_started
    if _cleanup_started:
        return
    _cleanup_started = True
    _cleanup_thread = threading.Thread(target=_cleanup_worker, name="campusfix-cleanup", daemon=True)
    _cleanup_thread.start()
