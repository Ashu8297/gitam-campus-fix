"""Issue state machine: which role may move an issue from one status to another."""
from fastapi import HTTPException

from .models import IssueStatus as S, Role

# (from_status, to_status) -> roles allowed
TRANSITIONS: dict[tuple[S, S], set[Role]] = {
    (S.reported, S.under_review): {Role.admin},
    (S.reported, S.approved): {Role.admin},
    (S.reported, S.rejected): {Role.admin},
    (S.under_review, S.approved): {Role.admin},
    (S.under_review, S.rejected): {Role.admin},
    (S.approved, S.assigned): {Role.admin},
    (S.assigned, S.assigned): {Role.admin},          # reassignment
    (S.assigned, S.accepted): {Role.staff},
    (S.assigned, S.approved): {Role.staff, Role.admin},  # declined -> back for reassignment
    (S.accepted, S.in_progress): {Role.staff},
    (S.in_progress, S.resolved): {Role.staff},
    (S.resolved, S.closed): {Role.admin},
    (S.resolved, S.reopened): {Role.admin},
    (S.closed, S.reopened): {Role.admin},
    (S.reopened, S.assigned): {Role.admin},
}


def check_transition(current: S, target: S, role: Role) -> None:
    allowed = TRANSITIONS.get((current, target))
    if allowed is None:
        raise HTTPException(409, f"Cannot move an issue from '{current.value}' to '{target.value}'.")
    if role not in allowed:
        raise HTTPException(403, "You do not have permission for this action.")
