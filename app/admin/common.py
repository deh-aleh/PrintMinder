"""Shared pieces of the portal: templates, session/CSRF dependencies, helpers."""

import hmac
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import i18n
from app.backup.core import app_version
from app.config import settings
from app.db.models import User
from app.policy.rules import MAX_LIMIT

templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))
PAGE = 50


def localtime(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:  # SQLite returns naive; we store UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(settings.timezone)).strftime(fmt)


def isotime(value: str | None) -> str:
    """localtime() for a timestamp that was stored as text (ISO 8601) inside a notice."""
    try:
        return localtime(datetime.fromisoformat(value)) if value else ""
    except ValueError:
        return ""


templates.env.filters["localtime"] = localtime
templates.env.filters["isotime"] = isotime
templates.env.globals.update(_=i18n.html_gettext, _p=i18n.html_pgettext, _t=i18n.plain_gettext, _js=i18n.raw_gettext, ngettext=i18n.html_ngettext, lang=i18n.current, languages=i18n.LANGUAGES)


def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


def session_stamp(user: User) -> str:
    """Changes whenever the password changes, which ends every other session of that user."""
    dt = user.password_changed_at
    if dt is None:
        return ""
    # SQLite hands datetimes back without tzinfo; we store UTC, so both forms must give the same stamp
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if user is None or not user.enabled or request.session.get("stamp", "") != session_stamp(user):
        request.session.clear()
        raise HTTPException(303, headers={"Location": "/admin/login"})
    if request.session.get("lang") != (user.language or ""):  # chosen on another device since this session started
        request.session["lang"] = user.language or ""
    if user.must_change_password and request.url.path != "/me/password":
        raise HTTPException(303, headers={"Location": "/me/password"})
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "administrators only")
    return user


async def verify_csrf(request: Request, csrf_token: str = Form("")) -> None:
    expected = request.session.get("csrf", "")
    if not expected or not hmac.compare_digest(expected, csrf_token):
        raise HTTPException(403, "invalid CSRF token")


def flash(request: Request, msg: str, kind: str = "ok") -> None:
    # reassign: Starlette only notices changes to top-level keys, not in-place list mutation
    request.session["flash"] = [*request.session.get("flash", []), [kind, msg]]


def render(request: Request, name: str, user: User | None = None, status_code: int = 200, **ctx) -> HTMLResponse:
    ctx.update(me=user, csrf=request.session.get("csrf", ""), flashes=request.session.pop("flash", []),
               radius_enabled=settings.radius_enabled,
               pending_requests=_pending_requests(request) if user is not None and user.is_admin else 0,
               notices_unseen=_notices_unseen(request, user.id) if user is not None and user.is_admin else 0,
               maintenance=_maintenance(request) if user is not None else False,
               update_info=getattr(request.app.state, "update_info", None) if user is not None and user.is_admin else None,
               app_version=app_version())
    resp = templates.TemplateResponse(request, name, ctx, status_code=status_code)
    resp.headers["Cache-Control"] = "no-store"  # pages may carry one-time secrets (new keys, temporary passwords)
    return resp


def _pending_requests(request: Request) -> int:
    from sqlalchemy import func, select

    from app.db.models import QuotaRequest, RequestStatus

    with request.app.state.sessionmaker() as db:
        return db.scalar(select(func.count(QuotaRequest.id)).where(
            QuotaRequest.status == RequestStatus.pending,
            QuotaRequest.expires_at > datetime.now(timezone.utc))) or 0


def _notices_unseen(request: Request, user_id: int) -> int:
    from app import notices

    return notices.unseen_count(request.app.state.sessionmaker, user_id)


def _maintenance(request: Request) -> bool:
    from app.policy.control import is_maintenance

    with request.app.state.sessionmaker() as db:
        return is_maintenance(db)


def safe_next(path: str, default: str) -> str:
    """Where to go after a form: only paths of this site (no open redirect)."""
    return path if path.startswith("/") and not path.startswith("//") and "\\" not in path else default


def back(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def parse_limit(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    if not (raw.isascii() and raw.isdigit()):
        raise ValueError(i18n.gettext("invalid limit %(value)s", value=repr(raw)))
    value = int(raw)
    if value > MAX_LIMIT:
        raise ValueError(i18n.gettext("limit too large (max %(max)s)", max=MAX_LIMIT))
    return value


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def portal_base(request: Request) -> str:
    """Public address of the portal, for messages that tell people where to go."""
    if settings.portal_url:
        return settings.portal_url.rstrip("/")
    return f"https://{request.headers.get('host', 'localhost')}"
