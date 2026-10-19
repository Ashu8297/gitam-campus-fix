"""Default categories and About-page content. Safe to run repeatedly."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AboutContent, Category, TeamMember

CATEGORIES = [
    "Classroom equipment", "Fans and air conditioning", "Lights and streetlights",
    "Doors and windows", "Computers and laboratory equipment", "Wi-Fi and network",
    "Washrooms and plumbing", "Water supply", "Furniture", "Electrical issues",
    "Cleanliness and waste management", "Roads and pathways", "Safety hazards",
    "Other (custom category)",
]

ABOUT = {
    "project_name": "Campus Fix — Campus Facilities & Issue Reporting Portal",
    "project_type": "Minor Project · Final Year B.Tech Computer Science · 7th Semester",
    "institution": "GITAM Bhubaneswar",
    "purpose": "Campus Fix gives verified students one place to report facility problems, support "
               "existing reports, track progress and rate completed work, while administrators and "
               "facilities staff manage the repair work with a shared, timestamped history.",
    "problem": "Maintenance complaints on a campus are often passed on verbally or through scattered "
               "messages, so they get lost, duplicated or forgotten, and students never learn what "
               "happened. Campus Fix makes every report visible, assignable and trackable.",
    "features": "Role-based login for students, admins and facilities staff\n"
                "Issue reporting with photos, priority and location\n"
                "Community feed with one-vote-per-student support\n"
                "Admin approval, rejection and staff assignment\n"
                "Staff workflow with completion photos\n"
                "Shared issue timeline and notifications\n"
                "Feedback ratings and analytics dashboards",
    "tech_stack": "React + Vite\nFastAPI (Python)\nSQLAlchemy\nMySQL\nJWT + Argon2\nRecharts",
    "submission_date": "4 November 2026",
    "disclaimer": "Campus Fix is a student-developed minor project. It is not an officially endorsed "
                  "or deployed GITAM service.",
}

TEAM = ["Ashutosh Pradhan", "Nitan Moharana", "Jayanta Kumar Pradhan", "Krishna Chandra Rout"]


def seed_defaults(db: Session) -> None:
    have = set(db.scalars(select(Category.name)))
    for name in CATEGORIES:
        if name not in have:
            db.add(Category(name=name))
    have_keys = set(db.scalars(select(AboutContent.key)))
    for k, v in ABOUT.items():
        if k not in have_keys:
            db.add(AboutContent(key=k, value=v))
    if not db.scalar(select(TeamMember.id).limit(1)):
        for i, n in enumerate(TEAM):
            # Placeholders only. Admin edits role, skills and links on the About page.
            db.add(TeamMember(name=n, role="Role to be updated", skills="", position=i))
    db.commit()
