from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_roles
from ..models import AboutContent, Role, TeamMember, User
from ..services import audit
from ..storage import save_image

router = APIRouter(prefix="/api/about", tags=["about"])
ALLOWED_KEYS = {"project_name", "project_type", "purpose", "problem", "features",
                "tech_stack", "disclaimer", "submission_date", "institution"}


def member_out(m: TeamMember) -> dict:
    return {k: getattr(m, k) for k in
            ("id", "name", "role", "skills", "photo_url", "github", "linkedin", "instagram", "youtube")}


@router.get("")
def get_about(db: Session = Depends(get_db)):
    content = {c.key: c.value for c in db.scalars(select(AboutContent))}
    team = db.scalars(select(TeamMember).order_by(TeamMember.position, TeamMember.id)).all()
    return {"content": content, "team": [member_out(m) for m in team]}


class ContentBody(BaseModel):
    content: dict[str, str]


@router.put("/content")
def update_content(body: ContentBody, admin: User = Depends(require_roles(Role.admin)),
                   db: Session = Depends(get_db)):
    for k, v in body.content.items():
        if k not in ALLOWED_KEYS:
            raise HTTPException(422, f"Unknown field: {k}")
        row = db.scalar(select(AboutContent).where(AboutContent.key == k))
        if row:
            row.value = v[:5000]
        else:
            db.add(AboutContent(key=k, value=v[:5000]))
    audit(db, admin, "about.update", ",".join(body.content))
    db.commit()
    return get_about(db)


def _url_ok(v: str) -> str:
    v = v.strip()
    if v and not v.lower().startswith(("http://", "https://", "/uploads/")):
        raise ValueError("Links must start with http:// or https://")
    return v


class MemberBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role: str = Field(default="", max_length=120)
    skills: str = Field(default="", max_length=300)
    photo_url: str = Field(default="", max_length=500)
    github: str = Field(default="", max_length=300)
    linkedin: str = Field(default="", max_length=300)
    instagram: str = Field(default="", max_length=300)
    youtube: str = Field(default="", max_length=300)


@router.put("/team/{member_id}")
def update_member(member_id: int, body: MemberBody, admin: User = Depends(require_roles(Role.admin)),
                  db: Session = Depends(get_db)):
    m = db.get(TeamMember, member_id)
    if not m:
        raise HTTPException(404, "Team member not found.")
    try:
        data = {k: (_url_ok(v) if k in ("photo_url", "github", "linkedin", "instagram", "youtube") else v)
                for k, v in body.model_dump().items()}
    except ValueError as e:
        raise HTTPException(422, str(e))
    for k, v in data.items():
        setattr(m, k, v)
    audit(db, admin, "about.team_update", m.name)
    db.commit()
    return member_out(m)


@router.post("/upload")
def upload_photo(file: UploadFile = File(...), admin: User = Depends(require_roles(Role.admin))):
    return {"url": save_image(file)}
