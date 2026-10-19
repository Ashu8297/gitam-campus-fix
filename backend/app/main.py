import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select, text

from . import models  # noqa: F401  (registers tables)
from .cleanup import start_cleanup_scheduler
from .config import settings
from .database import Base, SessionLocal, engine
from .models import Category, IssueStatus
from .routers import about, analytics, auth, issues, notifications, settings as settings_router, users
from .seed import seed_defaults

os.makedirs(settings.upload_dir, exist_ok=True)


def add_compatible_columns(bind=engine):
    additions = {
        "users": {
            "must_change_password": "BOOLEAN NOT NULL DEFAULT 0",
            "contact_number": "VARCHAR(20)",
            "profile_photo_url": "VARCHAR(500)",
        },
        "issues": {
            "issue_number": "VARCHAR(20)",
            "client_token": "VARCHAR(64)",
            "category_id": "INTEGER",
            "custom_category": "VARCHAR(100)",
            "reporter_id": "INTEGER",
            "assigned_staff_id": "INTEGER",
            "rejection_reason": "TEXT",
            "is_hidden": "BOOLEAN NOT NULL DEFAULT 0",
            "due_at": "DATETIME",
            "resolved_at": "DATETIME",
            "latitude": "FLOAT",
            "longitude": "FLOAT",
            "gps_accuracy_meters": "FLOAT",
            "gps_captured_at": "DATETIME",
            "building": "VARCHAR(150)",
            "floor": "VARCHAR(40)",
            "room_number": "VARCHAR(60)",
            "location_description": "TEXT",
        },
        "notifications": {
            "issue_id": "INTEGER",
        },
    }
    with bind.begin() as conn:
        inspector = inspect(conn)
        for table, columns in additions.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
                    existing.add(name)
        if inspector.has_table("issues"):
            columns = {column["name"]: column for column in inspector.get_columns("issues")}
            legacy_columns = {"category", "reported_by", "assigned_to"}
            if legacy_columns <= columns.keys():
                if bind.dialect.name == "mysql":
                    for name in ("category", "reported_by"):
                        column = columns[name]
                        if not column["nullable"]:
                            sql_type = str(column["type"])
                            conn.execute(text(
                                f"ALTER TABLE issues MODIFY COLUMN `{name}` {sql_type} NULL"
                            ))
                _backfill_legacy_issues(conn)
                if bind.dialect.name == "mysql":
                    for name, sql_type in (
                        ("issue_number", "VARCHAR(20)"),
                        ("category_id", "INTEGER"),
                        ("reporter_id", "INTEGER"),
                    ):
                        conn.execute(text(
                            f"ALTER TABLE issues MODIFY COLUMN `{name}` {sql_type} NOT NULL"
                        ))
                    indexes = inspect(conn).get_indexes("issues")
                    if not any(
                        index.get("unique")
                        and index.get("column_names") == ["issue_number"]
                        for index in indexes
                    ):
                        conn.execute(text(
                            "CREATE UNIQUE INDEX ix_issues_issue_number ON issues (issue_number)"
                        ))
            if "status" in columns:
                _migrate_issue_status_values(conn, bind, columns["status"])


