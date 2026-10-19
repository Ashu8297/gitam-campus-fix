import io

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Base, SessionLocal, engine
from app.main import add_compatible_columns, api_app, app
from app.models import AccountStatus, Role, StaffProfile, StudentProfile, User
from app.ratelimit import login_limiter
from app.security import hash_password, verify_password
from app.seed import seed_defaults

client = TestClient(app)
PW = "Str0ngPassword"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def make(db, email, role, **kw):
    u = User(email=email, full_name=email.split("@")[0], role=role,
             password_hash=hash_password(PW), status=AccountStatus.active)
    if role == Role.student:
        u.student_profile = StudentProfile(registration_number=kw.get("reg", email))
    if role == Role.staff:
        u.staff_profile = StaffProfile(staff_id=kw.get("sid", email))
    db.add(u)
    db.flush()
    return u


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    login_limiter.hits.clear()
    with SessionLocal() as db:
        seed_defaults(db)
        make(db, "admin@t.com", Role.admin)
        make(db, "s1@t.com", Role.student)
        make(db, "s2@t.com", Role.student)
        make(db, "w1@t.com", Role.staff)
        make(db, "w2@t.com", Role.staff)
        db.commit()


def auth(role, email):
    r = client.post("/api/auth/login", json={"role": role, "identifier": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def new_issue(h, **over):
    data = {"title": "Broken fan in room 101", "category_id": "1", "description": "The ceiling fan does not spin.",
            "location": "Block A, Room 101", "latitude": "20.1", "longitude": "85.2",
            "gps_accuracy_meters": "12.5", "gps_captured_at": "2026-10-17T10:30:00+00:00",
            "priority": "high", **over}
    return client.post("/api/issues", data=data, headers=h)


def staff_id(h):
    admin = auth("admin", "admin@t.com")
    return {s["name"]: s["id"] for s in client.get("/api/users/staff-options", headers=admin).json()}


def test_student_cannot_approve_or_assign():
    s = auth("student", "s1@t.com")
    iid = new_issue(s).json()["id"]
    assert client.post(f"/api/issues/{iid}/approve", json={}, headers=s).status_code == 403
    assert client.post(f"/api/issues/{iid}/assign", json={"staff_id": 1}, headers=s).status_code == 403


def test_vote_only_once_and_toggle():
    s1, s2 = auth("student", "s1@t.com"), auth("student", "s2@t.com")
    iid = new_issue(s1).json()["id"]
    admin = auth("admin", "admin@t.com")
    client.post(f"/api/issues/{iid}/approve", json={}, headers=admin)
    assert client.post(f"/api/issues/{iid}/vote", headers=s2).json() == {"voted": True, "votes": 1}
    assert client.post(f"/api/issues/{iid}/vote", headers=s2).json() == {"voted": False, "votes": 0}  # toggle off
    client.post(f"/api/issues/{iid}/vote", headers=s2)
    assert client.get(f"/api/issues/{iid}", headers=s2).json()["votes"] == 1  # never 2


def test_reject_requires_reason_and_is_visible():
    s, admin = auth("student", "s1@t.com"), auth("admin", "admin@t.com")
    iid = new_issue(s).json()["id"]
    assert client.post(f"/api/issues/{iid}/reject", json={"reason": ""}, headers=admin).status_code == 422
    assert client.post(f"/api/issues/{iid}/reject", json={"reason": "Duplicate"}, headers=admin).status_code == 200
    d = client.get(f"/api/issues/{iid}", headers=s).json()
    assert d["status"] == "rejected" and d["rejection_reason"] == "Duplicate"


def test_full_lifecycle_and_timeline():
    s, admin, w = auth("student", "s1@t.com"), auth("admin", "admin@t.com"), auth("staff", "w1@t.com")
    iid = new_issue(s).json()["id"]
    sid = staff_id(admin)["w1"]
    assert client.post(f"/api/issues/{iid}/approve", json={"staff_id": sid}, headers=admin).json()["status"] == "assigned"
    assert client.post(f"/api/issues/{iid}/start", headers=w).status_code == 409  # must accept first
    assert client.post(f"/api/issues/{iid}/accept", headers=w).status_code == 200
    assert client.post(f"/api/issues/{iid}/start", headers=w).status_code == 200
    # resolve needs photos
    assert client.post(f"/api/issues/{iid}/resolve", data={"description": "Replaced capacitor"}, headers=w).status_code == 422
    r = client.post(f"/api/issues/{iid}/resolve", data={"description": "Replaced capacitor"},
                    files=[("images", ("a.png", io.BytesIO(PNG), "image/png"))], headers=w)
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert client.post(f"/api/issues/{iid}/close", headers=w).status_code == 403  # staff cannot close
    assert client.post(f"/api/issues/{iid}/close", headers=admin).json()["status"] == "closed"
    assert client.post(f"/api/issues/{iid}/feedback", json={"rating": 5}, headers=s).status_code == 201
    assert client.post(f"/api/issues/{iid}/feedback", json={"rating": 4}, headers=s).status_code == 409  # one rating only
    events = [t["event"] for t in client.get(f"/api/issues/{iid}", headers=s).json()["timeline"]]
    assert events[0] == "Issue created" and "Marked resolved" in events and "Verified and closed" in events
    # every viewer sees the same timeline
    assert events == [t["event"] for t in client.get(f"/api/issues/{iid}", headers=admin).json()["timeline"]]


def test_staff_cannot_touch_unassigned_issue():
    s, admin = auth("student", "s1@t.com"), auth("admin", "admin@t.com")
    iid = new_issue(s).json()["id"]
    sid = staff_id(admin)["w1"]
    client.post(f"/api/issues/{iid}/approve", json={"staff_id": sid}, headers=admin)
    other = auth("staff", "w2@t.com")
    assert client.post(f"/api/issues/{iid}/accept", headers=other).status_code == 404
    assert client.get(f"/api/issues/{iid}", headers=other).status_code == 404
    assert client.get("/api/issues", headers=other).json()["total"] == 0


def test_bulk_partial_failure_is_reported():
    s, admin = auth("student", "s1@t.com"), auth("admin", "admin@t.com")
    a, b = new_issue(s).json()["id"], new_issue(s, title="Leaking tap in washroom").json()["id"]
    client.post(f"/api/issues/{a}/reject", json={"reason": "x"}, headers=admin)  # a can no longer be approved
    r = client.post("/api/issues/bulk/action", json={"ids": [a, b, 9999], "action": "approve"}, headers=admin).json()
    assert r["succeeded"] == 1 and r["failed"] == 2
    assert {x["id"]: x["ok"] for x in r["results"]} == {a: False, b: True, 9999: False}


def test_upload_rejects_non_image_and_too_many():
    s = auth("student", "s1@t.com")
    bad = client.post("/api/issues", data={"title": "Some title", "category_id": "1", "description": "long description here",
                      "location": "Lab", "latitude": "20.1", "longitude": "85.2",
                      "gps_accuracy_meters": "12.5", "gps_captured_at": "2026-10-17T10:30:00+00:00",
                      "priority": "low"}, files=[("images", ("x.png", io.BytesIO(b"MZ not an image"), "image/png"))], headers=s)
    assert bad.status_code == 415
    six = [("images", (f"{i}.png", io.BytesIO(PNG), "image/png")) for i in range(6)]
    assert client.post("/api/issues", data={"title": "Some title", "category_id": "1", "description": "long description here",
                       "location": "Lab", "latitude": "20.1", "longitude": "85.2",
                       "gps_accuracy_meters": "12.5", "gps_captured_at": "2026-10-17T10:30:00+00:00",
                       "priority": "low"}, files=six, headers=s).status_code == 422


def test_duplicate_submission_blocked_by_token():
    s = auth("student", "s1@t.com")
    one = new_issue(s, client_token="abc123").json()
    two = new_issue(s, client_token="abc123").json()
    assert one["id"] == two["id"]


def test_gps_location_is_saved_per_issue_and_links_use_saved_coordinates():
    student, admin = auth("student", "s1@t.com"), auth("admin", "admin@t.com")
    first = new_issue(student, latitude="20.08874", longitude="85.30505",
                      gps_accuracy_meters="8.2", building="Block A", floor="2",
                      room_number="201", location_description="Near the east stairwell").json()
    second = new_issue(student, title="Leaking tap in room 102", latitude="21.12345",
                       longitude="86.54321", building="Block B", floor="1",
                       room_number="102").json()
    assert first["id"] != second["id"]
    assert first["latitude"] == 20.08874 and first["longitude"] == 85.30505
    assert first["gps_accuracy_meters"] == 8.2
    assert first["building"] == "Block A" and first["floor"] == "2"
    assert first["room_number"] == "201"
    assert first["location_description"] == "Near the east stairwell"
    assert first["google_maps_url"] == "https://www.google.com/maps?q=20.08874,85.30505"
    assert second["google_maps_url"] == "https://www.google.com/maps?q=21.12345,86.54321"
    assert first["gps_captured_at"] == "2026-10-17T10:30:00+00:00"
    sid = staff_id(admin)["w1"]
    client.post(f"/api/issues/{first['id']}/approve", json={"staff_id": sid}, headers=admin)
    assigned_staff = auth("staff", "w1@t.com")
    staff_detail = client.get(f"/api/issues/{first['id']}", headers=assigned_staff).json()
    assert staff_detail["latitude"] == 20.08874
    assert staff_detail["building"] == "Block A"
    assert staff_detail["google_maps_url"] == first["google_maps_url"]
    other_student = auth("student", "s2@t.com")
    public_detail = client.get(f"/api/issues/{first['id']}", headers=other_student).json()
    assert "latitude" not in public_detail and "google_maps_url" not in public_detail
    assert "building" not in public_detail


def test_report_with_photo_and_gps():
    student = auth("student", "s1@t.com")
    response = client.post("/api/issues", data={
        "title": "Broken light in hall", "category_id": "1",
        "description": "The light flickers constantly.", "location": "Main hall, first floor",
        "latitude": "20.1", "longitude": "85.2", "gps_accuracy_meters": "12.5",
        "gps_captured_at": "2026-10-17T10:30:00+00:00",
        "priority": "medium",
    }, files=[("images", ("issue.png", io.BytesIO(PNG), "image/png"))], headers=student)
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["location"] == "Main hall, first floor"
    assert len(report["images"]) == 1
    assert report["latitude"] == 20.1 and report["longitude"] == 85.2
    assert report["gps_accuracy_meters"] == 12.5
    assert report["gps_captured_at"] == "2026-10-17T10:30:00+00:00"


def test_report_with_photo_without_gps():
    student = auth("student", "s1@t.com")
    response = client.post("/api/issues", data={
        "title": "Broken light in hall", "category_id": "1",
        "description": "The light flickers constantly.", "location": "Main hall, first floor",
        "priority": "medium",
    }, files=[("images", ("issue.png", io.BytesIO(PNG), "image/png"))], headers=student)
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["location"] == "Main hall, first floor"
    assert len(report["images"]) == 1
    assert report["latitude"] is None and report["longitude"] is None
    assert report["gps_accuracy_meters"] is None and report["gps_captured_at"] is None

    partial_gps = client.post("/api/issues", data={
        "title": "Another broken light", "category_id": "1",
        "description": "The light flickers constantly.", "location": "Main hall",
        "latitude": "20.1", "priority": "medium",
    }, headers=student)
    assert partial_gps.status_code == 422
    empty_location = client.post("/api/issues", data={
        "title": "Another broken light", "category_id": "1",
        "description": "The light flickers constantly.", "location": "  ",
        "priority": "medium",
    }, headers=student)
    assert empty_location.status_code == 422


def test_cors_headers_cover_issue_responses_and_unhandled_errors():
    origin = "http://localhost:5173"
    student = auth("student", "s1@t.com")
    payload = {
        "title": "Broken light in hall",
        "category_id": "1",
        "description": "The light flickers constantly.",
        "location": "Main hall, first floor",
        "priority": "medium",
    }
    report = client.post(
        "/api/issues",
        data=payload,
        files=[("images", ("issue.png", io.BytesIO(PNG), "image/png"))],
        headers=student | {"Origin": origin},
    )
    assert report.status_code == 201, report.text
    assert report.headers["access-control-allow-origin"] == origin

    unauthorized = client.post(
        "/api/issues",
        data=payload,
        headers={"Origin": origin},
    )
    assert unauthorized.status_code == 401
    assert unauthorized.headers["access-control-allow-origin"] == origin

    invalid_gps = client.post(
        "/api/issues",
        data=payload | {"latitude": "20.1"},
        headers=student | {"Origin": origin},
    )
    assert invalid_gps.status_code == 422
    assert invalid_gps.headers["access-control-allow-origin"] == origin

    invalid_image = client.post(
        "/api/issues",
        data=payload,
        files=[("images", ("issue.png", io.BytesIO(b"not an image"), "image/png"))],
        headers=student | {"Origin": origin},
    )
    assert invalid_image.status_code == 415
    assert invalid_image.headers["access-control-allow-origin"] == origin

    def fail_unexpectedly():
        raise RuntimeError("test-only unhandled endpoint error")

    api_app.add_api_route("/__test/unhandled-error", fail_unexpectedly, methods=["GET"])
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            "/__test/unhandled-error", headers={"Origin": origin}
        )
    finally:
        api_app.router.routes = [
            route for route in api_app.router.routes
            if getattr(route, "path", None) != "/__test/unhandled-error"
        ]
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == origin


def test_issue_photo_and_gps_are_submitted_together():
    student = auth("student", "s1@t.com")
    data = {
        "title": "Broken light in hall", "category_id": "1",
        "description": "The light flickers constantly.", "location": "Main hall",
        "latitude": "20.25", "longitude": "85.75", "gps_accuracy_meters": "5",
        "gps_captured_at": "2026-10-17T10:30:00+00:00", "building": "Main block",
        "priority": "medium",
    }
    response = client.post("/api/issues", data=data,
                           files=[("images", ("report.png", io.BytesIO(PNG), "image/png"))],
                           headers=student)
    assert response.status_code == 201, response.text
    detail = client.get(f"/api/issues/{response.json()['id']}", headers=student).json()
    assert detail["images"] and detail["latitude"] == 20.25
    assert detail["google_maps_url"] == "https://www.google.com/maps?q=20.25,85.75"


def test_temporary_password_account_creation_login_and_forced_change():
    admin = auth("admin", "admin@t.com")
    student_create = client.post("/api/users", json={
        "role": "student", "full_name": "Temporary Student", "email": "temp.student@example.com",
        "registration_number": "TMP-1", "temporary_password": "TempPassw0rd",
    }, headers=admin)
    staff_create = client.post("/api/users", json={
        "role": "staff", "full_name": "Temporary Staff", "email": "temp.staff@example.com",
        "staff_id": "TMP-ST-1", "temporary_password": "StaffPassw0rd",
    }, headers=admin)
    assert student_create.status_code == 201 and staff_create.status_code == 201
    assert "password_hash" not in student_create.json()["user"]
    duplicate = client.post("/api/users", json={
        "role": "student", "full_name": "Duplicate", "email": "TEMP.STUDENT@example.com",
        "registration_number": "TMP-2",
    }, headers=admin)
    assert duplicate.status_code == 422
    admin_create = client.post("/api/users", json={
        "role": "admin", "full_name": "Temporary Admin", "email": "temp.admin@example.com",
        "temporary_password": "AdminPassw0rd",
    }, headers=admin)
    assert admin_create.status_code == 201

    with SessionLocal() as db:
        stored = db.query(User).filter_by(email="temp.student@example.com").one()
        assert stored.password_hash != "TempPassw0rd"
        assert verify_password("TempPassw0rd", stored.password_hash)
        assert stored.must_change_password

    login = client.post("/api/auth/login", json={
        "role": "student", "identifier": "temp.student@example.com", "password": "TempPassw0rd",
    })
    assert login.status_code == 200 and login.json()["user"]["must_change_password"]
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/users", headers=headers).status_code == 401
    assert client.get("/api/auth/me", headers=headers).json()["must_change_password"]
    assert client.post("/api/auth/change-password", json={"password": "StudentPass2word"},
                       headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    changed_login = client.post("/api/auth/login", json={
        "role": "student", "identifier": "temp.student@example.com", "password": "StudentPass2word",
    })
    assert changed_login.status_code == 200
    changed_headers = {"Authorization": f"Bearer {changed_login.json()['access_token']}"}
    assert client.get("/api/users", headers=changed_headers).status_code == 403

    staff_login = client.post("/api/auth/login", json={
        "role": "staff", "identifier": "temp.staff@example.com", "password": "StaffPassw0rd",
    })
    assert staff_login.status_code == 200

    admin_login = client.post("/api/auth/login", json={
        "role": "admin", "identifier": "temp.admin@example.com", "password": "AdminPassw0rd",
    })
    assert admin_login.status_code == 200 and admin_login.json()["user"]["must_change_password"]
    admin_temp_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    assert client.patch("/api/users/1", json={"role": "student"}, headers=admin_temp_headers).status_code == 401
    assert client.post("/api/auth/change-password", json={"password": "AdminPass2word"},
                       headers=admin_temp_headers).status_code == 200
    admin_new_login = client.post("/api/auth/login", json={
        "role": "admin", "identifier": "temp.admin@example.com", "password": "AdminPass2word",
    })
    assert admin_new_login.status_code == 200
    admin_new_headers = {"Authorization": f"Bearer {admin_new_login.json()['access_token']}"}
    assert client.get("/api/users", headers=admin_new_headers).status_code == 200
    assert any(user["email"] == "temp.admin@example.com"
               for user in client.get("/api/users", headers=admin_new_headers).json())
    own_role_change = client.patch(
        f"/api/users/{admin_new_login.json()['user']['id']}",
        json={"role": "student", "registration_number": "ADMIN-STUDENT"},
        headers=admin_new_headers,
    )
    assert own_role_change.status_code == 409
    edited = client.patch(
        f"/api/users/{student_create.json()['user']['id']}",
        json={"department": "Physics"}, headers=admin_new_headers,
    )
    assert edited.status_code == 200 and edited.json()["department"] == "Physics"
    promoted = client.patch(
        f"/api/users/{student_create.json()['user']['id']}",
        json={"role": "staff", "staff_id": "TMP-ST-2"}, headers=admin_new_headers,
    )
    assert promoted.status_code == 200 and promoted.json()["role"] == "staff"


def test_compatible_column_upgrade_preserves_existing_rows():
    from sqlalchemy import create_engine, inspect, text

    legacy = create_engine("sqlite://")
    try:
        with legacy.begin() as conn:
            conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255))"))
            conn.execute(text("CREATE TABLE issues (id INTEGER PRIMARY KEY, title VARCHAR(200))"))
            conn.execute(text("INSERT INTO users (id, email) VALUES (1, 'existing@example.com')"))
            conn.execute(text("INSERT INTO issues (id, title) VALUES (1, 'Existing issue')"))
        add_compatible_columns(legacy)
        add_compatible_columns(legacy)
        with legacy.connect() as conn:
            assert conn.execute(text("SELECT email, must_change_password FROM users WHERE id = 1")).one() == (
                "existing@example.com", 0,
            )
            assert conn.execute(text("SELECT title, latitude FROM issues WHERE id = 1")).one() == (
                "Existing issue", None,
            )
        issue_columns = {column["name"] for column in inspect(legacy).get_columns("issues")}
        assert {"latitude", "longitude", "gps_accuracy_meters", "gps_captured_at",
                "building", "floor", "room_number", "location_description"} <= issue_columns
    finally:
        legacy.dispose()


