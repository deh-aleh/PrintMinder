"""Who may log in where.

  portal : any enabled user. A "local" account is checked against its argon2 hash; any other account is
           delegated to its provider (RADIUS). The provider is decided by the row in the database, never by
           the password: a local account can not be opened by the RADIUS server, whatever it says.
  print  : (IPP) a personal print key. With ipp_auth="keys+radius" a RADIUS user may also use the domain
           password (transition mode); local accounts never can.
"""

import logging
from datetime import datetime, timezone

from starlette.concurrency import run_in_threadpool

from app.auth import keys
from app.auth.passwords import verify_password
from app.auth.users import find_user, resolve_user
from app.config import settings
from app.db.models import User

log = logging.getLogger(__name__)
LOCAL = "local"


def normalize(username: str) -> str:
    return username.strip().lower()


def _radius(app):
    """The delegated provider (RADIUS) or None when the deployment is local-only."""
    return getattr(app.state, "auth", None)


def _lookup(app, name: str) -> User | None:
    with app.state.sessionmaker() as db:
        return find_user(db, name)


async def portal_login(app, username: str, password: str) -> User | None:
    name = normalize(username)
    if not name or not password:
        return None
    user = await run_in_threadpool(_lookup, app, name)
    provider = _radius(app)
    if user is None:
        # unknown name: only a delegated provider can vouch for a first-time user
        if provider is None or not settings.auto_create_users or not await provider.authenticate(username, password):
            await run_in_threadpool(verify_password, None, password)  # same cost as a real check
            return None
        return await run_in_threadpool(_create_delegated, app, provider.name, name)
    if user.provider == LOCAL:
        ok = await run_in_threadpool(verify_password, user.password_hash, password)
        return user if ok and user.enabled else None
    if provider is None or not await provider.authenticate(username, password):
        return None
    return user if user.enabled else None


def _create_delegated(app, provider_name: str, name: str) -> User | None:
    with app.state.sessionmaker() as db:
        user = resolve_user(db, provider_name, name, True, settings.default_group)
        # lost a race against a local account with the same name: the local one is not ours to hand out
        return user if user is not None and user.provider != LOCAL and user.enabled else None


def _check_key(app, name: str, key: str, ip: str | None) -> User | None:
    with app.state.sessionmaker() as db:
        user = find_user(db, name)
        if user is None or not user.enabled:
            return None
        return user if keys.verify_key(db, user, key, ip) is not None else None


async def print_login(app, username: str, secret: str, ip: str | None = None) -> User | None:
    """IPP Basic credentials -> User, or None."""
    name = normalize(username)
    if not name or not secret:
        return None
    user = await run_in_threadpool(_check_key, app, name, secret, ip)
    if user is not None:
        return user
    if settings.ipp_auth != "keys+radius":
        return None
    provider = _radius(app)
    existing = await run_in_threadpool(_lookup, app, name)
    if provider is None or (existing is not None and existing.provider == LOCAL):
        return None
    if not await provider.authenticate(username, secret):
        return None
    if existing is not None:
        return existing if existing.enabled else None
    return await run_in_threadpool(_create_delegated, app, provider.name, name) if settings.auto_create_users else None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
