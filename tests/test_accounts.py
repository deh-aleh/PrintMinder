"""Phase 1: local accounts, the first-run administrator, user/group administration, optional RADIUS."""

import pytest
from sqlalchemy import select

from app.auth import bootstrap
from app.auth.passwords import hash_password, validate_new_password, verify_password
from app.config import settings
from app.db.models import AdminAudit, User
from tests.conftest import StubRadius, csrf_of_page, make_user, portal_login

ORCH = "cups_orchestrator"
GOOD = "correct horse battery"


def user_row(cl, name):
    with cl.sm() as s:
        return s.scalars(select(User).where(User.username == name)).first()


def audit_actions(cl):
    with cl.sm() as s:
        return [a.action for a in s.scalars(select(AdminAudit).order_by(AdminAudit.id))]


# ---------------------------------------------------------------- passwords

def test_password_policy():
    assert validate_new_password("short", "x")
    assert validate_new_password("a" * 12, "x") is not None                  # too repetitive
    assert validate_new_password("MyUserName1234", "myusername1234") is not None
    assert validate_new_password("x" * 300, "x") is not None
    assert validate_new_password(GOOD, "bob") is None


def test_hash_is_argon2_and_verifies_in_constant_shape():
    h = hash_password(GOOD)
    assert h.startswith("$argon2id$") and GOOD not in h
    assert verify_password(h, GOOD) and not verify_password(h, GOOD + "x")
    assert not verify_password(None, GOOD)               # unknown account: false, but did the same work
    assert not verify_password("not a hash", GOOD)       # corrupted row never raises


# ---------------------------------------------------------------- first-run administrator

async def test_bootstrap_creates_passwordless_orchestrator_with_a_code(portal):
    code = bootstrap.ensure_orchestrator(portal.sm)
    assert code and len(code) >= 16
    u = user_row(portal, ORCH)
    assert (u.provider, u.is_admin, u.enabled, u.password_hash) == ("local", True, True, None)
    assert bootstrap.ensure_orchestrator(portal.sm) not in (None, code)   # a restart prints a fresh code
    with portal.sm() as s:
        u = s.scalars(select(User).where(User.username == ORCH)).one()
        u.password_hash = hash_password(GOOD)
        s.commit()
    assert bootstrap.ensure_orchestrator(portal.sm) is None               # nothing pending once it has a password


