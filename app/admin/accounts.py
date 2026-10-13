"""Administration: users, groups, limits, keys and the log of administrative actions."""

import logging
import re
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.common import (
    PAGE, back, current_admin, flash, get_db, localtime, parse_limit, render, verify_csrf,
)
from app.audit.adminlog import record
from app.auth import keys as keylib
from app.auth.groups import ADMIN_GROUP, set_admin, system_group_names
from app.auth.users import default_group_id, delete_user
from app.auth.passwords import hash_password, validate_new_password
from app.config import settings
from app.i18n import _, ngettext
from app.db.models import AdminAudit, Group, JobLog, Metric, Period, PrintKey, Resource, SubjectType, User
from app.policy.engine import active_grant_list, effective_limit, effective_rules, usage
from app.policy.rules import get_limits, set_limit

log = logging.getLogger("app.admin")
ACTIONS_PAGE = 30  # rows per page in the administrative log
router = APIRouter(prefix="/admin")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")


def _usage_lines(db: Session, user: User) -> list[str]:
    now, tz = datetime.now(timezone.utc), ZoneInfo(settings.timezone)
    return [_("%(used)s/%(limit)s %(metric)s (%(period)s)", used=usage(db, user, r, now, tz), limit=effective_limit(db, user, r, now),
              metric=_(r.metric.value), period=_(r.period.value))
            for r in effective_rules(db, user, Resource.print)]


def _other_admins(db: Session, user: User) -> int:
    return db.scalar(select(func.count(User.id)).where(User.is_admin, User.enabled, User.id != user.id)) or 0


def _protected_admin(db: Session, user: User, acting: User) -> str | None:
    """Why this account may not lose admin rights / be disabled, or None."""
    if user.id == acting.id:
        return _("You cannot disable or demote yourself")
    if user.username == settings.bootstrap_admin_username and user.provider == "local":
        return _("%(user)s is the emergency administrator: it can not be disabled or demoted", user=user.username)
    if user.is_admin and user.enabled and _other_admins(db, user) == 0:
        return _("That is the last administrator")
    return None


# ------------------------------------------------------------------ users

def _limit_view(db: Session, u: User, now) -> dict:
    """What the list shows for one user: effective limits (own or inherited from the group), active grants, usage."""
    rules = {r.metric: r for r in effective_rules(db, u, Resource.print)}
    own = get_limits(db, SubjectType.user, u.id)
    out = {"usage": _usage_lines(db, u)}
    for m in (Metric.jobs, Metric.pages):
        r = rules.get(m)
        inherited = bool(r) and m not in own
        grants = active_grant_list(db, u, m, now) if r else []
        # tooltip: where the limit comes from, then every active grant with its expiry
        tip = ([_("limit inherited from the group")] if inherited else []) + [
            f"+{g.amount} · " + (_("temporary, expires on %(date)s", date=localtime(g.valid_until, '%Y-%m-%d %H:%M')) if g.valid_until else _("permanent"))
            for g in grants]
        out[m.value] = {
            "limit": r.limit if r else None, "inherited": inherited,
            "extra": sum(g.amount for g in grants), "period": r.period.value if r else None, "tip": "\n".join(tip),
        }
    out["period"] = next((r.period.value for r in rules.values()), "weekly")
    return out


