import hashlib
import logging
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import (AuditLog, Issue, IssueTimeline, Notification, Role, User,
                     UserInvitation, AccountStatus)

log = logging.getLogger("campusfix")


def audit(db: Session, actor: User | None, action: str, detail: str = ""):
    db.add(AuditLog(actor_id=actor.id if actor else None, action=action, detail=detail))


def timeline(db: Session, issue: Issue, event: str, actor: User | None, note: str | None = None):
    db.add(IssueTimeline(issue_id=issue.id, event=event, actor_id=actor.id if actor else None, note=note))


def notify(db: Session, user_ids, message: str, issue_id: int | None = None, skip: int | None = None):
    for uid in set(user_ids):
        if uid != skip:
            db.add(Notification(user_id=uid, message=message[:300], issue_id=issue_id))


def admin_ids(db: Session) -> list[int]:
    return list(db.scalars(select(User.id).where(User.role == Role.admin, User.status == AccountStatus.active)))


def student_ids(db: Session) -> list[int]:
    return list(db.scalars(select(User.id).where(User.role == Role.student, User.status == AccountStatus.active)))


def next_issue_number(db: Session) -> str:
    count = db.scalar(select(Issue.id).order_by(Issue.id.desc()).limit(1)) or 0
    return f"CF-{datetime.now(timezone.utc).year}-{count + 1:05d}"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_invitation(db: Session, user: User, purpose: str = "invite") -> str:
    """Returns the raw token (only its hash is stored). Valid 48h, one use."""
    token = secrets.token_urlsafe(32)
    db.add(UserInvitation(
        user_id=user.id, token_hash=_hash(token), purpose=purpose,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48)))
    return token


def find_invitation(db: Session, token: str) -> UserInvitation | None:
    inv = db.scalar(select(UserInvitation).where(UserInvitation.token_hash == _hash(token)))
    if not inv or inv.used_at is not None:
        return None
    exp = inv.expires_at if inv.expires_at.tzinfo else inv.expires_at.replace(tzinfo=timezone.utc)
    return inv if exp > datetime.now(timezone.utc) else None


def send_invite_email(user: User, token: str, purpose: str = "invite") -> bool:
    """Sends via SMTP if configured. Otherwise logs the link (dev mode) and returns False."""
    link = f"{settings.frontend_url}/set-password?token={token}"
    subject = "Set up your Campus Fix account" if purpose == "invite" else "Reset your Campus Fix password"
    if not settings.smtp_host:
        log.warning("SMTP not configured. Link for %s: %s", user.email, link)
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from or settings.smtp_user, user.email, subject
    msg.set_content(f"Hello {user.full_name},\n\nUse this link (valid 48 hours, one use):\n{link}\n\nCampus Fix")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True
    except Exception:
        log.exception("Email send failed")
        return False
