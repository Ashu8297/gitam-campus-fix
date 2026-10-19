import os
import zipfile
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.cleanup as cleanup_service
from app.cleanup import delete_all_complaints, preview_cleanup, preview_delete_all, run_cleanup, set_retention_days
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import (
    AccountStatus,
    AboutContent,
    Category,
    CleanupLog,
    Issue,
    IssueImage,
    IssueTimeline,
    IssueVote,
    IssueStatus,
    Priority,
    Role,
    StaffProfile,
    StudentProfile,
    SystemSetting,
    TeamMember,
    UserInvitation,
    User,
)
from app.main import app
from app.security import create_access_token, hash_password

client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    os.makedirs(settings.upload_dir, exist_ok=True)


def _make_user(db, email, role, full_name=None):
    user = User(
        email=email,
        full_name=full_name or email.split("@")[0],
        role=role,
        password_hash=hash_password("Str0ngPassword"),
        status=AccountStatus.active,
    )
    db.add(user)
    db.flush()
    return user


def _make_issue(db, reporter, title, created_at, category, file_name=None):
    issue = Issue(
        issue_number=f"CF-{created_at.year}-{len(db.scalars(select(Issue)).all()) + 1:05d}",
        title=title,
        description="Old report for retention cleanup test.",
        category_id=category.id,
        location="Old location",
        priority=Priority.high,
        status=IssueStatus.reported,
        reporter_id=reporter.id,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(issue)
    db.flush()
    if file_name:
        image = IssueImage(issue_id=issue.id, url=f"/uploads/{file_name}", kind="report", uploaded_by=reporter.id)
        db.add(image)
        db.flush()
    return issue


def test_retention_cleanup_deletes_eligible_issues_and_keeps_recent_ones():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        category = Category(name="Electrical")
        admin = _make_user(db, "admin@example.com", Role.admin, "Admin User")
        student = _make_user(db, "student@example.com", Role.student, "Student User")
        db.add(category)
        db.flush()

        old_issue = _make_issue(db, student, "Old complaint", now - timedelta(days=12), category, "old.png")
        recent_issue = _make_issue(db, student, "Recent complaint", now - timedelta(hours=3), category, "new.png")

        old_path = os.path.join(settings.upload_dir, "old.png")
        new_path = os.path.join(settings.upload_dir, "new.png")
        with open(old_path, "wb") as fh:
            fh.write(b"old")
        with open(new_path, "wb") as fh:
            fh.write(b"new")

        set_retention_days(7, db)
        result = run_cleanup(dry_run=False, retention_days=7, mode="manual", db=db)

        assert result["complaint_count"] == 1
        assert db.get(Issue, old_issue.id) is None
        assert db.get(Issue, recent_issue.id) is not None
        assert not os.path.exists(old_path)
        assert os.path.exists(new_path)
        assert db.get(User, student.id) is not None
        assert db.get(User, admin.id) is not None


def test_selected_retention_period_and_repeated_cleanup_runs_are_safe():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        category = Category(name="Water")
        student = _make_user(db, "student2@example.com", Role.student, "Student Two")
        db.add(category)
        db.flush()

        old_issue = _make_issue(db, student, "Two-day old complaint", now - timedelta(days=2), category, "two-day.png")
        issue_path = os.path.join(settings.upload_dir, "two-day.png")
        with open(issue_path, "wb") as fh:
            fh.write(b"two-day")

        set_retention_days(1, db)
        preview = preview_cleanup(db, 1)
        assert preview["complaint_count"] == 1

        set_retention_days(7, db)
        preview = preview_cleanup(db, 7)
        assert preview["complaint_count"] == 0

        result = run_cleanup(dry_run=False, retention_days=1, mode="manual", db=db)
        assert result["complaint_count"] == 1
        assert db.get(Issue, old_issue.id) is None

        safe_result = run_cleanup(dry_run=False, retention_days=1, mode="manual", db=db)
        assert safe_result["complaint_count"] == 0
        assert safe_result["status"] in {"no_action", "completed"}


def test_cleanup_handles_missing_files_and_preserves_profile_photos():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        category = Category(name="Security")
        student = _make_user(db, "student3@example.com", Role.student, "Student Three")
        db.add(category)
        db.flush()

        student.profile_photo_url = "/uploads/profile-shared.png"
        missing_issue = _make_issue(db, student, "Missing photo complaint", now - timedelta(days=20), category, "profile-shared.png")
        profile_photo = os.path.join(settings.upload_dir, "profile-photo.png")
        with open(profile_photo, "wb") as fh:
            fh.write(b"profile")
        shared_photo = os.path.join(settings.upload_dir, "profile-shared.png")
        with open(shared_photo, "wb") as fh:
            fh.write(b"profile shared with complaint")

        result = run_cleanup(dry_run=False, retention_days=7, mode="manual", db=db)
        assert result["complaint_count"] == 1
        assert result["file_errors"] >= 0
        assert db.get(Issue, missing_issue.id) is None
        assert db.get(User, student.id) is not None
        assert os.path.exists(profile_photo)
        assert os.path.exists(shared_photo)


def test_system_setting_is_created_for_retention_policy():
    with SessionLocal() as db:
        set_retention_days(30, db)
        row = db.get(SystemSetting, "complaint_retention_days")
        assert row is not None and row.value == "30"
        assert preview_cleanup(db, 30)["retention_days"] == 30


def test_delete_all_creates_verified_backup_and_preserves_non_complaint_data(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    backup_dir = tmp_path / "backups"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        category = Category(name="General")
        admin = _make_user(db, "all-admin@example.com", Role.admin, "All Admin")
        student = _make_user(db, "all-student@example.com", Role.student, "All Student")
        staff = _make_user(db, "all-staff@example.com", Role.staff, "All Staff")
        student.student_profile = StudentProfile(registration_number="all-student-reg")
        staff.staff_profile = StaffProfile(staff_id="all-staff-id")
        invitation = UserInvitation(
            user_id=student.id,
            token_hash="a" * 64,
            expires_at=now + timedelta(days=1),
        )
        db.add(invitation)
        set_retention_days(30, db)
        db.add(category)
        db.flush()
        issue = _make_issue(db, student, "Current complaint", now, category, "evidence.png")
        shared_issue = _make_issue(db, student, "Shared complaint", now - timedelta(days=400), category, "shared.png")
        db.add(IssueTimeline(issue_id=issue.id, event="Issue created", actor_id=student.id))
        db.add(IssueVote(issue_id=issue.id, user_id=staff.id))
        db.add(TeamMember(name="Team", photo_url="/uploads/shared.png"))
        db.add(AboutContent(key="shared-photo-reference", value="/uploads/shared.png"))
        db.flush()
        evidence_path = upload_dir / "evidence.png"
        shared_path = upload_dir / "shared.png"
        evidence_path.write_bytes(b"complaint evidence bytes")
        shared_path.write_bytes(b"shared file bytes")

        preview = preview_delete_all(db)
        assert preview == {"complaint_count": 2, "attachment_count": 2}
        result = delete_all_complaints(db)

        assert result["status"] == "completed"
        assert result["complaint_count"] == 2
        assert result["attachment_count"] == 2
        assert db.scalar(select(Issue.id)) is None
        assert db.scalar(select(IssueImage.id)) is None
        assert db.scalar(select(IssueTimeline.id)) is None
        assert db.scalar(select(IssueVote.id)) is None
        assert db.get(User, admin.id) is not None
        assert db.get(User, student.id) is not None
        assert db.get(User, staff.id) is not None
        assert db.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id)) is not None
        assert db.scalar(select(StaffProfile).where(StaffProfile.user_id == staff.id)) is not None
        assert db.get(UserInvitation, invitation.id) is not None
        assert db.get(SystemSetting, "complaint_retention_days").value == "30"
        assert not evidence_path.exists()
        assert shared_path.exists()
        assert db.get(TeamMember, 1).photo_url == "/uploads/shared.png"
        assert db.get(AboutContent, 1).value == "/uploads/shared.png"
        archive_path = backup_dir / result["backup"]
        assert archive_path.is_file()
        with zipfile.ZipFile(archive_path) as archive:
            manifest = __import__("json").loads(archive.read("manifest.json"))
            assert manifest["complaint_count"] == 2
            assert manifest["attachment_count"] == 2
            assert any(archive.read(item["backup_file"]) == b"complaint evidence bytes"
                       for item in manifest["attachments"] if item["backup_file"])
        assert db.get(Issue, shared_issue.id) is None


