from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException

from ..cleanup import (
    delete_all_complaints,
    get_retention_days,
    preview_cleanup,
    preview_delete_all,
    run_cleanup,
    set_retention_days,
)
from ..database import get_db
from ..deps import require_roles
from ..models import CleanupLog, Role

router = APIRouter(prefix="/api/admin", tags=["admin-settings"])
ALLOWED_RETENTION_DAYS = [1, 7, 30]


class RetentionBody(BaseModel):
    days: int


class CleanupBody(BaseModel):
    confirm: bool = False
    dry_run: bool = False


class DeleteAllBody(BaseModel):
    confirmation: str
    expected_complaints: int
    expected_attachments: int


@router.get("/settings")
def get_settings(
    user=Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    retention_days = get_retention_days(db)
    preview = preview_cleanup(db, retention_days)
    logs = db.scalars(select(CleanupLog).order_by(CleanupLog.started_at.desc()).limit(5)).all()
    return {
        "retention_days": retention_days,
        "retention_options": ALLOWED_RETENTION_DAYS,
        "preview": preview,
        "logs": [
            {
                "id": log.id,
                "started_at": log.started_at.isoformat(),
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "retention_days": log.retention_days,
                "complaint_count": log.complaint_count,
                "attachment_count": log.attachment_count,
                "file_errors": log.file_errors,
                "mode": log.mode,
                "status": log.status,
                "message": log.message,
            }
            for log in logs
        ],
    }


@router.put("/settings/retention")
def update_retention(
    body: RetentionBody,
    user=Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    try:
        days = set_retention_days(body.days, db)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"retention_days": days, "retention_options": ALLOWED_RETENTION_DAYS}


@router.post("/settings/cleanup/preview")
def preview_cleanup_route(
    user=Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    return preview_cleanup(db, get_retention_days(db))


@router.post("/settings/cleanup")
def trigger_cleanup(
    body: CleanupBody,
    user=Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    if not body.confirm and not body.dry_run:
        raise HTTPException(400, "Confirmation required before permanent deletion.")
    if body.dry_run:
        return preview_cleanup(db, get_retention_days(db))
    result = run_cleanup(dry_run=False, retention_days=get_retention_days(db), mode="manual", db=db)
    return result


@router.get("/settings/cleanup/delete-all/preview")
def preview_delete_all_route(
    user=Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    return preview_delete_all(db)


@router.post("/settings/cleanup/delete-all")
def trigger_delete_all(
    body: DeleteAllBody,
    user=Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    if body.confirmation != "DELETE ALL COMPLAINTS":
        raise HTTPException(400, "Type DELETE ALL COMPLAINTS exactly to confirm.")
    current = preview_delete_all(db)
    if (
        current["complaint_count"] != body.expected_complaints
        or current["attachment_count"] != body.expected_attachments
    ):
        raise HTTPException(409, "Complaint or attachment counts changed. Refresh the preview before continuing.")
    result = delete_all_complaints(
        db,
        expected_complaints=body.expected_complaints,
        expected_attachments=body.expected_attachments,
    )
    if result["status"] == "busy":
        raise HTTPException(409, "Another cleanup operation is already running.")
    if result["status"] == "stale":
        raise HTTPException(409, "Complaint or attachment counts changed. Refresh the preview before continuing.")
    if result["status"] == "failed":
        raise HTTPException(500, "Complaint deletion failed; no complaint records were removed.")
    return result
