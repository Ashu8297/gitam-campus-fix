from datetime import datetime, timedelta, timezone
import math
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..common import (ACTIVE_WORK, PUBLIC_STATUSES, aware, display_name,
                      get_active_staff, get_issue_or_404, iso)
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import (Category, Issue, IssueFeedback, IssueImage, IssueStatus as S,
                      IssueVote, Priority, Role, User)
from ..services import (admin_ids, audit, next_issue_number, notify, timeline)
from ..storage import save_image
from ..workflow import check_transition

router = APIRouter(prefix="/api/issues", tags=["issues"])
SLA_DAYS = {Priority.high: 2, Priority.medium: 5, Priority.low: 10}


# ----------------------------------------------------------------- output ---
def issue_out(issue: Issue, user: User, detail: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    due = aware(issue.due_at)
    out = {
        "id": issue.id,
        "issue_number": issue.issue_number,
        "title": issue.title,
        "category": issue.custom_category or issue.category.name,
        "location": issue.location,
        "priority": issue.priority.value,
        "status": issue.status.value,
        "is_hidden": issue.is_hidden,
        "reporter": {"name": display_name(issue.reporter)},  # no email/phone/reg no
        "votes": len(issue.votes),
        "voted": any(v.user_id == user.id for v in issue.votes),
        "images": [i.url for i in issue.images if i.kind == "report"],
        "description": issue.description if detail else issue.description[:160],
        "created_at": iso(issue.created_at),
        "updated_at": iso(issue.updated_at),
        "assigned_staff": issue.assigned_staff.full_name if issue.assigned_staff else None,
        "overdue": bool(due and due < now and issue.status in ACTIVE_WORK),
    }
    has_private_location_access = (
        user.role == Role.admin
        or issue.reporter_id == user.id
        or (user.role == Role.staff and issue.assigned_staff_id == user.id)
    )
    if has_private_location_access and issue.latitude is not None and issue.longitude is not None:
        out["google_maps_url"] = (
            f"https://www.google.com/maps?q={issue.latitude},{issue.longitude}"
        )
    if has_private_location_access:
        out.update({
            "building": issue.building,
            "floor": issue.floor,
            "room_number": issue.room_number,
            "location_description": issue.location_description,
        })
    if detail:
        out["rejection_reason"] = issue.rejection_reason
        out["completion_images"] = [i.url for i in issue.images if i.kind == "completion"]
        out["due_at"] = iso(issue.due_at)
        out["is_mine"] = issue.reporter_id == user.id
        out["timeline"] = [
            {"id": t.id, "event": t.event, "note": t.note, "created_at": iso(t.created_at),
             "actor": (t.actor.full_name if t.actor else "System"),
             "actor_role": (t.actor.role.value if t.actor else None)}
            for t in issue.timeline
        ]
        fb = next((f for f in db_feedback(issue) if f.user_id == user.id), None)
        out["my_feedback"] = {"rating": fb.rating, "comment": fb.comment} if fb else None
        if has_private_location_access:
            out.update({
                "latitude": issue.latitude,
                "longitude": issue.longitude,
                "gps_accuracy_meters": issue.gps_accuracy_meters,
                "gps_captured_at": iso(issue.gps_captured_at),
                "building": issue.building,
                "floor": issue.floor,
                "room_number": issue.room_number,
                "location_description": issue.location_description,
            })
    return out


def db_feedback(issue: Issue):
    from sqlalchemy.orm import object_session
    return object_session(issue).scalars(
        select(IssueFeedback).where(IssueFeedback.issue_id == issue.id)).all()


# ------------------------------------------------------------------ create ---
@router.post("", status_code=201)
def create_issue(
    title: str = Form(..., min_length=5, max_length=200),
    category_id: int = Form(...),
    custom_category: str = Form(""),
    description: str = Form(..., min_length=10, max_length=5000),
    location: str = Form(..., min_length=2, max_length=200),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    gps_accuracy_meters: float | None = Form(None),
    gps_captured_at: datetime | None = Form(None),
    building: str = Form("", max_length=150),
    floor: str = Form("", max_length=40),
    room_number: str = Form("", max_length=60),
    location_description: str = Form("", max_length=1000),
    priority: Priority = Form(...),
    client_token: str = Form("", max_length=64),
    images: list[UploadFile] = File(default=[]),
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(422, "Please choose a valid category.")
    if len(location.strip()) < 2:
        raise HTTPException(422, "Please enter a location or address.")
    gps_details = (latitude, longitude, gps_accuracy_meters, gps_captured_at)
    if any(value is not None for value in gps_details) and any(value is None for value in gps_details):
        raise HTTPException(422, "Provide all GPS details together or omit them.")
    if latitude is not None and longitude is not None:
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise HTTPException(422, "GPS coordinates are outside the valid range.")
    if gps_accuracy_meters is not None:
        if not math.isfinite(gps_accuracy_meters) or gps_accuracy_meters < 0:
            raise HTTPException(422, "GPS accuracy must be zero or greater.")
    if gps_captured_at is not None and gps_captured_at.tzinfo is None:
        gps_captured_at = gps_captured_at.replace(tzinfo=timezone.utc)
    if category.name.lower().startswith("other") and not custom_category.strip():
        raise HTTPException(422, "Please enter a custom category.")
    images = [i for i in images if i.filename]
    if len(images) > 5:
        raise HTTPException(422, "You can upload at most 5 photos.")

    if client_token:  # retry / double-click protection
        existing = db.scalar(select(Issue).where(
            Issue.reporter_id == user.id, Issue.client_token == client_token))
        if existing:
            return issue_out(existing, user)

    urls = [save_image(f) for f in images]  # validates type + size
    issue = Issue(
        issue_number="pending", client_token=client_token or None, title=title.strip(),
        description=description.strip(), category_id=category.id,
        custom_category=custom_category.strip() or None if category.name.lower().startswith("other") else None,
        location=location.strip(), latitude=latitude, longitude=longitude,
        gps_accuracy_meters=gps_accuracy_meters, gps_captured_at=gps_captured_at,
        building=building.strip() or None, floor=floor.strip() or None,
        room_number=room_number.strip() or None,
        location_description=location_description.strip() or None,
        priority=priority, reporter_id=user.id)
    db.add(issue)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This report was already submitted.")
    issue.issue_number = f"CF-{datetime.now(timezone.utc).year}-{issue.id:05d}"
    for u in urls:
        db.add(IssueImage(issue_id=issue.id, url=u, kind="report", uploaded_by=user.id))
    timeline(db, issue, "Issue created", user, "Reported by student.")
    notify(db, admin_ids(db), f"New issue reported: {issue.title}", issue.id)
    db.commit()
    db.refresh(issue)
    return issue_out(issue, user, detail=True)


# -------------------------------------------------------------------- list ---
@router.get("")
def list_issues(
    q: str = "", category_id: int | None = None, status: S | None = None,
    priority: Priority | None = None, mine: bool = False,
    sort: Literal["newest", "oldest", "votes"] = "newest",
    page: int = 1, page_size: int = 10,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    page, page_size = max(page, 1), min(max(page_size, 1), 50)
    stmt = select(Issue)
    if user.role == Role.staff:
        stmt = stmt.where(Issue.assigned_staff_id == user.id)
    elif user.role == Role.student:
        stmt = stmt.where(Issue.is_hidden.is_(False))
        if mine:
            stmt = stmt.where(Issue.reporter_id == user.id)
        else:
            stmt = stmt.where(or_(Issue.reporter_id == user.id, Issue.status.in_(PUBLIC_STATUSES)))
    elif mine:
        stmt = stmt.where(Issue.reporter_id == user.id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Issue.title.ilike(like), Issue.description.ilike(like),
                              Issue.issue_number.ilike(like), Issue.location.ilike(like)))
    if category_id:
        stmt = stmt.where(Issue.category_id == category_id)
    if status:
        stmt = stmt.where(Issue.status == status)
    if priority:
        stmt = stmt.where(Issue.priority == priority)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    if sort == "votes":
        vc = select(func.count(IssueVote.id)).where(IssueVote.issue_id == Issue.id).scalar_subquery()
        stmt = stmt.order_by(vc.desc(), Issue.id.desc())
    elif sort == "oldest":
        stmt = stmt.order_by(Issue.id.asc())
    else:
        stmt = stmt.order_by(Issue.id.desc())
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [issue_out(i, user) for i in rows], "total": total,
            "page": page, "page_size": page_size}


@router.get("/{issue_id}")
def issue_detail(issue_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return issue_out(get_issue_or_404(db, issue_id, user), user, detail=True)


# -------------------------------------------------------------------- vote ---
@router.post("/{issue_id}/vote")
def toggle_vote(issue_id: int, user: User = Depends(require_roles(Role.student)),
                db: Session = Depends(get_db)):
    issue = get_issue_or_404(db, issue_id, user)
    if issue.status in (S.rejected, S.closed):
        raise HTTPException(409, "Support is closed for this report.")
    existing = db.scalar(select(IssueVote).where(
        IssueVote.issue_id == issue.id, IssueVote.user_id == user.id))
    if existing:
        db.delete(existing)
        voted = False
    else:
        db.add(IssueVote(issue_id=issue.id, user_id=user.id))
        voted = True
    try:
        db.commit()
    except IntegrityError:  # simultaneous double click: unique constraint wins
        db.rollback()
        voted = True
    count = db.scalar(select(func.count(IssueVote.id)).where(IssueVote.issue_id == issue.id))
    return {"voted": voted, "votes": count}


# ------------------------------------------------------------ admin actions ---
class ReasonBody(BaseModel):
    reason: str = Field(default="", max_length=1000)


class AssignBody(BaseModel):
    staff_id: int


class ApproveBody(BaseModel):
    staff_id: int | None = None


class PriorityBody(BaseModel):
    priority: Priority


class NoteBody(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


def _assign(db: Session, issue: Issue, admin: User, staff_id: int):
    staff = get_active_staff(db, staff_id)
    check_transition(issue.status, S.assigned, admin.role)
    reassigned = issue.status == S.assigned and issue.assigned_staff_id not in (None, staff.id)
    issue.status = S.assigned
    issue.assigned_staff_id = staff.id
    issue.due_at = datetime.now(timezone.utc) + timedelta(days=SLA_DAYS[issue.priority])
    timeline(db, issue, "Reassigned" if reassigned else "Assigned to staff", admin, f"Assigned to {staff.full_name}.")
    notify(db, [staff.id], f"New task assigned: {issue.title}", issue.id)
    notify(db, [issue.reporter_id], f"Your issue '{issue.title}' was assigned to staff.", issue.id)
    audit(db, admin, "issue.assign", f"{issue.issue_number} -> staff {staff.id}")


def _approve(db: Session, issue: Issue, admin: User, staff_id: int | None):
    if staff_id is not None:
        get_active_staff(db, staff_id)  # fail early, before any change
    check_transition(issue.status, S.approved, admin.role)
    issue.status = S.approved
    issue.rejection_reason = None
    timeline(db, issue, "Approved by administrator", admin)
    audit(db, admin, "issue.approve", issue.issue_number)
    from ..services import student_ids
    notify(db, [issue.reporter_id], f"Your issue '{issue.title}' was approved.", issue.id)
    notify(db, student_ids(db), f"New campus issue: {issue.title}", issue.id, skip=issue.reporter_id)
    if staff_id is not None:
        _assign(db, issue, admin, staff_id)


def _reject(db: Session, issue: Issue, admin: User, reason: str):
    if not reason.strip():
        raise HTTPException(422, "A reason is required to reject a report.")
    check_transition(issue.status, S.rejected, admin.role)
    issue.status = S.rejected
    issue.rejection_reason = reason.strip()
    timeline(db, issue, "Rejected by administrator", admin, reason.strip())
    audit(db, admin, "issue.reject", issue.issue_number)
    notify(db, [issue.reporter_id], f"Your issue '{issue.title}' was rejected.", issue.id)


@router.post("/{issue_id}/review")
def start_review(issue_id: int, admin: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    issue = get_issue_or_404(db, issue_id, admin)
    check_transition(issue.status, S.under_review, admin.role)
    issue.status = S.under_review
    timeline(db, issue, "Under review", admin)
    db.commit()
    return issue_out(issue, admin, True)


@router.post("/{issue_id}/approve")
def approve(issue_id: int, body: ApproveBody, admin: User = Depends(require_roles(Role.admin)),
            db: Session = Depends(get_db)):
    issue = get_issue_or_404(db, issue_id, admin)
    _approve(db, issue, admin, body.staff_id)  # one transaction: approve + assign
    db.commit()
    return issue_out(issue, admin, True)


@router.post("/{issue_id}/reject")
def reject(issue_id: int, body: ReasonBody, admin: User = Depends(require_roles(Role.admin)),
           db: Session = Depends(get_db)):
    issue = get_issue_or_404(db, issue_id, admin)
    _reject(db, issue, admin, body.reason)
    db.commit()
    return issue_out(issue, admin, True)


@router.post("/{issue_id}/assign")
def assign(issue_id: int, body: AssignBody, admin: User = Depends(require_roles(Role.admin)),
           db: Session = Depends(get_db)):
    issue = get_issue_or_404(db, issue_id, admin)
    _assign(db, issue, admin, body.staff_id)
    db.commit()
    return issue_out(issue, admin, True)


@router.post("/{issue_id}/priority")
def change_priority(issue_id: int, body: PriorityBody, admin: User = Depends(require_roles(Role.admin)),
                    db: Session = Depends(get_db)):
    issue = get_issue_or_404(db, issue_id, admin)
    old = issue.priority
    issue.priority = body.priority
    timeline(db, issue, "Priority changed", admin, f"{old.value} -> {body.priority.value}")
    audit(db, admin, "issue.priority", f"{issue.issue_number}: {old.value}->{body.priority.value}")
    db.commit()
    return issue_out(issue, admin, True)


@router.post("/{issue_id}/close")
def close(issue_id: int, admin: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    issue = get_issue_or_404(db, issue_id, admin)
    check_transition(issue.status, S.closed, admin.role)
    issue.status = S.closed
    timeline(db, issue, "Verified and closed", admin)
    audit(db, admin, "issue.close", issue.issue_number)
    notify(db, [issue.reporter_id], f"Your issue '{issue.title}' was verified and closed. Please leave feedback.", issue.id)
    db.commit()
    return issue_out(issue, admin, True)


@router.post("/{issue_id}/reopen")
def reopen(issue_id: int, body: ReasonBody, admin: User = Depends(require_roles(Role.admin)),
           db: Session = Depends(get_db)):
    if not body.reason.strip():
        raise HTTPException(422, "A reason is required to reopen an issue.")
    issue = get_issue_or_404(db, issue_id, admin)
    check_transition(issue.status, S.reopened, admin.role)
    issue.status = S.reopened
    issue.resolved_at = None
    timeline(db, issue, "Reopened", admin, body.reason.strip())
    audit(db, admin, "issue.reopen", issue.issue_number)
    notify(db, [issue.reporter_id] + ([issue.assigned_staff_id] if issue.assigned_staff_id else []),
           f"Issue '{issue.title}' was reopened.", issue.id)
    db.commit()
    return issue_out(issue, admin, True)


@router.post("/{issue_id}/hide")
def toggle_hide(issue_id: int, body: ReasonBody, admin: User = Depends(require_roles(Role.admin)),
                db: Session = Depends(get_db)):
    issue = get_issue_or_404(db, issue_id, admin)
    issue.is_hidden = not issue.is_hidden
    action = "hidden" if issue.is_hidden else "restored"
    timeline(db, issue, f"Report {action} by moderator", admin, body.reason or None)
    audit(db, admin, f"issue.{action}", issue.issue_number)
    db.commit()
    return issue_out(issue, admin, True)


class BulkBody(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)
    action: Literal["approve", "reject", "assign"]
    reason: str = ""
    staff_id: int | None = None


@router.post("/bulk/action")
def bulk_action(body: BulkBody, admin: User = Depends(require_roles(Role.admin)),
                db: Session = Depends(get_db)):
    """Each issue is validated on its own; one failure never blocks the others."""
    results = []
    for iid in body.ids:
        try:
            with db.begin_nested():
                issue = db.get(Issue, iid)
                if not issue:
                    raise HTTPException(404, "Issue not found.")
                if body.action == "approve":
                    _approve(db, issue, admin, body.staff_id)
                elif body.action == "reject":
                    _reject(db, issue, admin, body.reason)
                else:
                    if body.staff_id is None:
                        raise HTTPException(422, "Choose a staff member.")
                    _assign(db, issue, admin, body.staff_id)
            results.append({"id": iid, "ok": True})
        except HTTPException as e:
            results.append({"id": iid, "ok": False, "error": e.detail})
    db.commit()
    return {"results": results, "succeeded": sum(r["ok"] for r in results),
            "failed": sum(not r["ok"] for r in results)}


# ------------------------------------------------------------- staff actions ---
def _my_task(db: Session, issue_id: int, staff: User) -> Issue:
    issue = db.get(Issue, issue_id)
    # Staff can only act on tasks assigned to them.
    if not issue or issue.assigned_staff_id != staff.id:
        raise HTTPException(404, "Task not found.")
    return issue


@router.post("/{issue_id}/accept")
def accept(issue_id: int, staff: User = Depends(require_roles(Role.staff)), db: Session = Depends(get_db)):
    issue = _my_task(db, issue_id, staff)
    check_transition(issue.status, S.accepted, staff.role)
    issue.status = S.accepted
    timeline(db, issue, "Accepted by staff", staff)
    notify(db, admin_ids(db) + [issue.reporter_id], f"{staff.full_name} accepted '{issue.title}'.", issue.id)
    db.commit()
    return issue_out(issue, staff, True)


@router.post("/{issue_id}/decline")
def decline(issue_id: int, body: ReasonBody, staff: User = Depends(require_roles(Role.staff)),
            db: Session = Depends(get_db)):
    if not body.reason.strip():
        raise HTTPException(422, "Please give a reason for declining.")
    issue = _my_task(db, issue_id, staff)
    check_transition(issue.status, S.approved, staff.role)
    issue.status = S.approved
    issue.assigned_staff_id = None
    issue.due_at = None
    timeline(db, issue, "Declined by staff", staff, body.reason.strip())
    notify(db, admin_ids(db), f"{staff.full_name} declined '{issue.title}'. Reassignment needed.", issue.id)
    db.commit()
    return {"ok": True}


@router.post("/{issue_id}/start")
def start_work(issue_id: int, staff: User = Depends(require_roles(Role.staff)), db: Session = Depends(get_db)):
    issue = _my_task(db, issue_id, staff)
    check_transition(issue.status, S.in_progress, staff.role)
    issue.status = S.in_progress
    timeline(db, issue, "Work started", staff)
    notify(db, [issue.reporter_id] + admin_ids(db), f"Work started on '{issue.title}'.", issue.id)
    db.commit()
    return issue_out(issue, staff, True)


@router.post("/{issue_id}/progress")
def add_progress(issue_id: int, body: NoteBody, staff: User = Depends(require_roles(Role.staff)),
                 db: Session = Depends(get_db)):
    issue = _my_task(db, issue_id, staff)
    if issue.status != S.in_progress:
        raise HTTPException(409, "Start the work before adding progress updates.")
    timeline(db, issue, "Progress update", staff, body.note.strip())
    notify(db, [issue.reporter_id], f"Progress update on '{issue.title}'.", issue.id)
    db.commit()
    return issue_out(issue, staff, True)


@router.post("/{issue_id}/resolve")
def resolve(issue_id: int, description: str = Form(..., min_length=5, max_length=2000),
            images: list[UploadFile] = File(default=[]),
            staff: User = Depends(require_roles(Role.staff)), db: Session = Depends(get_db)):
    issue = _my_task(db, issue_id, staff)
    check_transition(issue.status, S.resolved, staff.role)
    images = [i for i in images if i.filename]
    if not 1 <= len(images) <= 5:
        raise HTTPException(422, "Upload 1 to 5 completion photos.")
    urls = [save_image(f) for f in images]
    for u in urls:
        db.add(IssueImage(issue_id=issue.id, url=u, kind="completion", uploaded_by=staff.id))
    issue.status = S.resolved
    issue.resolved_at = datetime.now(timezone.utc)
    timeline(db, issue, "Marked resolved", staff, description.strip())
    voters = [v.user_id for v in issue.votes]
    notify(db, admin_ids(db) + [issue.reporter_id] + voters,
           f"'{issue.title}' was marked resolved.", issue.id)
    db.commit()
    return issue_out(issue, staff, True)


# ------------------------------------------------------------------ feedback ---
class FeedbackBody(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


@router.post("/{issue_id}/feedback", status_code=201)
def submit_feedback(issue_id: int, body: FeedbackBody, user: User = Depends(require_roles(Role.student)),
                    db: Session = Depends(get_db)):
    issue = get_issue_or_404(db, issue_id, user)
    if issue.reporter_id != user.id:
        raise HTTPException(403, "Only the reporter can rate this issue.")
    if issue.status not in (S.resolved, S.closed):
        raise HTTPException(409, "Feedback opens once the issue is resolved.")
    db.add(IssueFeedback(issue_id=issue.id, user_id=user.id, rating=body.rating,
                         comment=body.comment.strip() or None))
    try:
        timeline(db, issue, "Student feedback", user, f"{body.rating}/5")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "You already rated this issue.")
    return {"ok": True}