def _migrate_issue_status_values(conn, bind, column):
    valid_statuses = [status.value for status in IssueStatus]
    if bind.dialect.name == "mysql":
        existing_statuses = getattr(column["type"], "enums", [])
        if set(existing_statuses) != set(valid_statuses):
            expanded_statuses = list(dict.fromkeys([*existing_statuses, *valid_statuses]))
            enum_sql = ", ".join(f"'{status}'" for status in expanded_statuses)
            nullable_sql = "NULL" if column["nullable"] else "NOT NULL"
            conn.execute(text(
                f"ALTER TABLE issues MODIFY COLUMN `status` ENUM({enum_sql}) {nullable_sql}"
            ))

    conn.execute(text(
        "UPDATE issues SET `status`='reported' WHERE `status`='submitted'"
    ))
    unknown_statuses = {
        row[0] for row in conn.execute(text("SELECT DISTINCT `status` FROM issues"))
    } - set(valid_statuses)
    if unknown_statuses:
        raise RuntimeError(
            "Cannot migrate issue status values not supported by the application: "
            + ", ".join(sorted(unknown_statuses))
        )

    if bind.dialect.name == "mysql" and set(existing_statuses) != set(valid_statuses):
        enum_sql = ", ".join(f"'{status}'" for status in valid_statuses)
        nullable_sql = "NULL" if column["nullable"] else "NOT NULL"
        conn.execute(text(
            f"ALTER TABLE issues MODIFY COLUMN `status` ENUM({enum_sql}) {nullable_sql}"
        ))


def _backfill_legacy_issues(conn):
    columns = {column["name"] for column in inspect(conn).get_columns("issues")}
    rows = conn.execute(text(
        "SELECT id, category, reported_by, assigned_to, issue_number, category_id, "
        "reporter_id, assigned_staff_id, custom_category FROM issues "
        "WHERE issue_number IS NULL OR category_id IS NULL OR reporter_id IS NULL "
        "OR assigned_staff_id IS NULL"
    )).mappings()
    category_table = Category.__table__
    categories = {
        name: category_id
        for category_id, name in conn.execute(select(category_table.c.id, category_table.c.name))
    }
    year = datetime.now(timezone.utc).year
    for row in rows:
        issue_id = row["id"]
        original_category = (row["category"] or "").strip()
        category_name = original_category or "Other (custom category)"
        custom_category = row["custom_category"]
        if len(category_name) > 100:
            category_name = "Other (custom category)"
            custom_category = original_category[:100]
        if category_name not in categories:
            result = conn.execute(category_table.insert().values(name=category_name))
            categories[category_name] = result.inserted_primary_key[0]
        if row["reporter_id"] is None and row["reported_by"] is None:
            raise RuntimeError(
                f"Cannot migrate legacy issue {issue_id}: it has no reporting user."
            )

        values = {
            "issue_number": row["issue_number"] or f"CF-{year}-{issue_id:05d}",
            "category_id": row["category_id"] or categories[category_name],
            "reporter_id": row["reporter_id"] or row["reported_by"],
            "assigned_staff_id": row["assigned_staff_id"] or row["assigned_to"],
            "custom_category": custom_category,
        }
        conn.execute(
            text(
                "UPDATE issues SET issue_number=:issue_number, category_id=:category_id, "
                "reporter_id=:reporter_id, assigned_staff_id=:assigned_staff_id, "
                "custom_category=:custom_category WHERE id=:id"
            ),
            {**values, "id": issue_id},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Convenience for development; production should use Alembic migrations.
    Base.metadata.create_all(engine)
    add_compatible_columns()
    with SessionLocal() as db:
        seed_defaults(db)
    start_cleanup_scheduler()
    yield


api_app = FastAPI(title="Campus Fix API", version="0.2.0", lifespan=lifespan)

allowed_origins = list(dict.fromkeys([
    *settings.cors_list,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]))

for r in (auth, users, issues, notifications, analytics, about, settings_router):
    api_app.include_router(r.router)
api_app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@api_app.get("/api/categories", tags=["categories"])
def categories():
    from .database import SessionLocal as S
    with S() as db:
        return [{"id": c.id, "name": c.name} for c in db.scalars(select(Category).order_by(Category.id))]


@api_app.get("/api/health", tags=["health"])
def health():
    """Reports whether the API and the database are reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db = "ok"
    except Exception:
        db = "unavailable"
    return {"status": "ok", "database": db}


# Wrap the complete application so even unexpected exception responses carry
# CORS headers and reach browsers as HTTP errors rather than opaque CORS failures.
app = CORSMiddleware(
    app=api_app,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
