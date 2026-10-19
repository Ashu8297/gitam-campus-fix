from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import (AccountStatus, Issue, IssueStatus, Role, User)

PUBLIC_STATUSES = [IssueStatus.approved, IssueStatus.assigned, IssueStatus.accepted,
                   IssueStatus.in_progress, IssueStatus.resolved, IssueStatus.closed,
                   IssueStatus.reopened]
ACTIVE_WORK = [IssueStatus.assigned, IssueStatus.accepted, IssueStatus.in_progress]


def iso(dt: datetime | None) -> str | None:
    """Always return UTC ISO time; the browser converts it to local time."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def display_name(user: User) -> str:
    if user.student_profile and user.student_profile.username:
        return user.student_profile.username
    return user.full_name


def can_view(user: User, issue: Issue) -> bool:
    if user.role == Role.admin:
        return True
    if user.role == Role.staff:
        return issue.assigned_staff_id == user.id
    if issue.is_hidden:
        return False
    return issue.reporter_id == user.id or issue.status in PUBLIC_STATUSES


def get_issue_or_404(db: Session, issue_id: int, user: User) -> Issue:
    issue = db.get(Issue, issue_id)
    if not issue or not can_view(user, issue):
        raise HTTPException(404, "Issue not found.")
    return issue


def get_active_staff(db: Session, staff_id: int) -> User:
    staff = db.get(User, staff_id)
    if not staff or staff.role != Role.staff or staff.status != AccountStatus.active:
        raise HTTPException(422, "Selected staff member is not available.")
    return staff
