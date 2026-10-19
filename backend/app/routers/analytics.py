from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..common import ACTIVE_WORK, aware
from ..database import get_db
from ..deps import require_roles
from ..models import (AccountStatus, Issue, IssueFeedback, IssueStatus as S, Role, User)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def date_range(name: str, start: date | None, end: date | None):
    """Returns (start_dt, end_dt) in UTC. end is exclusive."""
    today = datetime.now(timezone.utc).date()
    mon = today - timedelta(days=today.weekday())
    first = today.replace(day=1)
    last_month_end = first
    last_month_start = (first - timedelta(days=1)).replace(day=1)
    ranges = {
        "all": (None, None),
        "today": (today, today + timedelta(days=1)),
        "yesterday": (today - timedelta(days=1), today),
        "this_week": (mon, mon + timedelta(days=7)),
        "last_week": (mon - timedelta(days=7), mon),
        "this_month": (first, (first + timedelta(days=32)).replace(day=1)),
        "last_month": (last_month_start, last_month_end),
        "this_year": (date(today.year, 1, 1), date(today.year + 1, 1, 1)),
        "last_year": (date(today.year - 1, 1, 1), date(today.year, 1, 1)),
    }
    if name == "custom":
        if not start or not end or end < start:
            raise HTTPException(422, "Choose a valid start and end date.")
        s, e = start, end + timedelta(days=1)
    elif name in ranges:
        s, e = ranges[name]
    else:
        raise HTTPException(422, "Unknown date range.")
    conv = lambda d: datetime(d.year, d.month, d.day, tzinfo=timezone.utc) if d else None
    return conv(s), conv(e)


def bucket(dt: datetime, group: str) -> str:
    if group == "year":
        return f"{dt.year}"
    if group == "month":
        return f"{dt.year}-{dt.month:02d}"
    if group == "week":
        d = dt.date() - timedelta(days=dt.weekday())
        return d.isoformat()
    return dt.date().isoformat()


def _stats(issues: list[Issue], ratings: dict[int, int], group: str):
    now = datetime.now(timezone.utc)
    by_status = Counter(i.status.value for i in issues)
    resolved = [i for i in issues if i.resolved_at]
    hours = [(aware(i.resolved_at) - aware(i.created_at)).total_seconds() / 3600 for i in resolved]
    rated = [ratings[i.id] for i in issues if i.id in ratings]
    series = defaultdict(lambda: {"reported": 0, "resolved": 0})
    for i in issues:
        series[bucket(aware(i.created_at), group)]["reported"] += 1
        if i.resolved_at:
            series[bucket(aware(i.resolved_at), group)]["resolved"] += 1
    return {
        "total": len(issues),
        "by_status": dict(by_status),
        "by_priority": dict(Counter(i.priority.value for i in issues)),
        "by_category": dict(Counter(i.custom_category or i.category.name for i in issues)),
        "pending_review": by_status.get("reported", 0) + by_status.get("under_review", 0),
        "high_priority_open": sum(1 for i in issues if i.priority.value == "high"
                                  and i.status not in (S.closed, S.rejected, S.resolved)),
        "awaiting_acceptance": by_status.get("assigned", 0),
        "in_progress": by_status.get("in_progress", 0),
        "resolved_or_closed": by_status.get("resolved", 0) + by_status.get("closed", 0),
        "rejected": by_status.get("rejected", 0),
        "overdue": sum(1 for i in issues if i.due_at and aware(i.due_at) < now and i.status in ACTIVE_WORK),
        "reopened": by_status.get("reopened", 0),
        "avg_resolution_hours": round(sum(hours) / len(hours), 1) if hours else None,
        "avg_rating": round(sum(rated) / len(rated), 2) if len(rated) >= 3 else None,  # need enough data
        "rating_count": len(rated),
        "series": [{"period": k, **v} for k, v in sorted(series.items())],
    }


def _load(db: Session, rng, staff_id: int | None):
    stmt = select(Issue).where(Issue.is_hidden.is_(False))
    if staff_id:
        stmt = stmt.where(Issue.assigned_staff_id == staff_id)
    s, e = rng
    if s:
        stmt = stmt.where(Issue.created_at >= s, Issue.created_at < e)
    issues = db.scalars(stmt).all()
    ratings = {r.issue_id: r.rating for r in db.scalars(select(IssueFeedback)).all()}
    return issues, ratings


@router.get("/admin")
def admin_stats(range: str = "this_month", start: date | None = None, end: date | None = None,
                group: str = "day", admin: User = Depends(require_roles(Role.admin)),
                db: Session = Depends(get_db)):
    if group not in ("day", "week", "month", "year"):
        raise HTTPException(422, "group must be day, week, month or year.")
    issues, ratings = _load(db, date_range(range, start, end), None)
    out = _stats(issues, ratings, group)
    count_users = lambda role: db.scalar(select(func.count(User.id)).where(
        User.role == role, User.status == AccountStatus.active))
    out["students"] = count_users(Role.student)
    out["staff"] = count_users(Role.staff)

    # Staff workload / performance (rating is per issue, not a personal score).
    workload = []
    for st in db.scalars(select(User).where(User.role == Role.staff, User.status == AccountStatus.active)):
        mine = [i for i in issues if i.assigned_staff_id == st.id]
        workload.append({
            "name": st.full_name,
            "open": sum(1 for i in mine if i.status in ACTIVE_WORK or i.status == S.reopened),
            "completed": sum(1 for i in mine if i.status in (S.resolved, S.closed)),
        })
    out["workload"] = workload
    return out


@router.get("/staff")
def staff_stats(range: str = "this_month", start: date | None = None, end: date | None = None,
                staff: User = Depends(require_roles(Role.staff)), db: Session = Depends(get_db)):
    issues, ratings = _load(db, date_range(range, start, end), staff.id)
    out = _stats(issues, ratings, "day")
    # "completed today/week/month/year" use the staff member's own resolve dates.
    now = datetime.now(timezone.utc)
    mine = db.scalars(select(Issue).where(Issue.assigned_staff_id == staff.id, Issue.resolved_at.is_not(None))).all()
    def since(d): return sum(1 for i in mine if aware(i.resolved_at) >= d)
    today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    out["completed_today"] = since(today)
    out["completed_week"] = since(today - timedelta(days=today.weekday()))
    out["completed_month"] = since(today.replace(day=1))
    out["completed_year"] = since(today.replace(month=1, day=1))
    return out
