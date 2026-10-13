"""Personal print keys. A key is a random secret the user pastes into the OS print dialog instead of the
domain password. High entropy, so a fast hash (sha256) is the right tool: a slow one would only make every
one of the 3-4 requests of a print job expensive and open a CPU-exhaustion hole."""

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PrintKey, User
from app.i18n import _

KEY_TAG = "cpk-"
MAX_LABEL = 64
MAX_KEYS_PER_USER = 20
TOUCH_EVERY = 60.0  # seconds: last_used is informational, not worth a DB write per request

_last_touch: dict[int, float] = {}


def hash_key(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def create_key(session: Session, user: User, label: str, ttl_days: int | None, now: datetime | None = None
               ) -> tuple[PrintKey, str]:
    """Returns (row, plaintext). The plaintext exists only in this return value: show it once."""
    label = label.strip()
    if not label or len(label) > MAX_LABEL:
        raise ValueError(_("the label must be 1-%(n)s characters", n=MAX_LABEL))
    active = session.scalars(select(PrintKey).where(PrintKey.user_id == user.id, PrintKey.revoked_at.is_(None))).all()
    if len(active) >= MAX_KEYS_PER_USER:
        raise ValueError(_("at most %(n)s active keys per user: revoke some first", n=MAX_KEYS_PER_USER))
    now = now or datetime.now(timezone.utc)
    plain = KEY_TAG + secrets.token_urlsafe(24)  # 192 bits
    row = PrintKey(
        user_id=user.id, label=label, key_prefix=plain[:8], key_hash=hash_key(plain), created_at=now,
        expires_at=now + timedelta(days=ttl_days) if ttl_days else None,
    )
    session.add(row)
    session.commit()
    return row, plain


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite drops tzinfo; we store UTC


def key_is_usable(row: PrintKey, now: datetime) -> bool:
    expires = _aware(row.expires_at)
    return row.revoked_at is None and (expires is None or now < expires)


def verify_key(session: Session, user: User, plain: str, ip: str | None = None, now: datetime | None = None
               ) -> PrintKey | None:
    """The key belongs to this user, is not revoked and has not expired."""
    if not plain.startswith(KEY_TAG) or len(plain) > 128:
        return None
    now = now or datetime.now(timezone.utc)
    row = session.scalars(select(PrintKey).where(PrintKey.key_hash == hash_key(plain))).first()
    if row is None or row.user_id != user.id or not key_is_usable(row, now):
        return None
    mono = time.monotonic()
    if mono - _last_touch.get(row.id, -TOUCH_EVERY) >= TOUCH_EVERY:
        _last_touch[row.id] = mono
        row.last_used_at, row.last_used_ip = now, (ip or "")[:64] or None
        session.commit()
    return row


def revoke_key(session: Session, row: PrintKey, now: datetime | None = None) -> bool:
    if row.revoked_at is not None:
        return False
    row.revoked_at = now or datetime.now(timezone.utc)
    session.commit()
    return True


def revoke_all(session: Session, user: User, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    rows = session.scalars(select(PrintKey).where(PrintKey.user_id == user.id, PrintKey.revoked_at.is_(None))).all()
    for r in rows:
        r.revoked_at = now
    session.commit()
    return len(rows)


def ttl_days_for(user: User, radius_days: int, local_days: int) -> int:
    return local_days if user.provider == "local" else radius_days
