from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AccountStatus, Role, User  # noqa: E402
from app.ratelimit import login_limiter  # noqa: E402
from app.security import hash_password  # noqa: E402

client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    login_limiter.hits.clear()
    with SessionLocal() as db:
        db.add(User(email="admin@test.com", full_name="Admin", role=Role.admin,
                    password_hash=hash_password("Str0ngPassword"), status=AccountStatus.active))
        db.add(User(email="sus@test.com", full_name="Sus", role=Role.student,
                    password_hash=hash_password("Str0ngPassword"), status=AccountStatus.suspended))
        db.commit()


def login(role, ident, pw):
    return client.post("/api/auth/login", json={"role": role, "identifier": ident, "password": pw})


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_admin_login_ok_and_me():
    r = login("admin", "admin@test.com", "Str0ngPassword")
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["role"] == "admin"


def test_unknown_wrong_password_wrong_role_suspended_share_message():
    msgs = set()
    for args in [("student", "nobody@test.com", "x"), ("admin", "admin@test.com", "bad"),
                 ("student", "admin@test.com", "Str0ngPassword"),
                 ("student", "sus@test.com", "Str0ngPassword")]:
        r = login(*args)
        assert r.status_code == 401
        msgs.add(r.json()["detail"])
    assert len(msgs) == 1


def test_rate_limit():
    for _ in range(8):
        login("admin", "admin@test.com", "bad")
    assert login("admin", "admin@test.com", "bad").status_code == 429


def test_logout_all_revokes_token():
    token = login("admin", "admin@test.com", "Str0ngPassword").json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/auth/logout-all", headers=h).status_code == 204
    assert client.get("/api/auth/me", headers=h).status_code == 401
