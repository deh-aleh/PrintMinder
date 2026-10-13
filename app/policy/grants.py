"""Requests for more quota / another group, and the grants that approvals produce.

A grant ADDS to the user's limit; it never edits job_log. Temporary grants end with the period of the rule that
limits the user (decided by the admin in the database, never by the user); permanent ones apply to every
following period until revoked.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.i18n import _
from app.audit.adminlog import record
from app.config import settings
from app.db.models import (
    Group, Metric, QuotaGrant, QuotaRequest, RequestKind, RequestScope, RequestStatus, Resource, User,
)
from app.policy.engine import active_grants, effective_rules, usage, window_end

MAX_AMOUNT = 100_000
MAX_TEXT = 500


def _update(model):
    """Conditional UPDATE decided by the database alone. No in-Python re-evaluation against objects already in the
    session (they carry timezone-less datetimes from SQLite): callers re-read what they need."""
    return update(model).execution_options(synchronize_session=False)


def _aware(dt: datetime) -> datetime:
    """SQLite gives datetimes back without tzinfo; everything we store is UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class RequestError(ValueError):
    """A request or decision that can not be accepted; the message is safe to show."""


def _clean(text: str, what: str, required: bool = True) -> str:
    """`what`: "reason" or "note" (picks the message; each one is a whole sentence so it can be translated)."""
    text = "".join(ch for ch in text.strip() if ch == "\n" or ord(ch) >= 32)
    if required and not text:
        raise RequestError(_("The reason is required"))
    if len(text) > MAX_TEXT:
        raise RequestError(_("The reason is too long (max %(max)s characters)", max=MAX_TEXT) if what == "reason"
                           else _("The note is too long (max %(max)s characters)", max=MAX_TEXT))
    return text


def _rule_for(session: Session, user: User, metric: Metric):
    return next((r for r in effective_rules(session, user, Resource.print) if r.metric is metric), None)


def quota_options(session: Session, user: User, now: datetime, tz: ZoneInfo) -> list[dict]:
    """What the quota form can offer: only metrics that actually limit the user, with the period the ADMIN set."""
    out = []
    for r in effective_rules(session, user, Resource.print):
        out.append({
            "metric": r.metric.value, "period": r.period.value, "limit": r.limit,
            "extra": active_grants(session, user, r.metric, now),
            "used": usage(session, user, r, now, tz), "window_end": window_end(r.period, now, tz),
        })
    return out


def _open_count(session: Session, user: User, now: datetime) -> int:
    return session.scalar(select(func.count(QuotaRequest.id)).where(
        QuotaRequest.user_id == user.id, QuotaRequest.status == RequestStatus.pending, QuotaRequest.expires_at > now,
    )) or 0


def _new_request(session: Session, user: User, kind: RequestKind, scope, params: dict, reason: str, now: datetime):
    if not user.enabled:
        raise RequestError(_("account disabled"))
    if _open_count(session, user, now) >= settings.max_open_requests:
        raise RequestError(_("you already have %(n)s open requests: wait for an answer or cancel one", n=settings.max_open_requests))
    req = QuotaRequest(user_id=user.id, kind=kind, scope=scope, params_json=params, reason=reason,
                       status=RequestStatus.pending, created_at=now,
                       expires_at=now + timedelta(days=settings.request_ttl_days))
    session.add(req)
    session.commit()
    return req


def create_quota_request(session: Session, user: User, metric: str, amount: int, scope: str, reason: str,
                         now: datetime) -> QuotaRequest:
    try:
        m, sc = Metric(metric), RequestScope(scope)
    except ValueError:
        raise RequestError(_("invalid request")) from None
    if not isinstance(amount, int) or not 1 <= amount <= MAX_AMOUNT:
        raise RequestError(_("the amount must be between 1 and %(max)s", max=MAX_AMOUNT))
    if _rule_for(session, user, m) is None:
        raise RequestError(_("no %(metric)s limit applies to you, there is nothing to ask for", metric=_(m.value)))
    # NB: the period is deliberately not a parameter. It comes from the rule the admin set.
    return _new_request(session, user, RequestKind.quota, sc, {"metric": m.value, "amount": amount},
                        _clean(reason, "reason"), now)


def create_group_request(session: Session, user: User, target_group_id: int, reason: str, now: datetime) -> QuotaRequest:
    group = session.get(Group, target_group_id)
    if group is None or not group.requestable:
        raise RequestError(_("that group can not be requested"))
    if user.group_id == group.id:
        raise RequestError(_("you are already in that group"))
    return _new_request(session, user, RequestKind.group_change, None, {"target_group_id": group.id},
                        _clean(reason, "reason"), now)


def cancel_request(session: Session, req: QuotaRequest, user: User, now: datetime) -> None:
    if req.user_id != user.id:
        raise RequestError(_("not your request"))
    done = session.execute(_update(QuotaRequest).where(
        QuotaRequest.id == req.id, QuotaRequest.status == RequestStatus.pending,
    ).values(status=RequestStatus.canceled, decided_at=now))
    session.commit()
    if done.rowcount != 1:
        raise RequestError(_("the request was already decided"))