def test_delete_all_admin_route_requires_role_phrase_and_current_preview(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    backup_dir = tmp_path / "backups"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        category = Category(name="Route test")
        admin = _make_user(db, "route-admin@example.com", Role.admin, "Route Admin")
        student = _make_user(db, "route-student@example.com", Role.student, "Route Student")
        db.add(category)
        db.flush()
        issue = _make_issue(db, student, "Route complaint", now, category, "route.png")
        db.commit()
        issue_id = issue.id
        admin_token = create_access_token(admin.id, admin.role.value, admin.token_version)
        student_token = create_access_token(student.id, student.role.value, student.token_version)
        admin_id, student_id = admin.id, student.id

    (upload_dir / "route.png").write_bytes(b"route complaint attachment")

    student_headers = {"Authorization": f"Bearer {student_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    assert client.get(
        "/api/admin/settings/cleanup/delete-all/preview", headers=student_headers
    ).status_code == 403
    bad_confirmation = client.post(
        "/api/admin/settings/cleanup/delete-all",
        json={"confirmation": "delete all", "expected_complaints": 0, "expected_attachments": 0},
        headers=admin_headers,
    )
    assert bad_confirmation.status_code == 400
    preview = client.get(
        "/api/admin/settings/cleanup/delete-all/preview", headers=admin_headers
    ).json()
    assert preview == {"complaint_count": 1, "attachment_count": 1}
    stale_counts = client.post(
        "/api/admin/settings/cleanup/delete-all",
        json={"confirmation": "DELETE ALL COMPLAINTS", "expected_complaints": 0, "expected_attachments": 0},
        headers=admin_headers,
    )
    assert stale_counts.status_code == 409
    response = client.post(
        "/api/admin/settings/cleanup/delete-all",
        json={
            "confirmation": "DELETE ALL COMPLAINTS",
            "expected_complaints": preview["complaint_count"],
            "expected_attachments": preview["attachment_count"],
        },
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["complaint_count"] == 1
    assert response.json()["attachment_count"] == 1
    assert response.json()["backup"]
    assert not (upload_dir / "route.png").exists()
    with SessionLocal() as db:
        assert db.get(Issue, issue_id) is None
        assert db.get(User, admin_id) is not None
        assert db.get(User, student_id) is not None


def test_delete_all_database_failure_rolls_back_and_keeps_uploads(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    backup_dir = tmp_path / "backups"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
    with SessionLocal() as db:
        category = Category(name="Rollback")
        student = _make_user(db, "rollback-student@example.com", Role.student)
        db.add(category)
        db.flush()
        issue = _make_issue(db, student, "Rollback complaint", datetime.now(timezone.utc), category, "rollback.png")
        issue_id = issue.id
        file_path = upload_dir / "rollback.png"
        file_path.write_bytes(b"rollback data")
        db.commit()

        original_commit = db.commit
        commit_calls = 0

        def fail_first_commit():
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls == 1:
                raise RuntimeError("simulated database commit failure")
            original_commit()

        monkeypatch.setattr(db, "commit", fail_first_commit)
        result = delete_all_complaints(db)

        assert result["status"] == "failed"
        assert db.get(Issue, issue_id) is not None
        assert file_path.exists()
        assert db.scalar(select(CleanupLog).where(CleanupLog.status == "failed")) is not None
        assert list(backup_dir.glob("complaints-before-delete-all-*.zip"))


def test_delete_all_aborts_when_backup_cannot_be_verified(monkeypatch):
    with SessionLocal() as db:
        category = Category(name="Backup failure")
        student = _make_user(db, "backup-failure-student@example.com", Role.student)
        db.add(category)
        db.flush()
        issue = _make_issue(db, student, "Backup failure complaint", datetime.now(timezone.utc), category)
        issue_id = issue.id
        db.commit()

        def fail_backup(_db, _issues):
            raise OSError("simulated backup verification failure")

        monkeypatch.setattr(cleanup_service, "_write_verified_complaint_backup", fail_backup)
        result = delete_all_complaints(db)

        assert result["status"] == "failed"
        assert db.get(Issue, issue_id) is not None


def test_delete_all_file_unlink_failure_is_logged_without_rolling_back_database(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    backup_dir = tmp_path / "backups"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
    with SessionLocal() as db:
        category = Category(name="Filesystem failure")
        student = _make_user(db, "file-error-student@example.com", Role.student)
        db.add(category)
        db.flush()
        issue = _make_issue(db, student, "File error complaint", datetime.now(timezone.utc), category, "file-error.png")
        issue_id = issue.id
        file_path = upload_dir / "file-error.png"
        file_path.write_bytes(b"kept after simulated unlink failure")

        original_remove = cleanup_service.os.remove

        def fail_upload_unlink(path):
            if os.path.abspath(path) == os.path.abspath(file_path):
                raise OSError("simulated file deletion failure")
            original_remove(path)

        monkeypatch.setattr(cleanup_service.os, "remove", fail_upload_unlink)
        result = delete_all_complaints(db)

        assert result["status"] == "completed"
        assert result["complaint_count"] == 1
        assert result["file_errors"] == 1
        assert db.get(Issue, issue_id) is None
        assert file_path.exists()
        log_entry = db.scalar(select(CleanupLog).where(CleanupLog.mode == "manual_delete_all"))
        assert log_entry.status == "completed_with_file_errors"
        assert log_entry.file_errors == 1