async def test_bootstrap_can_be_switched_off(portal, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_admin", False)
    assert bootstrap.ensure_orchestrator(portal.sm) is None and user_row(portal, ORCH) is None


async def test_setup_page_exists_only_while_pending(portal):
    assert (await portal.get("/admin/setup")).status_code == 404
    portal.app.state.setup_code = "the-code"
    assert (await portal.get("/admin/setup")).status_code == 200
    assert "/admin/setup" in (await portal.get("/admin/login")).text       # the login page points to it


async def test_setup_flow_sets_the_password_once(portal):
    bootstrap_code = bootstrap.ensure_orchestrator(portal.sm)
    portal.app.state.setup_code = bootstrap_code
    bad = await portal.post("/admin/setup", data={"code": "wrong", "password": GOOD, "confirm": GOOD})
    assert bad.status_code == 303 and user_row(portal, ORCH).password_hash is None      # wrong code
    r = await portal.post("/admin/setup", data={"code": bootstrap_code, "password": GOOD, "confirm": GOOD + "x"})
    assert user_row(portal, ORCH).password_hash is None                                   # passwords differ
    r = await portal.post("/admin/setup", data={"code": bootstrap_code, "password": "short", "confirm": "short"})
    assert user_row(portal, ORCH).password_hash is None                                   # too weak
    r = await portal.post("/admin/setup", data={"code": bootstrap_code, "password": GOOD, "confirm": GOOD})
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"
    assert verify_password(user_row(portal, ORCH).password_hash, GOOD)
    assert "admin.setup" in audit_actions(portal)
    # the code is burned: neither page nor POST works any more
    assert (await portal.get("/admin/setup")).status_code == 404
    again = await portal.post("/admin/setup", data={"code": bootstrap_code, "password": GOOD + "!", "confirm": GOOD + "!"})
    assert again.status_code == 404 and verify_password(user_row(portal, ORCH).password_hash, GOOD)
    assert (await portal_login(portal, ORCH, GOOD)).headers["location"] == "/admin/"


async def test_setup_code_guessing_is_throttled(portal):
    portal.app.state.setup_code = "right-code-1234567890"
    for i in range(5):
        await portal.post("/admin/setup", data={"code": f"guess{i}", "password": GOOD, "confirm": GOOD})
    r = await portal.post("/admin/setup", data={"code": "right-code-1234567890", "password": GOOD, "confirm": GOOD})
    assert r.status_code == 303 and r.headers["location"] == "/admin/setup"     # locked out, even with the right code
    assert portal.app.state.setup_code == "right-code-1234567890"


# ---------------------------------------------------------------- logging in

async def test_local_login_and_where_each_kind_of_user_lands(portal):
    make_user(portal.sm, "boss", password=GOOD, admin=True)
    make_user(portal.sm, "ann", password=GOOD)
    assert (await portal_login(portal, "ann", GOOD + "x")).headers["location"] == "/admin/login"
    assert (await portal_login(portal, "ann", GOOD)).headers["location"] == "/me"
    assert (await portal.get("/admin/jobs")).status_code == 403
    await portal.post("/admin/logout", data={"csrf_token": await csrf_of_page(portal)})
    assert (await portal_login(portal, "BOSS ", GOOD)).headers["location"] == "/admin/"
    assert (await portal.get("/admin/jobs")).status_code == 200
    assert "login" in audit_actions(portal)                                          # admin logins are recorded


async def test_disabled_and_unknown_local_users_cannot_log_in(portal):
    make_user(portal.sm, "off", password=GOOD, enabled=False)
    assert (await portal_login(portal, "off", GOOD)).headers["location"] == "/admin/login"
    assert (await portal_login(portal, "ghost", GOOD)).headers["location"] == "/admin/login"


async def test_radius_cannot_open_a_local_account(portal):
    """The provider is decided by the row in the database, never by who says yes."""
    make_user(portal.sm, "rad", password=GOOD)                    # LOCAL account that happens to share a RADIUS name
    assert (await portal_login(portal, "rad", "radpw")).headers["location"] == "/admin/login"   # RADIUS would say yes
    assert (await portal_login(portal, "rad", GOOD)).headers["location"] == "/me"                # the local password works


async def test_radius_user_is_created_at_first_login_and_name_collisions_are_refused(portal):
    assert user_row(portal, "rad") is None
    assert (await portal_login(portal, "rad", "radpw")).headers["location"] == "/me"
    u = user_row(portal, "rad")
    assert u.provider == "radius" and u.password_hash is None
    # a local user can not take a name that is already somebody else's
    make_user(portal.sm, "boss", password=GOOD, admin=True)
    await portal.post("/admin/logout", data={"csrf_token": await csrf_of_page(portal)})
    await portal_login(portal, "boss", GOOD)
    token = await csrf_of_page(portal, "/admin/users")
    r = await portal.post("/admin/users/local", data={"username": "rad", "csrf_token": token})
    assert r.status_code == 303
    assert user_row(portal, "rad").provider == "radius"


async def test_without_radius_only_local_accounts_exist(portal):
    portal.app.state.auth = None
    make_user(portal.sm, "boss", password=GOOD, admin=True)
    assert (await portal_login(portal, "rad", "radpw")).headers["location"] == "/admin/login"
    assert user_row(portal, "rad") is None
    await portal_login(portal, "boss", GOOD)
    token = await csrf_of_page(portal, "/admin/users")
    html = (await portal.get("/admin/users")).text
    assert "Pre-registra utente RADIUS" not in html and "Nuovo utente locale" in html
    await portal.post("/admin/users", data={"username": "x", "csrf_token": token})
    assert user_row(portal, "x") is None                                              # no provider to pre-register for


# ---------------------------------------------------------------- forced password change

async def test_temporary_password_forces_a_change_and_ends_other_sessions(portal):
    make_user(portal.sm, "tmp", password="Temp-password-1", must_change=True)
    first = await portal_login(portal, "tmp", "Temp-password-1")
    assert first.headers["location"] == "/me/password"
    assert (await portal.get("/me")).status_code == 303 and (await portal.get("/me")).headers["location"] == "/me/password"
    token = await csrf_of_page(portal, "/me/password")
    for new, current in (("short", "Temp-password-1"), ("Temp-password-1", "Temp-password-1"), ("a-fine-new-pass1", "wrong")):
        await portal.post("/me/password", data={"current": current, "new": new, "confirm": new, "csrf_token": token})
        assert user_row(portal, "tmp").must_change_password                              # nothing accepted
    # a second browser logged in with the same temporary password
    import httpx
    other = httpx.AsyncClient(transport=httpx.ASGITransport(app=portal.app, client=("10.0.0.8", 1)), base_url="https://gw.test")
    async with other:
        await other.post("/admin/login", data={"username": "tmp", "password": "Temp-password-1"})
        r = await portal.post("/me/password", data={"current": "Temp-password-1", "new": "a-fine-new-pass1",
                                                    "confirm": "a-fine-new-pass1", "csrf_token": token})
        assert r.status_code == 303 and r.headers["location"] == "/me"
        assert not user_row(portal, "tmp").must_change_password
        assert (await portal.get("/me")).status_code == 200                              # this session survives
        assert (await other.get("/me")).status_code == 303                               # the other one is ended


async def test_radius_users_have_no_password_page(portal):
    await portal_login(portal, "rad", "radpw")
    r = await portal.get("/me/password")
    assert r.status_code == 303 and r.headers["location"] == "/me"


# ---------------------------------------------------------------- administering users and groups

@pytest.fixture
async def boss(portal):
    make_user(portal.sm, "boss", password=GOOD, admin=True)
    make_user(portal.sm, ORCH, password=GOOD, admin=True)
    await portal_login(portal, "boss", GOOD)
    portal.token = await csrf_of_page(portal, "/admin/users")
    return portal


@pytest.mark.usefixtures("english")
async def test_admin_creates_a_local_user_whose_temporary_password_is_shown_once(boss):
    r = await boss.post("/admin/users/local", data={"username": " NewGuy ", "csrf_token": boss.token})
    assert r.status_code == 200 and "Temporary password" in r.text
    temp = re.search(r'class="secret">([^<]+)<', r.text).group(1)
    u = user_row(boss, "newguy")
    assert u.provider == "local" and u.must_change_password and verify_password(u.password_hash, temp)
    assert temp not in (await boss.get("/admin/users")).text                          # never shown again
    assert "user.create" in audit_actions(boss)
    assert "no-store" in r.headers["cache-control"]


async def test_admin_user_creation_validation(boss):
    for name in ("", "a b", "-x", "x" * 80, "<script>"):
        await boss.post("/admin/users/local", data={"username": name, "csrf_token": boss.token})
    await boss.post("/admin/users/local", data={"username": "weak", "password": "short", "csrf_token": boss.token})
    await boss.post("/admin/users/local", data={"username": "grp", "group_id": "999", "csrf_token": boss.token})
    with boss.sm() as s:
        assert [u.username for u in s.scalars(select(User).order_by(User.username))] == ["boss", ORCH]
    r = await boss.post("/admin/users/local", data={"username": "adm", "password": GOOD, "is_admin": "1",
                                                    "csrf_token": boss.token})
    assert user_row(boss, "adm").is_admin and verify_password(user_row(boss, "adm").password_hash, GOOD)


async def test_admin_resets_a_local_password_and_not_a_radius_one(boss):
    make_user(boss.sm, "ann", password=GOOD)
    make_user(boss.sm, "radu", provider="radius")
    uid = user_row(boss, "ann").id
    r = await boss.post(f"/admin/users/{uid}/password", data={"csrf_token": boss.token})
    temp = re.search(r'class="secret">([^<]+)<', r.text).group(1)
    u = user_row(boss, "ann")
    assert u.must_change_password and verify_password(u.password_hash, temp) and not verify_password(u.password_hash, GOOD)
    await boss.post(f"/admin/users/{user_row(boss, 'radu').id}/password", data={"csrf_token": boss.token})
    assert user_row(boss, "radu").password_hash is None
    assert "user.reset_password" in audit_actions(boss)


async def test_the_emergency_admin_can_not_be_disabled_or_demoted(boss):
    orch = user_row(boss, ORCH).id
    for form in ({"is_admin": "1"}, {"enabled": "1"}, {}):                           # disable / demote / both
        await boss.post(f"/admin/users/{orch}", data={**form, "csrf_token": boss.token})
        u = user_row(boss, ORCH)
        assert u.enabled and u.is_admin


async def test_other_admins_can_be_demoted_but_never_yourself(boss):
    make_user(boss.sm, "other", password=GOOD, admin=True)
    oid, bid = user_row(boss, "other").id, user_row(boss, "boss").id
    await boss.post(f"/admin/users/{oid}", data={"enabled": "1", "csrf_token": boss.token})
    assert not user_row(boss, "other").is_admin
    await boss.post(f"/admin/users/{bid}", data={"enabled": "1", "csrf_token": boss.token})   # demote myself
    await boss.post(f"/admin/users/{bid}", data={"is_admin": "1", "csrf_token": boss.token})  # disable myself
    assert user_row(boss, "boss").is_admin and user_row(boss, "boss").enabled


@pytest.mark.usefixtures("english")
def test_the_last_enabled_admin_is_protected_even_from_a_non_admin_caller(portal):
    """Defence in depth for races (two admins removing each other at once)."""
    from app.admin.accounts import _protected_admin

    only = make_user(portal.sm, "only", password=GOOD, admin=True)
    nobody = make_user(portal.sm, "plain", password=GOOD)
    with portal.sm() as s:
        assert "last administrator" in _protected_admin(s, s.get(User, only), s.get(User, nobody))
        make_user(portal.sm, "second", password=GOOD, admin=True)
        assert _protected_admin(s, s.get(User, only), s.get(User, nobody)) is None
        assert "yourself" in _protected_admin(s, s.get(User, only), s.get(User, only))


async def test_group_and_user_changes_leave_an_admin_trail(boss):
    await boss.post("/admin/groups", data={"name": "staff", "csrf_token": boss.token})
    make_user(boss.sm, "ann", password=GOOD)
    uid = user_row(boss, "ann").id
    await boss.post(f"/admin/users/{uid}", data={"enabled": "1", "jobs_limit": "5", "csrf_token": boss.token})
    acts = audit_actions(boss)
    assert "group.create" in acts and "user.update" in acts
    with boss.sm() as s:
        a = s.scalars(select(AdminAudit).where(AdminAudit.action == "user.update")).one()
        assert a.actor_name == "boss" and a.detail_json["limits"]["jobs"] == 5


async def test_admin_pages_refuse_plain_users_and_csrf_is_required(boss):
    make_user(boss.sm, "ann", password=GOOD)
    uid = user_row(boss, "ann").id
    r = await boss.post("/admin/users/local", data={"username": "nope"})
    assert r.status_code == 403 and user_row(boss, "nope") is None                    # no CSRF token


import re  # noqa: E402  (used by the helpers above)
