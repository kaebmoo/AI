"""Data-subject request (Plan 7 Phase 4.5): erase one user's traces. Admin only."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.services.user_data import erase_user_data

router = APIRouter()


@router.delete("/users/{user_id}/data")
def erase_data_of_user(
    user_id: int,
    dry_run: bool = Query(True, description="true (default) = count only; false = erase — cannot be undone"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """History, session data, feedback, export files, admin-agent conversations and cached answers of
    this user. The account and its API keys stay; the query audit is anonymised, not deleted."""
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้")
    done = erase_user_data(db, user_id, dry_run=dry_run)
    if not dry_run:  # who erased whom, and how much — the record of the erasure itself stays
        import json

        from app.services import query_audit
        query_audit.record(db, user_id=current_user.id, channel="dsr_erase",
                           question=f"erase data of user {user_id}", result_columns=json.dumps(done))
    return {"user_id": user_id, "dry_run": dry_run, "erased" if not dry_run else "would_erase": done}
