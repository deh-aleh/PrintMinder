"""Notices for administrators (the bell in the portal), with a limit on how often the same one is reported.

A notice is identified by its kind and its source (for example "escl_anonymous_refused" and an IP address). The first time
it happens it is written to the database and to the log. After that, repeats from the same source are only counted
in memory until the interval has passed, so a client that retries 100 times a minute produces one line a day, not 100.
The interval depends on CUPSPL_LOG_LEVEL (a quieter log level means rarer reports) unless CUPSPL_NOTICE_INTERVAL is set:

    DEBUG   every minute     (for people looking for a problem)
    INFO    once a day       (default)
    WARNING every 3 days
    ERROR   every 7 days
"""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.config import settings
from app.db.models import Notice

log = logging.getLogger("app.notices")

BY_LEVEL = {"DEBUG": 60, "INFO": 24 * 3600, "WARNING": 3 * 24 * 3600, "ERROR": 7 * 24 * 3600, "CRITICAL": 7 * 24 * 3600}
MAX_OPEN_PER_KIND = 200   # sources are limited too: spoofed addresses must not fill the list
KEEP_DISMISSED = timedelta(days=90)
LOG_TEXT = {
    "escl_anonymous_refused": "scan request without credentials refused from %s (%d attempt(s) since the last report): "
                              "scans without login are off (CUPSPL_ESCL_ANONYMOUS=false)",
}

_lock = threading.Lock()
_state: dict[tuple[str, str], dict] = {}   # (kind, source) -> {"last": unix time of the last report, "pending": repeats since}


def interval() -> int:
    if settings.notice_interval > 0:
        return settings.notice_interval
    return BY_LEVEL.get(settings.log_level.upper(), BY_LEVEL["INFO"])


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def report(sm, kind: str, key: str, detail: dict | None = None, now: float | None = None) -> bool:
    """Count one more occurrence. Returns True when this one was written (and logged), False when it was only counted."""
    now = time.time() if now is None else now
    key = key[:128]
    wait = interval()
    with _lock:
        st = _state.get((kind, key))
        if st is None:  # after a restart: the database still knows when this source was last reported
            with sm() as db:
                last = db.scalar(select(func.max(Notice.last_at)).where(Notice.kind == kind, Notice.key == key))
            if last is not None and now - _aware(last).timestamp() < wait:
                st = _state[(kind, key)] = {"last": _aware(last).timestamp(), "pending": 0}
        if st is not None and now - st["last"] < wait:
            st["pending"] += 1
            return False
        pending = st["pending"] if st else 0
        _state[(kind, key)] = {"last": now, "pending": 0}
        if len(_state) > 2000:  # forget sources that are past their interval
            for k in [k for k, v in _state.items() if now - v["last"] >= wait]:
                del _state[k]
    when = datetime.fromtimestamp(now, timezone.utc)
    with sm() as db:
        row = db.scalars(select(Notice).where(Notice.kind == kind, Notice.key == key, Notice.dismissed_at.is_(None))).first()
        if row is not None:
            row.last_at, row.count, row.detail_json = when, row.count + pending + 1, detail or row.detail_json
        else:
            open_now = db.scalar(select(func.count(Notice.id)).where(Notice.kind == kind, Notice.dismissed_at.is_(None))) or 0
            if open_now < MAX_OPEN_PER_KIND:
                db.add(Notice(kind=kind, key=key, first_at=when, last_at=when, count=pending + 1, detail_json=detail))
        for old in db.scalars(select(Notice).where(Notice.dismissed_at < when - KEEP_DISMISSED)):
            db.delete(old)
        db.commit()
    if kind in LOG_TEXT:
        log.warning(LOG_TEXT[kind], key, pending + 1)
    else:
        log.warning("notice %s from %s (%d)", kind, key, pending + 1)
    return True


def pending(kind: str, key: str) -> int:
    """Repeats counted in memory and not yet written (shown beside the stored count)."""
    with _lock:
        st = _state.get((kind, key))
        return st["pending"] if st else 0


def unseen_count(sm, user_id: int) -> int:
    """Open notices that are new, or happened again, since this administrator last opened the list (the red dot)."""
    from app.db.models import User

    with sm() as db:
        seen = db.scalar(select(User.notices_seen_at).where(User.id == user_id))
        q = select(func.count(Notice.id)).where(Notice.dismissed_at.is_(None))
        if seen is not None:
            q = q.where(Notice.last_at > seen)
        return db.scalar(q) or 0
