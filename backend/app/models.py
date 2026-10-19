import enum
from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    student = "student"
    admin = "admin"
    staff = "staff"


class AccountStatus(str, enum.Enum):
    invited = "invited"
    active = "active"
    suspended = "suspended"
    deactivated = "deactivated"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    contact_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    profile_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus), default=AccountStatus.invited
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), nullable=False
    )
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # bump to revoke sessions
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    student_profile: Mapped["StudentProfile | None"] = relationship(
        back_populates="user", uselist=False
    )
    staff_profile: Mapped["StaffProfile | None"] = relationship(
        back_populates="user", uselist=False
    )


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    registration_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    year_of_study: Mapped[int | None] = mapped_column(Integer, nullable=True)
    semester: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(20), nullable=True)

    user: Mapped[User] = relationship(back_populates="student_profile")


class StaffProfile(Base):
    __tablename__ = "staff_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    staff_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    contact_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    work_category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    user: Mapped[User] = relationship(back_populates="staff_profile")


# ---------------------------------------------------------------- Phase 2+ ---
from sqlalchemy import JSON, Text, UniqueConstraint  # noqa: E402


class Priority(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class IssueStatus(str, enum.Enum):
    reported = "reported"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    assigned = "assigned"
    accepted = "accepted"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"
    reopened = "reopened"


class Category(Base):
    __tablename__ = "issue_categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Issue(Base):
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    client_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey("issue_categories.id"), index=True)
    custom_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_accuracy_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    building: Mapped[str | None] = mapped_column(String(150), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(40), nullable=True)
    room_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    location_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[Priority] = mapped_column(Enum(Priority), index=True)
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus), default=IssueStatus.reported, index=True
    )
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    category: Mapped[Category] = relationship()
    reporter: Mapped[User] = relationship(foreign_keys=[reporter_id])
    assigned_staff: Mapped[User | None] = relationship(foreign_keys=[assigned_staff_id])
    images: Mapped[list["IssueImage"]] = relationship(back_populates="issue")
    timeline: Mapped[list["IssueTimeline"]] = relationship(
        back_populates="issue", order_by="IssueTimeline.id"
    )
    votes: Mapped[list["IssueVote"]] = relationship()
    __table_args__ = (UniqueConstraint("reporter_id", "client_token", name="uq_issue_client_token"),)


class IssueImage(Base):
    __tablename__ = "issue_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(20), default="report")  # report | completion
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    issue: Mapped[Issue] = relationship(back_populates="images")


class IssueVote(Base):
    __tablename__ = "issue_votes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("issue_id", "user_id", name="uq_vote_once"),)


class IssueTimeline(Base):
    __tablename__ = "issue_timeline"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    event: Mapped[str] = mapped_column(String(60))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    issue: Mapped[Issue] = relationship(back_populates="timeline")
    actor: Mapped[User | None] = relationship()


class IssueFeedback(Base):
    __tablename__ = "issue_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("issue_id", "user_id", name="uq_feedback_once"),)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(String(300))
    issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id"), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserInvitation(Base):
    __tablename__ = "user_invitations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purpose: Mapped[str] = mapped_column(String(20), default="invite")  # invite | reset


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AboutContent(Base):
    __tablename__ = "about_page_content"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    value: Mapped[str] = mapped_column(Text)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CleanupLog(Base):
    __tablename__ = "cleanup_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=7)
    complaint_count: Mapped[int] = mapped_column(Integer, default=0)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    file_errors: Mapped[int] = mapped_column(Integer, default=0)
    mode: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="completed")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TeamMember(Base):
    __tablename__ = "team_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(120), default="")
    skills: Mapped[str] = mapped_column(String(300), default="")
    photo_url: Mapped[str] = mapped_column(String(500), default="")
    github: Mapped[str] = mapped_column(String(300), default="")
    linkedin: Mapped[str] = mapped_column(String(300), default="")
    instagram: Mapped[str] = mapped_column(String(300), default="")
    youtube: Mapped[str] = mapped_column(String(300), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