def expire_requests(session: Session, now: datetime) -> int:
    done = session.execute(_update(QuotaRequest).where(
        QuotaRequest.status == RequestStatus.pending, QuotaRequest.expires_at <= now,
    ).values(status=RequestStatus.expired, decided_at=now))
    session.commit()
    return done.rowcount


def _make_grant(session: Session, user: User, metric: Metric, amount: int, scope: RequestScope, admin: User,
                now: datetime, tz: ZoneInfo, request_id: int | None, note: str | None) -> QuotaGrant:
    rule = _rule_for(session, user, metric)
    if rule is None:
        raise RequestError(_("no %(metric)s limit applies to %(user)s any more: nothing to extend", metric=_(metric.value), user=user.username))
    until = window_end(rule.period, now, tz) if scope is RequestScope.temporary else None
    grant = QuotaGrant(user_id=user.id, metric=metric, amount=amount, scope=scope, valid_from=now, valid_until=until,
                       request_id=request_id, granted_by=admin.id, note=note, created_at=now)
    session.add(grant)
    return grant


def approve_request(session: Session, req: QuotaRequest, admin: User, now: datetime, tz: ZoneInfo,
                    amount: int | None = None, scope: str | None = None, note: str = "") -> QuotaGrant | None:
    """Idempotent: the status flip is a single conditional UPDATE, so a double click or two admins at once
    grant once. The admin may change amount and scope of a quota request before approving."""
    note = _clean(note, "note", required=False)
    user = session.get(User, req.user_id)
    if user is None or not user.enabled:
        raise RequestError(_("the user is disabled"))
    if _aware(req.expires_at) <= now and req.status is RequestStatus.pending:
        expire_requests(session, now)
        raise RequestError(_("the request has expired"))
    claimed = session.execute(_update(QuotaRequest).where(
        QuotaRequest.id == req.id, QuotaRequest.status == RequestStatus.pending,
    ).values(status=RequestStatus.approved, decided_by=admin.id, decided_at=now, decision_note=note or None))
    if claimed.rowcount != 1:
        session.rollback()
        raise RequestError(_("the request was already decided"))
    grant = None
    try:
        if req.kind is RequestKind.quota:
            metric = Metric(req.params_json["metric"])
            amt = req.params_json["amount"] if amount is None else amount
            if not isinstance(amt, int) or not 1 <= amt <= MAX_AMOUNT:
                raise RequestError(_("the amount must be between 1 and %(max)s", max=MAX_AMOUNT))
            sc = req.scope if scope is None else RequestScope(scope)
            grant = _make_grant(session, user, metric, amt, sc, admin, now, tz, req.id, note or None)
            record(session, admin, "request.approve", "quota_request", req.id, user=user.username, kind="quota",
                   metric=metric.value, amount=amt, scope=sc.value, requested_amount=req.params_json["amount"],
                   requested_scope=req.scope.value)
        else:
            group = session.get(Group, req.params_json["target_group_id"])
            if group is None:
                raise RequestError(_("the requested group no longer exists"))
            old = user.group_id
            user.group_id = group.id
            record(session, admin, "request.approve", "quota_request", req.id, user=user.username,
                   kind="group_change", from_group_id=old, to_group_id=group.id)
        session.commit()
    except (RequestError, ValueError, KeyError):
        session.rollback()  # also undoes the status flip: a refused approval leaves the request pending
        raise
    return grant


def reject_request(session: Session, req: QuotaRequest, admin: User, now: datetime, note: str = "") -> None:
    note = _clean(note, "note", required=False)
    done = session.execute(_update(QuotaRequest).where(
        QuotaRequest.id == req.id, QuotaRequest.status == RequestStatus.pending,
    ).values(status=RequestStatus.rejected, decided_by=admin.id, decided_at=now, decision_note=note or None))
    if done.rowcount != 1:
        session.rollback()
        raise RequestError(_("the request was already decided"))
    record(session, admin, "request.reject", "quota_request", req.id, kind=req.kind.value, note=note)
    session.commit()


def create_grant(session: Session, admin: User, user: User, metric: str, amount: int, scope: str, note: str,
                 now: datetime, tz: ZoneInfo) -> QuotaGrant:
    """A grant the admin hands out without a request."""
    try:
        m, sc = Metric(metric), RequestScope(scope)
    except ValueError:
        raise RequestError(_("invalid grant")) from None
    if not isinstance(amount, int) or not 1 <= amount <= MAX_AMOUNT:
        raise RequestError(_("the amount must be between 1 and %(max)s", max=MAX_AMOUNT))
    grant = _make_grant(session, user, m, amount, sc, admin, now, tz, None, _clean(note, "note", required=False) or None)
    session.flush()
    record(session, admin, "grant.create", "quota_grant", grant.id, user=user.username, metric=m.value,
           amount=amount, scope=sc.value)
    session.commit()
    return grant


def revoke_grant(session: Session, grant: QuotaGrant, admin: User, now: datetime) -> None:
    done = session.execute(_update(QuotaGrant).where(QuotaGrant.id == grant.id, QuotaGrant.revoked_at.is_(None))
                           .values(revoked_at=now, revoked_by=admin.id))
    if done.rowcount != 1:
        session.rollback()
        raise RequestError(_("the grant was already revoked"))
    record(session, admin, "grant.revoke", "quota_grant", grant.id, user_id=grant.user_id, metric=grant.metric.value)
    session.commit()
