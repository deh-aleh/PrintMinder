"""Administrator side of requests and grants."""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.i18n import _
from app.admin.common import back, current_admin, flash, get_db, render, verify_csrf
from app.config import settings
from app.db.models import Group, QuotaGrant, QuotaRequest, RequestStatus, User
from app.policy import grants

log = logging.getLogger("app.admin")
router = APIRouter(prefix="/admin")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def _what(db: Session, req: QuotaRequest) -> dict:
    p = req.params_json or {}
    if req.kind.value == "quota":
        return {"text": f"+{p.get('amount')} {_(str(p.get('metric')))}", "scope": req.scope.value, "amount": p.get("amount"),
                "metric": p.get("metric")}
    target = db.get(Group, p.get("target_group_id"))
    return {"text": _("move to group %(name)s", name=target.name if target else "?"), "scope": "permanent", "amount": None, "metric": None}


@router.get("/requests", response_class=HTMLResponse)
def requests_page(request: Request, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    now = _now()
    grants.expire_requests(db, now)
    names = {u.id: u.username for u in db.scalars(select(User))}
    pending = db.scalars(select(QuotaRequest).where(QuotaRequest.status == RequestStatus.pending)
                         .order_by(QuotaRequest.id)).all()
    done = db.scalars(select(QuotaRequest).where(QuotaRequest.status != RequestStatus.pending)
                      .order_by(QuotaRequest.id.desc()).limit(50)).all()
    wrap = lambda rs: [{"r": r, "user": names.get(r.user_id, "?"), "by": names.get(r.decided_by), **_what(db, r)} for r in rs]  # noqa: E731
    return render(request, "requests.html", admin, pending=wrap(pending), done=wrap(done))


def _get(db: Session, req_id: int) -> QuotaRequest:
    req = db.get(QuotaRequest, req_id)
    if req is None:
        raise HTTPException(404)
    return req


@router.post("/requests/{req_id}/approve", dependencies=[Depends(verify_csrf)])
def approve(request: Request, req_id: int, amount: str = Form(""), scope: str = Form(""), note: str = Form(""),
            admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    req = _get(db, req_id)
    try:
        amt = int(amount) if amount.strip().isascii() and amount.strip().isdigit() else None
        if amount.strip() and amt is None:
            raise grants.RequestError("the amount must be a whole number")
        grants.approve_request(db, req, admin, _now(), _tz(), amount=amt, scope=scope or None, note=note)
        flash(request, _("Approved"))
        log.info("admin %s approved request %s", admin.username, req_id)
    except (grants.RequestError, ValueError) as exc:
        flash(request, str(exc), "err")
    return back("/admin/requests")


@router.post("/requests/{req_id}/reject", dependencies=[Depends(verify_csrf)])
def reject(request: Request, req_id: int, note: str = Form(""), admin: User = Depends(current_admin),
           db: Session = Depends(get_db)):
    req = _get(db, req_id)
    try:
        grants.reject_request(db, req, admin, _now(), note)
        flash(request, _("Rejected"))
    except grants.RequestError as exc:
        flash(request, str(exc), "err")
    return back("/admin/requests")


@router.get("/grants", response_class=HTMLResponse)
def grants_page(request: Request, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    now = _now()
    names = {u.id: u.username for u in db.scalars(select(User))}
    rows = db.scalars(select(QuotaGrant).order_by(QuotaGrant.id.desc()).limit(200)).all()

    def state(g: QuotaGrant) -> str:
        until = g.valid_until if g.valid_until is None or g.valid_until.tzinfo else g.valid_until.replace(tzinfo=timezone.utc)
        if g.revoked_at is not None:
            return "revoked"
        return "active" if until is None or until > now else "ended"

    return render(request, "grants.html", admin, rows=[{"g": g, "user": names.get(g.user_id, "?"), "state": state(g),
                  "by": names.get(g.granted_by)} for g in rows],
                  usernames=sorted(u for u in names.values()))


@router.post("/grants", dependencies=[Depends(verify_csrf)])
def grant_create(request: Request, username: str = Form(""), metric: str = Form(""), amount: str = Form(""),
                 scope: str = Form(""), note: str = Form(""), admin: User = Depends(current_admin),
                 db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.username == username.strip().lower())).first()
    try:
        if user is None:
            raise grants.RequestError("unknown user")
        n = int(amount) if amount.strip().isascii() and amount.strip().isdigit() else 0
        grants.create_grant(db, admin, user, metric, n, scope, note, _now(), _tz())
        flash(request, _("Grant created for %(user)s", user=user.username))
    except grants.RequestError as exc:
        flash(request, str(exc), "err")
    return back("/admin/grants")


@router.post("/grants/{grant_id}/revoke", dependencies=[Depends(verify_csrf)])
def grant_revoke(request: Request, grant_id: int, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    g = db.get(QuotaGrant, grant_id)
    if g is None:
        raise HTTPException(404)
    try:
        grants.revoke_grant(db, g, admin, _now())
        flash(request, _("Grant revoked"))
    except grants.RequestError as exc:
        flash(request, str(exc), "err")
    return back("/admin/grants")
