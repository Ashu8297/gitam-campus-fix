import csv
import io
import logging
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import (AccountStatus, Issue, Role, StaffProfile, StudentProfile, User)
from ..profile_data import profile_response
from ..security import hash_password, password_problem
from ..services import audit, create_invitation, send_invite_email
from ..storage import remove_image_if_unreferenced, save_image

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STUDENT_COLS = ["full_name", "registration_number", "email", "department", "branch",
                "year_of_study", "semester", "contact_number"]
STAFF_COLS = ["full_name", "staff_id", "email", "contact_number", "work_category"]
MAX_ROWS = 200


def user_out(u: User) -> dict:
    p, s = u.student_profile, u.staff_profile
    return {
        "id": u.id, "full_name": u.full_name, "email": u.email, "role": u.role.value,
        "status": u.status.value,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "password_setup_required": u.password_hash is None or u.must_change_password,
        "registration_number": p.registration_number if p else None,
        "department": p.department if p else None,
        "branch": p.branch if p else None,
        "year_of_study": p.year_of_study if p else None,
        "semester": p.semester if p else None,
        "student_contact_number": p.contact_number if p else None,
        "staff_id": s.staff_id if s else None,
        "work_category": s.work_category if s else None,
        "staff_contact_number": s.contact_number if s else None,
    }


class NewUser(BaseModel):
    role: str = Field(pattern="^(student|admin|staff)$")
    full_name: str = Field(min_length=2, max_length=150)
    email: str = Field(max_length=255)
    temporary_password: str | None = Field(default=None, max_length=200)
    registration_number: str | None = Field(default=None, max_length=50)
    staff_id: str | None = Field(default=None, max_length=50)
    department: str | None = Field(default=None, max_length=100)
    branch: str | None = Field(default=None, max_length=100)
    year_of_study: int | None = Field(default=None, ge=1, le=6)
    semester: int | None = Field(default=None, ge=1, le=12)
    contact_number: str | None = Field(default=None, max_length=20)
    work_category: str | None = Field(default=None, max_length=100)


def _create_user(db: Session, d: dict, role: str) -> tuple[User, str | None]:
    email = d["email"].strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("Invalid email address.")
    if not d.get("full_name", "").strip():
        raise ValueError("Full name is required.")
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise ValueError("Email already exists.")
    temporary_password = d.get("temporary_password")
    user = User(
        email=email,
        full_name=d["full_name"].strip(),
        role=Role(role),
        status=AccountStatus.active if temporary_password else AccountStatus.invited,
        password_hash=hash_password(temporary_password) if temporary_password else None,
        must_change_password=bool(temporary_password),
    )
    if role == "student":
        reg = (d.get("registration_number") or "").strip()
        if not reg:
            raise ValueError("Registration number is required.")
        if db.scalar(select(StudentProfile.id).where(StudentProfile.registration_number == reg)):
            raise ValueError("Registration number already exists.")
        user.student_profile = StudentProfile(
            registration_number=reg, department=d.get("department") or None,
            branch=d.get("branch") or None, year_of_study=d.get("year_of_study") or None,
            semester=d.get("semester") or None, contact_number=d.get("contact_number") or None)
    elif role == "staff":
        sid = (d.get("staff_id") or "").strip()
        if not sid:
            raise ValueError("Staff ID is required.")
        if db.scalar(select(StaffProfile.id).where(StaffProfile.staff_id == sid)):
            raise ValueError("Staff ID already exists.")
        user.staff_profile = StaffProfile(
            staff_id=sid, contact_number=d.get("contact_number") or None,
            work_category=d.get("work_category") or None)
    db.add(user)
    db.flush()
    return user, None if temporary_password else create_invitation(db, user)


def _link_for(token: str) -> str:
    return f"{settings.frontend_url}/set-password?token={token}"


@router.post("", status_code=201)
def create_user(body: NewUser, admin: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    if body.temporary_password:
        problem = password_problem(body.temporary_password)
        if problem:
            raise HTTPException(422, problem)
    try:
        user, token = _create_user(db, body.model_dump(), body.role)
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e))
    audit(db, admin, "user.create", f"{user.email} ({body.role})")
    db.commit()
    if token:
        sent = send_invite_email(user, token)
        return {
            "user": user_out(user),
            "email_sent": sent,
            "invite_link": None if sent else _link_for(token),
        }
    return {"user": user_out(user), "email_sent": False, "invite_link": None}


