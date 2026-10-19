"""One-time command to create the first administrator.

Usage (from the backend folder, with your venv active):
    python create_admin.py

Reads INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_NAME and INITIAL_ADMIN_PASSWORD from
your .env file. After it succeeds, delete the password from .env.
"""
import sys

from sqlalchemy import select

from app.config import settings
from app.database import Base, SessionLocal, engine
from app import models  # noqa: F401  (registers tables)
from app.models import AccountStatus, Role, User
from app.security import hash_password, password_problem


def main():
    email = settings.initial_admin_email.strip().lower()
    name = settings.initial_admin_name.strip()
    password = settings.initial_admin_password
    if not (email and name and password):
        sys.exit("Set INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_NAME and INITIAL_ADMIN_PASSWORD in .env first.")
    problem = password_problem(password)
    if problem:
        sys.exit(problem)

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            sys.exit("An account with that email already exists.")
        db.add(
            User(
                email=email,
                full_name=name,
                password_hash=hash_password(password),
                role=Role.admin,
                status=AccountStatus.active,
            )
        )
        db.commit()
    print(f"Administrator created: {email}")
    print("Now remove INITIAL_ADMIN_PASSWORD from your .env file.")


if __name__ == "__main__":
    main()
