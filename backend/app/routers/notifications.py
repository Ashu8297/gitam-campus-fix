from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..common import iso
from ..database import get_db
from ..deps import get_current_user
from ..models import Notification, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(page: int = 1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    base = select(Notification).where(Notification.user_id == user.id)
    rows = db.scalars(base.order_by(Notification.id.desc()).offset((max(page, 1) - 1) * 30).limit(30)).all()
    unread = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.is_read.is_(False)))
    return {"unread": unread, "items": [
        {"id": n.id, "message": n.message, "issue_id": n.issue_id, "is_read": n.is_read,
         "created_at": iso(n.created_at)} for n in rows]}


@router.get("/unread-count")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"unread": db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.is_read.is_(False)))}


@router.post("/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.id).values(is_read=True))
    db.commit()
    return {"ok": True}


@router.post("/{nid}/read")
def read_one(nid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.get(Notification, nid)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "Notification not found.")
    n.is_read = True
    db.commit()
    return {"ok": True}