def test_legacy_issue_schema_upgrade_allows_new_issue_submission():
    Base.metadata.drop_all(engine)
    for table in Base.metadata.sorted_tables:
        if table.name not in {"issues", "notifications"}:
            table.create(engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE issues ("
            "id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, description TEXT NOT NULL, "
            "category VARCHAR(100), location VARCHAR(200) NOT NULL, status VARCHAR(30) NOT NULL, "
            "priority VARCHAR(30) NOT NULL, reported_by INTEGER, assigned_to INTEGER, "
            "image_url VARCHAR(500), created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE notifications ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, message VARCHAR(300) NOT NULL, "
            "is_read BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME)"
        ))

    with SessionLocal() as db:
        seed_defaults(db)
        student = make(db, "legacy-student@example.com", Role.student)
        db.commit()
        student_id = student.id
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO issues "
            "(id, title, description, category, location, status, priority, reported_by) "
            "VALUES (7, 'Legacy issue', 'Legacy description', 'Classroom equipment', "
            "'Old building', 'submitted', 'medium', :student_id)"
        ), {"student_id": student_id})

    add_compatible_columns(engine)
    student_headers = auth("student", "legacy-student@example.com")
    legacy_report = client.get("/api/issues/7", headers=student_headers)
    assert legacy_report.status_code == 200, legacy_report.text
    assert legacy_report.json()["title"] == "Legacy issue"
    assert legacy_report.json()["status"] == "reported"

    response = client.post(
        "/api/issues",
        data={
            "title": "New issue after upgrade",
            "category_id": "1",
            "description": "This issue verifies the old schema was upgraded.",
            "location": "Main hall",
            "priority": "medium",
            "client_token": "legacy-schema-regression",
        },
        files=[("images", ("issue.png", io.BytesIO(PNG), "image/png"))],
        headers=student_headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["title"] == "New issue after upgrade"

    with engine.connect() as conn:
        preserved = conn.execute(text(
            "SELECT title, category, reported_by, category_id, reporter_id, status "
            "FROM issues WHERE id = 7"
        )).one()
        assert preserved == (
            "Legacy issue", "Classroom equipment", student_id, 1, student_id, "reported",
        )


def test_private_details_not_in_feed():
    s1, s2, admin = auth("student", "s1@t.com"), auth("student", "s2@t.com"), auth("admin", "admin@t.com")
    iid = new_issue(s1).json()["id"]
    client.post(f"/api/issues/{iid}/approve", json={}, headers=admin)
    body = client.get("/api/issues", headers=s2).text
    assert "s1@t.com" not in body and "registration" not in body.lower()
    # unapproved reports are private to the reporter
    other = new_issue(s1, title="Private pending report").json()["id"]
    assert client.get(f"/api/issues/{other}", headers=s2).status_code == 404


def test_invite_flow_one_time_link_and_suspension():
    admin = auth("admin", "admin@t.com")
    r = client.post("/api/users", json={"role": "student", "full_name": "New Kid", "email": "kid@t.com",
                                        "registration_number": "R1"}, headers=admin)
    assert r.status_code == 201
    token = r.json()["invite_link"].split("token=")[1]
    login = lambda: client.post("/api/auth/login", json={"role": "student", "identifier": "kid@t.com", "password": "NewPassw0rdX"})
    assert login().status_code == 401  # cannot log in before setting password
    assert client.post("/api/auth/set-password", json={"token": token, "password": "weak"}).status_code == 422
    assert client.post("/api/auth/set-password", json={"token": token, "password": "NewPassw0rdX"}).status_code == 200
    assert client.post("/api/auth/set-password", json={"token": token, "password": "NewPassw0rdX"}).status_code == 400  # one use
    assert login().status_code == 200
    uid = r.json()["user"]["id"]
    client.patch(f"/api/users/{uid}/status", json={"status": "suspended"}, headers=admin)
    assert login().status_code == 401  # suspended users are locked out


def test_bulk_import_reports_partial_failures():
    admin = auth("admin", "admin@t.com")
    csv = ("full_name,registration_number,email,department,branch,year_of_study,semester,contact_number\n"
           "Good One,R10,g1@t.com,CSE,CSE,4,7,900\n"
           "Dup Email,R11,g1@t.com,CSE,CSE,4,7,900\n"
           "Bad Email,R12,not-an-email,CSE,CSE,4,7,900\n"
           ",R13,g3@t.com,CSE,CSE,4,7,900\n")
    r = client.post("/api/users/bulk-import?role=student", files={"file": ("s.csv", csv, "text/csv")}, headers=admin).json()
    assert r["created"] == 1 and len(r["failed"]) == 3
    assert {f["row"] for f in r["failed"]} == {3, 4, 5}


def test_student_cannot_use_admin_endpoints():
    s = auth("student", "s1@t.com")
    assert client.get("/api/users", headers=s).status_code == 403
    assert client.get("/api/analytics/admin", headers=s).status_code == 403


def test_admin_analytics_uses_real_records():
    s, admin = auth("student", "s1@t.com"), auth("admin", "admin@t.com")
    assert client.get("/api/analytics/admin?range=all", headers=admin).json()["total"] == 0
    new_issue(s)
    d = client.get("/api/analytics/admin?range=all", headers=admin).json()
    assert d["total"] == 1 and d["by_priority"] == {"high": 1} and d["students"] == 2 and d["pending_review"] == 1