@router.get("/users", response_class=HTMLResponse)
def users(request: Request, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    group_names = {g.id: g.name for g in db.scalars(select(Group))}
    key_counts = dict(db.execute(select(PrintKey.user_id, func.count(PrintKey.id)).where(
        PrintKey.revoked_at.is_(None), (PrintKey.expires_at.is_(None)) | (PrintKey.expires_at > now))
        .group_by(PrintKey.user_id)).all())
    rows = [{"u": u, "group": group_names.get(u.group_id, "—"), "key_count": key_counts.get(u.id, 0),
             "view": _limit_view(db, u, now), "protected": _is_emergency(u)}
            for u in db.scalars(select(User).order_by(User.username))]
    groups = db.scalars(select(Group).where(Group.name != ADMIN_GROUP).order_by(Group.name)).all()  # administrators are made with the checkbox
    return render(request, "users.html", admin, rows=rows, groups=groups, default_group=settings.default_group)


def _is_admin_group(db: Session, group_id: int) -> bool:
    g = db.get(Group, group_id) if group_id else None
    return g is not None and g.name == ADMIN_GROUP


def _is_emergency(u: User) -> bool:
    return u.username == settings.bootstrap_admin_username and u.provider == "local"


def _providers(request: Request) -> list[str]:
    auth = getattr(request.app.state, "auth", None)
    return ["local"] + ([auth.name] if auth is not None else [])


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
def user_edit(request: Request, user_id: int, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404)
    v = _limit_view(db, u, datetime.now(timezone.utc))
    own = get_limits(db, SubjectType.user, u.id)
    return render(request, "user_edit.html", admin, u=u, view=v, groups=db.scalars(select(Group).order_by(Group.name)).all(),
                  jobs=own[Metric.jobs].limit if Metric.jobs in own else "",
                  pages=own[Metric.pages].limit if Metric.pages in own else "",
                  periods=[p.value for p in Period], providers=_providers(request), admin_group=ADMIN_GROUP,
                  protected=_is_emergency(u), is_self=u.id == admin.id)


def _temp_password() -> str:
    return secrets.token_urlsafe(12)


@router.post("/users/local", dependencies=[Depends(verify_csrf)])
def user_create_local(request: Request, username: str = Form(...), group_id: int = Form(0), password: str = Form(""),
                      is_admin: str = Form(""), admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    name = username.strip().lower()
    generated = not password
    pw = password or _temp_password()
    error = (
        _("Unknown group") if group_id and db.get(Group, group_id) is None else
        _('Group "%(group)s" is only for administrators: tick the administrator box instead', group=ADMIN_GROUP) if _is_admin_group(db, group_id) else
        _("Invalid username (letters, digits, dot, dash, underscore; max 63)") if not USERNAME_RE.match(name) else
        _("User %(name)s already exists", name=name) if db.scalars(select(User).where(User.username == name)).first() else
        None if generated else validate_new_password(pw, name)
    )
    if error:
        flash(request, error, "err")
        return back("/admin/users")
    user = User(provider="local", username=name, group_id=group_id or default_group_id(db, settings.default_group),
                password_hash=hash_password(pw), must_change_password=True,
                password_changed_at=datetime.now(timezone.utc))
    db.add(user)
    db.flush()
    if is_admin:
        set_admin(db, user, True)
    record(db, admin, "user.create", "user", user.id, username=name, provider="local", is_admin=bool(is_admin))
    db.commit()
    log.info("admin %s created local user %s", admin.username, name)
    return render(request, "secret_shown.html", admin, title=_("User %(name)s created", name=name), what=_("Temporary password"),
                  secret=pw, note=_("Give it to the user over a safe channel. They must choose their own at first login."),
                  next_url="/admin/users")


@router.post("/users", dependencies=[Depends(verify_csrf)])
def user_create(request: Request, username: str = Form(...), group_id: int = Form(0),
                admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Pre-register someone who will log in through the delegated provider (RADIUS)."""
    provider = getattr(request.app.state, "auth", None)
    name = username.strip().lower()
    if provider is None:
        flash(request, _("RADIUS is not configured: create a local user instead"), "err")
    elif group_id and db.get(Group, group_id) is None:
        flash(request, _("Unknown group"), "err")
    elif _is_admin_group(db, group_id):
        flash(request, _('Group "%(group)s" is only for administrators: make them administrator from their page', group=ADMIN_GROUP), "err")
    elif not name or len(name) > 128:
        flash(request, _("Invalid username"), "err")
    elif db.scalars(select(User).where(User.username == name)).first():
        flash(request, _("User %(name)s already exists", name=name), "err")
    else:
        user = User(provider=provider.name, username=name, group_id=group_id or default_group_id(db, settings.default_group))
        db.add(user)
        db.flush()
        record(db, admin, "user.create", "user", user.id, username=name, provider=provider.name)
        db.commit()
        log.info("admin %s created user %s", admin.username, name)
        flash(request, _("User %(name)s created", name=name))
    return back("/admin/users")


@router.post("/users/{user_id}", dependencies=[Depends(verify_csrf)])
def user_update(request: Request, user_id: int, group_id: int = Form(0), enabled: str = Form(""),
                is_admin: str = Form(""), jobs_limit: str = Form(""), pages_limit: str = Form(""),
                period: str = Form("weekly"), provider: str = Form(""),
                admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404)
    edit = f"/admin/users/{u.id}/edit"
    try:
        jl, pl, per = parse_limit(jobs_limit), parse_limit(pages_limit), Period(period)
    except ValueError as exc:
        flash(request, str(exc), "err")
        return back(edit)
    if group_id and db.get(Group, group_id) is None:
        flash(request, _("Unknown group"), "err")
        return back(edit)
    provider = provider or u.provider
    if provider not in _providers(request) and provider != u.provider:
        flash(request, _("Unknown or unavailable login method"), "err")
        return back(edit)
    if not enabled or not is_admin:  # disabling or demoting: never yourself, the emergency admin, or the last admin
        reason = _protected_admin(db, u, admin)
        if reason:
            flash(request, reason, "err")
            return back(edit)
    if provider != u.provider and _is_emergency(u):
        flash(request, _("%(user)s is the emergency administrator: it must stay a local account", user=u.username), "err")
        return back(edit)
    admin_group = db.scalars(select(Group).where(Group.name == ADMIN_GROUP)).first()
    changes = {}
    if u.enabled != bool(enabled):
        changes["enabled"] = bool(enabled)
    if u.is_admin != bool(is_admin):
        changes["is_admin"] = bool(is_admin)
        set_admin(db, u, bool(is_admin))  # administrators live in "administrator"; demoted ones go back to "default"
    elif (u.group_id or 0) != group_id:
        if admin_group is not None and group_id == admin_group.id and not u.is_admin:
            flash(request, _('Group "%(group)s" is only for administrators', group=ADMIN_GROUP), "err")
            return back(edit)
        if u.is_admin and (admin_group is None or group_id != admin_group.id):
            flash(request, _('Administrators stay in "%(group)s": remove the admin right first', group=ADMIN_GROUP), "err")
            return back(edit)
        changes["group_id"] = [u.group_id, group_id or None]
        u.group_id = group_id or None
    u.enabled = bool(enabled)
    temp = None
    if provider != u.provider:
        changes["provider"] = [u.provider, provider]
        if provider == "local":  # becomes a local account: a temporary password, shown once
            temp = _temp_password()
            u.password_hash, u.must_change_password = hash_password(temp), True
        else:  # handed over to RADIUS: the stored password must not remain a second way in
            u.password_hash, u.must_change_password = None, False
        u.provider = provider
        u.password_changed_at = datetime.now(timezone.utc)  # ends the user's current portal sessions
    set_limit(db, SubjectType.user, u.id, Metric.jobs, jl, per)
    set_limit(db, SubjectType.user, u.id, Metric.pages, pl, per)
    record(db, admin, "user.update", "user", u.id, username=u.username, limits={"jobs": jl, "pages": pl, "period": per.value},
           **changes)
    db.commit()
    log.info("admin %s updated user %s", admin.username, u.username)
    if temp:
        return render(request, "secret_shown.html", admin, title=_("%(user)s is now a local account", user=u.username),
                      what=_("Temporary password"), secret=temp,
                      note=_("The user must choose their own at the next login. Their print keys keep working."),
                      next_url="/admin/users")
    flash(request, _("Saved %(name)s", name=u.username))
    return back("/admin/users")


@router.get("/users/{user_id}/delete", response_class=HTMLResponse)
def user_delete_confirm(request: Request, user_id: int, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404)
    reason = _delete_blocked(db, u, admin)
    if reason:
        flash(request, reason, "err")
        return back(f"/admin/users/{u.id}/edit")
    jobs = db.scalar(select(func.count(JobLog.id)).where(JobLog.user_id == u.id)) or 0
    return render(request, "user_delete.html", admin, u=u, jobs=jobs)


def _delete_blocked(db: Session, u: User, acting: User) -> str | None:
    if u.id == acting.id:
        return _("You cannot delete yourself")
    if _is_emergency(u):
        return _("%(user)s is the emergency administrator: it can not be deleted", user=u.username)
    if u.is_admin and u.enabled and _other_admins(db, u) == 0:
        return _("That is the last administrator")
    return None


@router.post("/users/{user_id}/delete", dependencies=[Depends(verify_csrf)])
def user_delete(request: Request, user_id: int, confirm_name: str = Form(""), admin: User = Depends(current_admin),
                db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404)
    reason = _delete_blocked(db, u, admin)
    if reason is None and confirm_name.strip().lower() != u.username:
        reason = _("The name you typed does not match: nothing was deleted")
    if reason:
        flash(request, reason, "err")
        return back(f"/admin/users/{u.id}/delete")
    summary = delete_user(db, u)
    record(db, admin, "user.delete", "user", user_id, **summary)
    db.commit()
    log.info("admin %s deleted user %s", admin.username, summary["username"])
    flash(request, _("Account %(name)s deleted (%(n)s print record(s) kept in the audit)", name=summary["username"], n=summary["jobs_kept"]))
    return back("/admin/users")


@router.post("/users/{user_id}/password", dependencies=[Depends(verify_csrf)])
def user_reset_password(request: Request, user_id: int, admin: User = Depends(current_admin),
                        db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404)
    if u.provider != "local":
        flash(request, _("That account signs in through RADIUS: its password is managed there"), "err")
        return back("/admin/users")
    pw = _temp_password()
    u.password_hash, u.must_change_password = hash_password(pw), True
    u.password_changed_at = datetime.now(timezone.utc)  # ends the user's current portal sessions
    record(db, admin, "user.reset_password", "user", u.id, username=u.username)
    db.commit()
    return render(request, "secret_shown.html", admin, title=_("New password for %(user)s", user=u.username),
                  what=_("Temporary password"), secret=pw,
                  note=_("The user must choose a new one at the next login. Their print keys keep working."),
                  next_url="/admin/users")


@router.post("/users/{user_id}/revoke-keys", dependencies=[Depends(verify_csrf)])
def user_revoke_keys(request: Request, user_id: int, admin: User = Depends(current_admin),
                     db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404)
    n = keylib.revoke_all(db, u)
    record(db, admin, "user.revoke_keys", "user", u.id, username=u.username, revoked=n)
    db.commit()
    flash(request, _("%(n)s key(s) of %(user)s revoked", n=n, user=u.username))
    return back(f"/admin/users/{u.id}/keys")


@router.get("/users/{user_id}/keys", response_class=HTMLResponse)
def user_keys(request: Request, user_id: int, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404)
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(PrintKey).where(PrintKey.user_id == u.id).order_by(PrintKey.id.desc())).all()
    return render(request, "keys.html", admin, owner=u, keys=[{"k": k, "usable": keylib.key_is_usable(k, now)} for k in rows],
                  base=f"/admin/users/{u.id}/keys", own=False)


@router.post("/users/{user_id}/keys/{key_id}/revoke", dependencies=[Depends(verify_csrf)])
def user_key_revoke(request: Request, user_id: int, key_id: int, admin: User = Depends(current_admin),
                    db: Session = Depends(get_db)):
    k = db.get(PrintKey, key_id)
    if k is None or k.user_id != user_id:
        raise HTTPException(404)
    if keylib.revoke_key(db, k):
        record(db, admin, "key.revoke", "print_key", k.id, username=db.get(User, user_id).username, label=k.label)
        db.commit()
        flash(request, _("Key %(label)s revoked", label=repr(k.label)))
    return back(f"/admin/users/{user_id}/keys")


# ------------------------------------------------------------------ groups

def _delete_warning(name: str, members: int) -> str:
    if members:
        return ngettext("The group “%(name)s” has %(n)s user: it will be moved to the default group “%(group)s” (with that group's limits). Delete the group?",
                        "The group “%(name)s” has %(n)s users: they will be moved to the default group “%(group)s” (with that group's limits). Delete the group?",
                        members, name=name, group=settings.default_group)
    return _("Delete the group “%(name)s”? It has no users.", name=name)


def _group_row(db: Session, g: Group) -> dict:
    lim = get_limits(db, SubjectType.group, g.id)
    members = db.scalar(select(func.count(User.id)).where(User.group_id == g.id)) or 0
    return {
        "g": g, "members": members, "warning": _delete_warning(g.name, members),
        "jobs": lim[Metric.jobs].limit if Metric.jobs in lim else "",
        "pages": lim[Metric.pages].limit if Metric.pages in lim else "",
        "period": next((r.period.value for r in lim.values()), "weekly"),
    }


@router.get("/groups", response_class=HTMLResponse)
def groups(request: Request, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    rows = [_group_row(db, g) for g in db.scalars(select(Group).order_by(Group.name))]
    return render(request, "groups.html", admin, rows=rows, system=system_group_names())


@router.get("/groups/new", response_class=HTMLResponse)
def group_new(request: Request, admin: User = Depends(current_admin)):
    return render(request, "group_edit.html", admin, g=None, jobs="", pages="", period="weekly",
                  periods=[p.value for p in Period], system=system_group_names(), admin_group=ADMIN_GROUP, warning="")


@router.get("/groups/{group_id}/edit", response_class=HTMLResponse)
def group_edit(request: Request, group_id: int, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    g = db.get(Group, group_id)
    if g is None:
        raise HTTPException(404)
    r = _group_row(db, g)
    return render(request, "group_edit.html", admin, g=g, jobs=r["jobs"], pages=r["pages"], period=r["period"],
                  periods=[p.value for p in Period], system=system_group_names(), admin_group=ADMIN_GROUP,
                  warning=r["warning"])


@router.post("/groups", dependencies=[Depends(verify_csrf)])
def group_create(request: Request, name: str = Form(...), jobs_limit: str = Form(""), pages_limit: str = Form(""),
                 period: str = Form("weekly"), requestable: str = Form(""),
                 admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    name = name.strip()
    try:
        jl, pl, per = parse_limit(jobs_limit), parse_limit(pages_limit), Period(period)
    except ValueError as exc:
        flash(request, str(exc), "err")
        return back("/admin/groups/new")
    if not name or len(name) > 64:
        flash(request, _("Invalid group name"), "err")
    elif db.scalars(select(Group).where(Group.name == name)).first():
        flash(request, _("Group %(name)s already exists", name=name), "err")
    else:
        g = Group(name=name, requestable=bool(requestable))
        db.add(g)
        db.flush()
        set_limit(db, SubjectType.group, g.id, Metric.jobs, jl, per)
        set_limit(db, SubjectType.group, g.id, Metric.pages, pl, per)
        record(db, admin, "group.create", "group", g.id, name=name, requestable=g.requestable,
               limits={"jobs": jl, "pages": pl, "period": per.value})
        db.commit()
        log.info("admin %s created group %s", admin.username, name)
        flash(request, _("Group %(name)s created", name=name))
        return back("/admin/groups")
    return back("/admin/groups/new")


@router.post("/groups/{group_id}", dependencies=[Depends(verify_csrf)])
def group_update(request: Request, group_id: int, name: str = Form(""), jobs_limit: str = Form(""),
                 pages_limit: str = Form(""), period: str = Form("weekly"), requestable: str = Form(""),
                 admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    g = db.get(Group, group_id)
    if g is None:
        raise HTTPException(404)
    edit = f"/admin/groups/{g.id}/edit"
    try:
        jl, pl, per = parse_limit(jobs_limit), parse_limit(pages_limit), Period(period)
    except ValueError as exc:
        flash(request, str(exc), "err")
        return back(edit)
    old_name, new_name = g.name, name.strip()
    if new_name and new_name != old_name:
        if old_name in system_group_names():
            flash(request, _('"%(name)s" is a system group: it can not be renamed', name=old_name), "err")
            return back(edit)
        if len(new_name) > 64:
            flash(request, _("Invalid group name"), "err")
            return back(edit)
        if db.scalars(select(Group).where(Group.name == new_name)).first():
            flash(request, _("Group %(name)s already exists", name=new_name), "err")
            return back(edit)
        g.name = new_name
    g.requestable = bool(requestable)
    set_limit(db, SubjectType.group, g.id, Metric.jobs, jl, per)
    set_limit(db, SubjectType.group, g.id, Metric.pages, pl, per)
    extra = {"renamed_from": old_name} if g.name != old_name else {}
    record(db, admin, "group.update", "group", g.id, name=g.name, requestable=g.requestable,
           limits={"jobs": jl, "pages": pl, "period": per.value}, **extra)
    db.commit()
    log.info("admin %s updated group %s", admin.username, g.name)
    flash(request, _("Saved %(name)s", name=g.name))
    return back("/admin/groups")


@router.post("/groups/{group_id}/delete", dependencies=[Depends(verify_csrf)])
def group_delete(request: Request, group_id: int, admin: User = Depends(current_admin),
                 db: Session = Depends(get_db)):
    g = db.get(Group, group_id)
    if g is None:
        raise HTTPException(404)
    if g.name in system_group_names():
        flash(request, _('"%(name)s" is a system group: it can not be deleted', name=g.name), "err")
    else:
        # members are not left without a group: they go to the default one (and take its limits)
        members = db.scalars(select(User).where(User.group_id == g.id)).all()
        target = default_group_id(db, settings.default_group) if members else None
        for u in members:
            u.group_id = target
        set_limit(db, SubjectType.group, g.id, Metric.jobs, None)
        set_limit(db, SubjectType.group, g.id, Metric.pages, None)
        record(db, admin, "group.delete", "group", g.id, name=g.name, moved_users=[u.username for u in members],
               moved_to=settings.default_group if members else None)
        db.delete(g)
        db.commit()
        log.info("admin %s deleted group %s (%d user(s) moved to %s)", admin.username, g.name, len(members), settings.default_group)
        flash(request, _("Group %(name)s deleted", name=g.name) + (_("; %(n)s user(s) moved to %(group)s", n=len(members), group=settings.default_group) if members else ""))
    return back("/admin/groups")


# ------------------------------------------------------------------ log of administrative actions

@router.get("/actions", response_class=HTMLResponse)
def actions(request: Request, actor: str = "", action: str = "", page: int = 1,
            admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    page = max(page, 1)
    stmt = select(AdminAudit)
    if actor.strip():
        stmt = stmt.where(AdminAudit.actor_name.contains(actor.strip().lower(), autoescape=True))
    if action.strip():
        stmt = stmt.where(AdminAudit.action.contains(action.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AdminAudit.id.desc()).limit(ACTIONS_PAGE).offset((page - 1) * ACTIONS_PAGE)).all()
    # what the two filter boxes suggest: the administrators, and the actions that really occur in the log
    actors = list(db.scalars(select(User.username).where(User.is_admin).order_by(User.username)))
    action_names = list(db.scalars(select(AdminAudit.action).distinct().order_by(AdminAudit.action)))
    return render(request, "actions.html", admin, rows=rows, total=total, page=page, pages=max(1, -(-total // ACTIONS_PAGE)),
                  f={"actor": actor, "action": action}, actors=actors, action_names=action_names)
