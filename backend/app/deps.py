from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import AccountStatus, Role, User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def _current_user(
    creds: HTTPAuthorizationCredentials | None,
    db: Session,
    allow_password_change: bool,
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")
    if not creds:
        raise unauthorized
    payload = decode_token(creds.credentials)
    if not payload:
        raise unauthorized
    user = db.get(User, int(payload["sub"]))
    # The role always comes from the database, never from the client.
    if (
        not user
        or user.status != AccountStatus.active
        or user.token_version != payload.get("ver")
        or (user.must_change_password and not allow_password_change)
    ):
        raise unauthorized
    return user


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    return _current_user(creds, db, allow_password_change=False)


def get_current_user_for_password_change(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    return _current_user(creds, db, allow_password_change=True)


def require_roles(*roles: Role):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission.")
        return user

    return checker
