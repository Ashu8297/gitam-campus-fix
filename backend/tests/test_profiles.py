import io

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import (
    AccountStatus,
    Role,
    StaffProfile,
    StudentProfile,
    User,
)
from app.security import create_access_token, hash_password

client = TestClient(app)
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"valid test image payload"


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _user(db, role: Role, suffix: str):
    user = User(
        email=f"{suffix}@example.com",
        full_name=f"{suffix.title()} Person",
        role=role,
        status=AccountStatus.active,
        password_hash=hash_password("Str0ngPassword"),
    )
    if role == Role.admin:
        user.contact_number = "9000000002"
    elif role == Role.student:
        user.student_profile = StudentProfile(
            registration_number=f"REG-{suffix}",
            username=f"user_{suffix}",
            department="Computing",
            branch="Computer Science",
            year_of_study=3,
            semester=5,
            contact_number="9000000000",
        )
    elif role == Role.staff:
        user.staff_profile = StaffProfile(
            staff_id=f"STAFF-{suffix}",
            contact_number="9000000001",
            work_category="Electrical",
        )
    db.add(user)
    db.flush()
    return user


def _headers(user: User):
    token = create_access_token(user.id, user.role.value, user.token_version)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("role", [Role.student, Role.admin, Role.staff])
def test_each_role_can_edit_own_profile_and_photo_lifecycle(tmp_path, monkeypatch, role):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    with SessionLocal() as db:
        user = _user(db, role, f"profile-{role.value}")
        other = _user(db, role, f"other-{role.value}")
        user_id, other_id = user.id, other.id
        headers = _headers(user)
        other_headers = _headers(other)
        db.commit()

    current = client.get("/api/users/me/profile", headers=headers)
    assert current.status_code == 200
    assert current.json()["id"] == user_id
    assert current.json()["email"] == f"profile-{role.value}@example.com"
    assert current.json()["profile_photo_url"] is None
    assert current.json()["completion"] == 100

    update = {"full_name": "Changed Name"}
    if role == Role.student:
        update["department"] = "Engineering"
    elif role == Role.staff:
        update["work_category"] = "Plumbing"
    else:
        update["contact_number"] = "+1 234 567 8901"
    changed = client.patch("/api/users/me/profile", json=update, headers=headers)
    assert changed.status_code == 200, changed.text
    assert changed.json()["full_name"] == "Changed Name"
    assert changed.json()["id"] == user_id
    assert client.get("/api/users/me/profile", headers=other_headers).json()["id"] == other_id

    protected = client.patch(
        "/api/users/me/profile",
        json={"role": "admin", "email": "attacker@example.com"},
        headers=headers,
    )
    assert protected.status_code == 422

    upload = client.post(
        "/api/users/me/profile/photo",
        files={"file": ("profile.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    photo_url = upload.json()["profile_photo_url"]
    assert photo_url.startswith("/uploads/")
    assert (upload_dir / photo_url.rsplit("/", 1)[-1]).read_bytes() == PNG_BYTES

    replacement = client.post(
        "/api/users/me/profile/photo",
        files={"file": ("replacement.png", io.BytesIO(PNG_BYTES + b"second"), "image/png")},
        headers=headers,
    )
    assert replacement.status_code == 200
    new_photo_url = replacement.json()["profile_photo_url"]
    assert new_photo_url != photo_url
    assert not (upload_dir / photo_url.rsplit("/", 1)[-1]).exists()
    assert (upload_dir / new_photo_url.rsplit("/", 1)[-1]).exists()

    persisted = client.get("/api/auth/me", headers=headers)
    assert persisted.status_code == 200
    assert persisted.json()["profile_photo_url"] == new_photo_url

    removed = client.delete("/api/users/me/profile/photo", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["profile_photo_url"] is None
    assert not (upload_dir / new_photo_url.rsplit("/", 1)[-1]).exists()


def test_profile_upload_rejects_invalid_images_and_requires_auth(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    with SessionLocal() as db:
        user = _user(db, Role.student, "invalid-photo")
        headers = _headers(user)
        db.commit()

    unauthenticated = client.post(
        "/api/users/me/profile/photo",
        files={"file": ("x.png", io.BytesIO(PNG_BYTES), "image/png")},
    )
    assert unauthenticated.status_code == 401
    invalid = client.post(
        "/api/users/me/profile/photo",
        files={"file": ("fake.png", io.BytesIO(b"not an image"), "image/png")},
        headers=headers,
    )
    assert invalid.status_code == 415
    oversized = client.post(
        "/api/users/me/profile/photo",
        files={"file": ("large.png", io.BytesIO(PNG_BYTES + b"x" * (1024 * 1024)), "image/png")},
        headers=headers,
    )
    assert oversized.status_code == 413
    assert list(upload_dir.iterdir()) == []


def test_profile_photo_persists_across_login(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    with SessionLocal() as db:
        user = _user(db, Role.admin, "login-photo")
        user.password_hash = hash_password("Str0ngPassword")
        user_id = user.id
        db.commit()
        headers = _headers(user)

    saved = client.post(
        "/api/users/me/profile/photo",
        files={"file": ("profile.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers=headers,
    )
    assert saved.status_code == 200
    login = client.post(
        "/api/auth/login",
        json={"role": "admin", "identifier": "login-photo@example.com", "password": "Str0ngPassword"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == user_id
    assert login.json()["user"]["profile_photo_url"] == saved.json()["profile_photo_url"]