@router.get("")
def list_users(q: str = "", role: str | None = None, status: str | None = None,
               admin: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    stmt = select(User)
    if role in ("student", "staff"):
        stmt = stmt.where(User.role == Role(role))
    elif role == "admin":
        stmt = stmt.where(User.role == Role.admin)
    if status in [s.value for s in AccountStatus]:
        stmt = stmt.where(User.status == AccountStatus(status))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.outerjoin(StudentProfile).outerjoin(StaffProfile).where(or_(
            User.full_name.ilike(like), User.email.ilike(like),
            StudentProfile.registration_number.ilike(like), StaffProfile.staff_id.ilike(like)))
    return [user_out(u) for u in db.scalars(stmt.order_by(User.id.desc()).limit(300)).all()]


class EditUser(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, pattern="^(student|admin|staff)$")
    registration_number: str | None = Field(default=None, max_length=50)
    department: str | None = Field(default=None, max_length=100)
    branch: str | None = Field(default=None, max_length=100)
    year_of_study: int | None = Field(default=None, ge=1, le=6)
    semester: int | None = Field(default=None, ge=1, le=12)
    student_contact_number: str | None = Field(default=None, max_length=20)
    staff_id: str | None = Field(default=None, max_length=50)
    work_category: str | None = Field(default=None, max_length=100)
    staff_contact_number: str | None = Field(default=None, max_length=20)


@router.patch("/{user_id}")
def edit_user(user_id: int, body: EditUser, admin: User = Depends(require_roles(Role.admin)),
              db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    data = body.model_dump(exclude_unset=True)
    email = data.get("email")
    if email is not None:
        email = email.strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(422, "Invalid email address.")
        duplicate = db.scalar(select(User.id).where(
            func.lower(User.email) == email, User.id != user.id
        ))
        if duplicate:
            raise HTTPException(409, "Email already exists.")
        user.email = email
    if "full_name" in data:
        if data["full_name"] is None:
            raise HTTPException(422, "Full name cannot be empty.")
        user.full_name = data["full_name"].strip()
    new_role = Role(data["role"]) if data.get("role") else user.role
    if user.id == admin.id and new_role != Role.admin:
        raise HTTPException(409, "You cannot remove your own administrator role.")
    if (user.role == Role.admin and user.status == AccountStatus.active
            and new_role != Role.admin):
        active_admins = db.scalar(select(func.count(User.id)).where(
            User.role == Role.admin, User.status == AccountStatus.active
        ))
        if active_admins <= 1:
            raise HTTPException(409, "At least one active administrator must remain.")
    if new_role == Role.student:
        profile = user.student_profile
        registration_number = data.get("registration_number")
        registration_number = (
            registration_number.strip() if registration_number is not None
            else profile.registration_number if profile else ""
        )
        if not registration_number:
            raise HTTPException(422, "Registration number is required for a student.")
        duplicate = db.scalar(select(StudentProfile.id).where(
            StudentProfile.registration_number == registration_number,
            StudentProfile.user_id != user.id,
        ))
        if duplicate:
            raise HTTPException(409, "Registration number already exists.")
        if profile is None:
            profile = StudentProfile(user_id=user.id, registration_number=registration_number)
            db.add(profile)
        profile.registration_number = registration_number
        for key in ("department", "branch", "year_of_study", "semester"):
            if key in data:
                setattr(profile, key, data[key])
        if "student_contact_number" in data:
            profile.contact_number = data["student_contact_number"]
    elif new_role == Role.staff:
        profile = user.staff_profile
        staff_id = data.get("staff_id")
        staff_id = staff_id.strip() if staff_id is not None else profile.staff_id if profile else ""
        if not staff_id:
            raise HTTPException(422, "Staff ID is required for facility staff.")
        duplicate = db.scalar(select(StaffProfile.id).where(
            StaffProfile.staff_id == staff_id, StaffProfile.user_id != user.id,
        ))
        if duplicate:
            raise HTTPException(409, "Staff ID already exists.")
        if profile is None:
            profile = StaffProfile(user_id=user.id, staff_id=staff_id)
            db.add(profile)
        profile.staff_id = staff_id
        if "work_category" in data:
            profile.work_category = data["work_category"]
        if "staff_contact_number" in data:
            profile.contact_number = data["staff_contact_number"]
    if user.role != new_role:
        user.role = new_role
        user.token_version += 1
    audit(db, admin, "user.update", f"{user.email} ({user.role.value})")
    db.commit()
    return user_out(user)


@router.get("/staff-options")
def staff_options(admin: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.role == Role.staff, User.status == AccountStatus.active)).all()
    return [{"id": u.id, "name": u.full_name,
             "category": u.staff_profile.work_category if u.staff_profile else None} for u in rows]


class StatusBody(BaseModel):
    status: str = Field(pattern="^(active|suspended|deactivated)$")


@router.patch("/{user_id}/status")
def set_status(user_id: int, body: StatusBody, admin: User = Depends(require_roles(Role.admin)),
               db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    if user.id == admin.id:
        raise HTTPException(409, "You cannot change your own account status.")
    if (user.role == Role.admin and user.status == AccountStatus.active
            and body.status != AccountStatus.active.value):
        active_admins = db.scalar(select(func.count(User.id)).where(
            User.role == Role.admin, User.status == AccountStatus.active
        ))
        if active_admins <= 1:
            raise HTTPException(409, "At least one active administrator must remain.")
    if user.password_hash is None and body.status == "active":
        raise HTTPException(409, "This user has not set a password yet. Resend the invitation instead.")
    user.status = AccountStatus(body.status)
    user.token_version += 1  # revoke their existing sessions immediately
    audit(db, admin, "user.status", f"{user.email} -> {body.status}")
    db.commit()
    return user_out(user)


@router.post("/{user_id}/resend-invite")
def resend_invite(user_id: int, admin: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    token = create_invitation(db, user, "invite" if user.password_hash is None else "reset")
    audit(db, admin, "user.resend_invite", user.email)
    db.commit()
    sent = send_invite_email(user, token)
    return {"email_sent": sent, "invite_link": None if sent else _link_for(token)}


@router.get("/template", response_class=PlainTextResponse)
def csv_template(role: str = "student", admin: User = Depends(require_roles(Role.admin))):
    cols = STAFF_COLS if role == "staff" else STUDENT_COLS
    sample = {
        "student": ["Sample Student", "2210000001", "sample.student@example.com", "CSE", "CSE", "4", "7", "9000000000"],
        "staff": ["Sample Staff", "ST-001", "sample.staff@example.com", "9000000001", "Electrical"],
    }["staff" if role == "staff" else "student"]
    return PlainTextResponse(",".join(cols) + "\n" + ",".join(sample) + "\n", media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={role}_template.csv"})


@router.post("/bulk-import")
def bulk_import(role: str, file: UploadFile = File(...),
                admin: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    if role not in ("student", "staff"):
        raise HTTPException(422, "role must be student or staff.")
    raw = file.file.read(1_000_001)
    if len(raw) > 1_000_000:
        raise HTTPException(413, "CSV file is too large.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV must be UTF-8 encoded.")
    reader = csv.DictReader(io.StringIO(text))
    cols = STAFF_COLS if role == "staff" else STUDENT_COLS
    missing = [c for c in cols if c not in (reader.fieldnames or [])]
    required_missing = [c for c in missing if c in ("full_name", "email", "staff_id", "registration_number")]
    if required_missing:
        raise HTTPException(422, f"CSV is missing columns: {', '.join(required_missing)}")
    rows = list(reader)
    if not rows:
        raise HTTPException(422, "The CSV has no data rows.")
    if len(rows) > MAX_ROWS:
        raise HTTPException(422, f"At most {MAX_ROWS} rows per import.")

    created, failed, links = 0, [], []
    seen_emails, seen_ids = set(), set()
    for n, row in enumerate(rows, start=2):  # row 1 is the header
        d = {k: (v or "").strip() for k, v in row.items() if k}
        key = d.get("registration_number" if role == "student" else "staff_id", "")
        email = d.get("email", "").lower()
        try:
            if email in seen_emails:
                raise ValueError("Duplicate email inside the file.")
            if key and key in seen_ids:
                raise ValueError("Duplicate ID inside the file.")
            for f in ("year_of_study", "semester"):
                if d.get(f):
                    if not d[f].isdigit():
                        raise ValueError(f"{f} must be a number.")
                    d[f] = int(d[f])
            with db.begin_nested():
                user, token = _create_user(db, d, role)
            seen_emails.add(email)
            seen_ids.add(key)
            created += 1
            links.append((user, token))
        except ValueError as e:
            failed.append({"row": n, "email": email, "error": str(e)})
    audit(db, admin, "user.bulk_import", f"{role}: {created} created, {len(failed)} failed")
    db.commit()
    dev_links = []
    for user, token in links:
        if not send_invite_email(user, token):
            dev_links.append({"email": user.email, "link": _link_for(token)})
    return {"created": created, "failed": failed, "invite_links": dev_links}


# --------------------------------------------------------- own profile ---
class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    username: str | None = Field(default=None, min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_. ]+$")
    department: str | None = Field(default=None, max_length=100)
    branch: str | None = Field(default=None, max_length=100)
    year_of_study: int | None = Field(default=None, ge=1, le=6)
    semester: int | None = Field(default=None, ge=1, le=12)
    contact_number: str | None = Field(default=None, pattern=r"^[0-9+\- ]{7,20}$")
    work_category: str | None = Field(default=None, max_length=100)


@router.get("/me/profile")
def my_profile(user: User = Depends(get_current_user)):
    return profile_response(user)


@router.patch("/me/profile")
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    values = body.model_dump(exclude_unset=True)
    if "full_name" in values:
        if values["full_name"] is None or not values["full_name"].strip():
            raise HTTPException(422, "Display name cannot be empty.")
        user.full_name = values.pop("full_name").strip()

    if user.role == Role.student:
        if not user.student_profile:
            raise HTTPException(409, "Student profile is not available for this account.")
        allowed = {"username", "department", "branch", "year_of_study", "semester", "contact_number"}
        invalid = values.keys() - allowed
        if invalid:
            raise HTTPException(422, "These profile fields are not editable for this role.")
        for key, value in values.items():
            setattr(user.student_profile, key, value.strip() or None if isinstance(value, str) else value)
    elif user.role == Role.staff:
        if not user.staff_profile:
            raise HTTPException(409, "Facility staff profile is not available for this account.")
        allowed = {"contact_number", "work_category"}
        invalid = values.keys() - allowed
        if invalid:
            raise HTTPException(422, "These profile fields are not editable for this role.")
        for key, value in values.items():
            setattr(user.staff_profile, key, value.strip() or None if isinstance(value, str) else value)
    else:
        allowed = {"contact_number"}
        invalid = values.keys() - allowed
        if invalid:
            raise HTTPException(422, "These profile fields are not editable for this role.")
        if "contact_number" in values:
            value = values["contact_number"]
            user.contact_number = value.strip() or None if isinstance(value, str) else value

    db.commit()
    db.refresh(user)
    return profile_response(user)


@router.post("/me/profile/photo")
def upload_profile_photo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(422, "Choose an image to upload.")
    previous_url = user.profile_photo_url
    uploaded_url = save_image(file)
    user.profile_photo_url = uploaded_url
    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        try:
            remove_image_if_unreferenced(db, uploaded_url)
        except OSError:
            logger.exception("Could not remove newly uploaded profile image after failed database save")
        raise
    if previous_url and previous_url != uploaded_url:
        try:
            remove_image_if_unreferenced(db, previous_url)
        except OSError:
            logger.exception("Could not remove replaced profile image")
    return profile_response(user)


@router.delete("/me/profile/photo")
def delete_profile_photo(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    previous_url = user.profile_photo_url
    user.profile_photo_url = None
    db.commit()
    db.refresh(user)
    if previous_url:
        try:
            remove_image_if_unreferenced(db, previous_url)
        except OSError:
            logger.exception("Could not remove deleted profile image")
    return profile_response(user)
