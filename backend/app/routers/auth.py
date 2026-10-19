from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_current_user_for_password_change
from ..models import AccountStatus, Role, StaffProfile, User
from ..profile_data import profile_completion
from ..ratelimit import login_limiter
from ..schemas import LoginRequest, LoginResponse, UserOut
from ..security import (DUMMY_HASH, create_access_token, hash_password,
                        password_problem, verify_password)
from ..services import audit, create_invitation, find_invitation, send_invite_email
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])

GENERIC_ERROR = (
    "Your account could not be verified. Please contact the Campus Fix "
    "administrator or college support team for assistance."
)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ident = body.identifier.strip().lower()
    ip = request.client.host if request.client else "unknown"
    key = f"{ip}:{ident}"
    login_limiter.check(key)

    user = db.scalar(select(User).where(func.lower(User.email) == ident))
    # Staff may also log in with their unique staff ID.
    if not user and body.role == "staff":
        user = db.scalar(
            select(User)
            .join(StaffProfile, StaffProfile.user_id == User.id)
            .where(StaffProfile.staff_id == body.identifier.strip())
        )

    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    # Same message for every failure so no account details leak.
    if not (
        user
        and ok
        and user.status == AccountStatus.active
        and user.role == Role(body.role)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_ERROR)

    login_limiter.reset(key)
    token = create_access_token(user.id, user.role.value, user.token_version)
    completion, _ = profile_completion(user)
    return LoginResponse(
        access_token=token,
        user=UserOut(id=user.id, email=user.email, full_name=user.full_name,
                     role=user.role.value, must_change_password=user.must_change_password,
                     profile_photo_url=user.profile_photo_url, completion=completion),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user_for_password_change)):
    completion, _ = profile_completion(user)
    return UserOut(
        id=user.id, email=user.email, full_name=user.full_name, role=user.role.value,
        must_change_password=user.must_change_password,
        profile_photo_url=user.profile_photo_url, completion=completion,
    )


@router.post("/logout-all", status_code=204)
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revoke every session for this user by bumping the token version."""
    user.token_version += 1
    db.commit()


class SetPasswordBody(BaseModel):
    token: str
    password: str


class ChangePasswordBody(BaseModel):
    password: str = Field(min_length=10, max_length=200)


class ForgotBody(BaseModel):
    email: str


@router.post("/set-password")
def set_password(body: SetPasswordBody, request: Request, db: Session = Depends(get_db)):
    """Used for both first-time setup (invitation) and password reset."""
    login_limiter.check(f"setpw:{request.client.host if request.client else 'x'}")
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(422, problem)
    inv = find_invitation(db, body.token)
    if not inv:
        raise HTTPException(400, "This link is invalid or has expired. Ask the administrator for a new one.")
    user = db.get(User, inv.user_id)
    if user.status in (AccountStatus.suspended, AccountStatus.deactivated):
        raise HTTPException(400, GENERIC_ERROR)
    from datetime import datetime, timezone
    user.password_hash = hash_password(body.password)
    user.status = AccountStatus.active
    user.must_change_password = False
    user.token_version += 1
    inv.used_at = datetime.now(timezone.utc)  # one-time use
    audit(db, user, "auth.set_password", inv.purpose)
    db.commit()
    return {"ok": True}


@router.post("/forgot-password")
def forgot_password(body: ForgotBody, request: Request, db: Session = Depends(get_db)):
    login_limiter.check(f"forgot:{request.client.host if request.client else 'x'}")
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    if user and user.status == AccountStatus.active:
        token = create_invitation(db, user, "reset")
        db.commit()
        send_invite_email(user, token, "reset")
    # Same answer whether or not the account exists.
    return {"message": "If this email belongs to an active account, a reset link has been sent."}


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    user: User = Depends(get_current_user_for_password_change),
    db: Session = Depends(get_db),
):
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(422, problem)
    user.password_hash = hash_password(body.password)
    user.must_change_password = False
    user.token_version += 1
    audit(db, user, "auth.change_password")
    db.commit()
    return {"ok": True}
