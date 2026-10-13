"""Job accounting: atomically reserve a quota slot, then finalize once CUPS has answered."""

import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import JobKind, JobLog, JobState, Resource, User
from app.policy import control
from app.policy.engine import Decision, check_job

# check + insert must be one critical section or concurrent submissions overshoot the limit.
# The thread lock covers one process (and in-memory test DBs); _lock_quota covers many processes.
_submit_lock = threading.Lock()


def _lock_quota(session: Session, user_id: int) -> None:
    """Serialize quota decisions across processes, until the session commits."""
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")  # single writer: blocks other reservers
    elif dialect == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": user_id})


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def reserve(
    session: Session, user: User, printer: str | None, title: str | None, options: dict, tz: ZoneInfo,
    pages: int | None = None, kind: JobKind = JobKind.print,
) -> tuple[Decision, int]:
    """Check the quota and record the attempt. Allowed attempts count immediately (state=accepted).
    `pages` = counted pages of the document (copies included), recorded at once so concurrent jobs see them.
    A blocked printer or the maintenance mode refuses before any quota is looked at (and is audited as denied)."""
    now = now_utc()
    with _submit_lock:
        _lock_quota(session, user.id)
        why = control.block_reason(session, user, printer)
        decision = Decision(False, why) if why else check_job(session, user, Resource(kind.value), now, tz, pages)
        row = JobLog(
            ts=now, user_id=user.id, user_name=user.username, kind=kind, printer=printer, title=title,
            options_json=options or None, pages=pages if decision.allowed else None,
            state=JobState.accepted if decision.allowed else JobState.denied,
            denied_reason=None if decision.allowed else decision.reason,
        )
        session.add(row)
        session.commit()
    return decision, row.id


def finalize(session: Session, log_id: int, ok: bool, cups_job_id: int | None, reason: str | None = None) -> None:
    row = session.get(JobLog, log_id)
    if row is None:
        return
    if ok:
        row.cups_job_id = cups_job_id
    else:  # CUPS refused it: free the slot
        row.state = JobState.failed
        row.denied_reason = reason
    session.commit()


def attach_document(session: Session, user_id: int, cups_job_id: int, name: str | None, fmt: str | None,
                    pages: int | None = None) -> None:
    """Send-Document after Create-Job: the file name usually only shows up here."""
    row = session.scalars(
        select(JobLog).where(JobLog.user_id == user_id, JobLog.cups_job_id == cups_job_id)
        .order_by(JobLog.id.desc())
    ).first()
    if row is None:
        return
    opts = dict(row.options_json or {})
    if name:
        opts["document_name"] = name
        if not row.title or row.title == "untitled":
            row.title = name
    if fmt:
        opts["document_format"] = fmt
    if pages and not row.pages:
        row.pages = pages  # counted at Send-Document: the next job already sees them
    row.options_json = opts
    session.commit()
