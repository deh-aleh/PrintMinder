"""Phase 2: personal print keys and the two IPP authentication modes."""

import base64
import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.auth import keys
from app.config import settings
from app.db.models import AdminAudit, JobLog, PrintKey, User
from app.ipp import codec as c
from tests.conftest import (
    CUPS_TEST_URL, StubRadius, csrf_of_page, make_user, portal_login, requires_cups,
)

GOOD = "correct horse battery"
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode(), "Content-Type": "application/ipp"}


def new_key(sm, username, label="laptop", ttl=30, now=NOW):
    with sm() as s:
        user = s.scalars(select(User).where(User.username == username)).one()
        row, plain = keys.create_key(s, user, label, ttl, now)
        return row.id, plain


def check(sm, username, plain, now=NOW):
    with sm() as s:
        user = s.scalars(select(User).where(User.username == username)).one()
        return keys.verify_key(s, user, plain, "10.1.1.1", now)


# ---------------------------------------------------------------- the key library

def test_only_the_hash_is_stored_and_the_key_has_enough_entropy(portal):
    make_user(portal.sm, "ann", password=GOOD)
    kid, plain = new_key(portal.sm, "ann")
    assert plain.startswith("cpk-") and len(plain) >= 32
    with portal.sm() as s:
        row = s.get(PrintKey, kid)
        assert plain not in repr(row.__dict__) and row.key_hash == keys.hash_key(plain) and len(row.key_hash) == 64
        assert row.key_prefix == plain[:8]
    assert new_key(portal.sm, "ann")[1] != plain                                      # random each time


def test_a_key_is_valid_for_its_owner_only_and_until_expiry_or_revocation(portal):
    make_user(portal.sm, "ann", password=GOOD)
    make_user(portal.sm, "bob", password=GOOD)
    kid, plain = new_key(portal.sm, "ann", ttl=10)
    assert check(portal.sm, "ann", plain)
    assert not check(portal.sm, "bob", plain)                                         # somebody else's key
    assert not check(portal.sm, "ann", plain + "x") and not check(portal.sm, "ann", "cpk-nope")
    assert not check(portal.sm, "ann", "x" * 200) and not check(portal.sm, "ann", "")
    assert check(portal.sm, "ann", plain, now=NOW + timedelta(days=9, hours=23))
    assert not check(portal.sm, "ann", plain, now=NOW + timedelta(days=10, seconds=1))  # expired
    with portal.sm() as s:
        assert keys.revoke_key(s, s.get(PrintKey, kid)) and not keys.revoke_key(s, s.get(PrintKey, kid))
    assert not check(portal.sm, "ann", plain)                                          # revoked


@pytest.mark.usefixtures("english")
def test_limits_and_validation(portal):
    make_user(portal.sm, "ann", password=GOOD)
    with portal.sm() as s:
        user = s.scalars(select(User)).one()
        for bad in ("", "   ", "x" * 65):
            with pytest.raises(ValueError):
                keys.create_key(s, user, bad, 30)
        for i in range(keys.MAX_KEYS_PER_USER):
            keys.create_key(s, user, f"k{i}", 30)
        with pytest.raises(ValueError, match="at most"):
            keys.create_key(s, user, "one too many", 30)
        assert keys.revoke_all(s, user) == keys.MAX_KEYS_PER_USER
        keys.create_key(s, user, "fresh", 30)                                         # revoked ones free the slots


def test_last_used_is_recorded_but_not_on_every_request(portal, monkeypatch):
    make_user(portal.sm, "ann", password=GOOD)
    kid, plain = new_key(portal.sm, "ann")
    clock = [1000.0]
    monkeypatch.setattr(keys.time, "monotonic", lambda: clock[0])
    keys._last_touch.clear()
    check(portal.sm, "ann", plain)
    with portal.sm() as s:
        first = s.get(PrintKey, kid).last_used_at
        assert first is not None and s.get(PrintKey, kid).last_used_ip == "10.1.1.1"
    clock[0] += 10
    check(portal.sm, "ann", plain, now=NOW + timedelta(minutes=5))
    with portal.sm() as s:
        assert s.get(PrintKey, kid).last_used_at == first                             # within a minute: no write
    clock[0] += 61
    check(portal.sm, "ann", plain, now=NOW + timedelta(minutes=6))
    with portal.sm() as s:
        assert s.get(PrintKey, kid).last_used_at != first


# ---------------------------------------------------------------- the portal pages

async def test_key_is_shown_once_with_the_right_lifetime_per_kind_of_account(portal):
    make_user(portal.sm, "loc", password=GOOD)
    await portal_login(portal, "loc", GOOD)
    token = await csrf_of_page(portal)
    r = await portal.post("/me/keys", data={"label": "my laptop", "csrf_token": token})
    plain = re.search(r'class="secret">([^<]+)<', r.text).group(1)
    assert plain.startswith("cpk-") and "no-store" in r.headers["cache-control"]
    page = (await portal.get("/me/keys")).text
    assert plain not in page and plain[:8] in page and "my laptop" in page            # only the prefix is listed
    with portal.sm() as s:
        row = s.scalars(select(PrintKey)).one()
        assert abs((row.expires_at.replace(tzinfo=timezone.utc) - row.created_at.replace(tzinfo=timezone.utc)).days
                   - settings.key_ttl_days_local) <= 1
    await portal.post("/admin/logout", data={"csrf_token": token})
    await portal_login(portal, "rad", "radpw")                                         # RADIUS-backed: shorter life
    token = await csrf_of_page(portal)
    await portal.post("/me/keys", data={"label": "phone", "csrf_token": token})
    with portal.sm() as s:
        row = s.scalars(select(PrintKey).join(User).where(User.username == "rad")).one()
        assert abs((row.expires_at.replace(tzinfo=timezone.utc) - row.created_at.replace(tzinfo=timezone.utc)).days
                   - settings.key_ttl_days_radius) <= 1


async def test_users_revoke_only_their_own_keys(portal):
    make_user(portal.sm, "ann", password=GOOD)
    make_user(portal.sm, "bob", password=GOOD)
    kid_bob, _ = new_key(portal.sm, "bob")
    kid_ann, plain_ann = new_key(portal.sm, "ann")
    await portal_login(portal, "ann", GOOD)
    token = await csrf_of_page(portal)
    assert (await portal.post(f"/me/keys/{kid_bob}/revoke", data={"csrf_token": token})).status_code == 404
    await portal.post(f"/me/keys/{kid_ann}/revoke", data={"csrf_token": token})
    with portal.sm() as s:
        assert s.get(PrintKey, kid_bob).revoked_at is None and s.get(PrintKey, kid_ann).revoked_at is not None
    assert not check(portal.sm, "ann", plain_ann)


async def test_admin_can_revoke_all_keys_of_a_user_and_it_is_logged(portal):
    make_user(portal.sm, "boss", password=GOOD, admin=True)
    make_user(portal.sm, "ann", password=GOOD)
    _, p1 = new_key(portal.sm, "ann", "a")
    _, p2 = new_key(portal.sm, "ann", "b")
    await portal_login(portal, "boss", GOOD)
    token = await csrf_of_page(portal, "/admin/users")
    with portal.sm() as s:
        uid = s.scalars(select(User).where(User.username == "ann")).one().id
    await portal.post(f"/admin/users/{uid}/revoke-keys", data={"csrf_token": token})
    assert not check(portal.sm, "ann", p1) and not check(portal.sm, "ann", p2)
    with portal.sm() as s:
        assert s.scalars(select(AdminAudit).where(AdminAudit.action == "user.revoke_keys")).one().detail_json["revoked"] == 2


async def test_a_print_key_is_not_a_portal_password(portal):
    make_user(portal.sm, "ann", password=GOOD)
    make_user(portal.sm, "radu", provider="radius")
    _, k1 = new_key(portal.sm, "ann")
    _, k2 = new_key(portal.sm, "radu")
    assert (await portal_login(portal, "ann", k1)).headers["location"] == "/admin/login"
    assert (await portal_login(portal, "radu", k2)).headers["location"] == "/admin/login"


# ---------------------------------------------------------------- IPP: who may print, in each mode

@pytest.fixture
async def ipp(portal, monkeypatch):
    monkeypatch.setattr(settings, "ipp_auth", "keys")
    portal.app.state.upstream = httpx.AsyncClient(base_url=CUPS_TEST_URL, timeout=10)
    yield portal
    await portal.app.state.upstream.aclose()


def print_job(title="doc.txt"):
    r = c.make_request(c.PRINT_JOB, 1, printer_uri="ipp://gw.test/printers/virtual", job_name=title,
                       document_format="text/plain")
    r.data = b"hello\n"
    return r


def get_jobs():
    return c.make_request(c.GET_JOBS, 1, printer_uri="ipp://gw.test/printers/virtual")


async def send(cl, req, user, secret):
    return await cl.post("/printers/virtual", content=c.encode(req), headers=basic(user, secret))


@requires_cups
async def test_a_local_user_prints_with_a_key_and_the_job_is_audited(ipp):
    make_user(ipp.sm, "ann", password=GOOD)
    _, plain = new_key(ipp.sm, "ann")
    r = await send(ipp, print_job("budget.txt"), "ann", plain)
    assert r.status_code == 200 and c.decode(r.content).code < 0x0100
    with ipp.sm() as s:
        row = s.scalars(select(JobLog)).one()
        assert (row.title, row.state.value, row.printer) == ("budget.txt", "accepted", "virtual")
        assert s.get(User, row.user_id).username == "ann"


@requires_cups
async def test_the_domain_password_is_not_accepted_for_printing_in_keys_mode(ipp):
    make_user(ipp.sm, "radu", provider="radius")
    ipp.app.state.auth = StubRadius({"radu": "domain-pass"})
    assert (await send(ipp, get_jobs(), "radu", "domain-pass")).status_code == 401
    _, plain = new_key(ipp.sm, "radu")
    assert (await send(ipp, get_jobs(), "radu", plain)).status_code == 200            # the key does


@requires_cups
async def test_keys_plus_radius_mode_accepts_the_domain_password_but_never_for_local_accounts(ipp, monkeypatch):
    monkeypatch.setattr(settings, "ipp_auth", "keys+radius")
    make_user(ipp.sm, "radu", provider="radius")
    make_user(ipp.sm, "loc", password=GOOD)
    ipp.app.state.auth = StubRadius({"radu": "domain-pass", "loc": "domain-pass"})
    assert (await send(ipp, get_jobs(), "radu", "domain-pass")).status_code == 200
    assert (await send(ipp, get_jobs(), "loc", "domain-pass")).status_code == 401     # RADIUS can not speak for a local account
    assert (await send(ipp, get_jobs(), "loc", GOOD)).status_code == 401              # nor does the portal password work here


async def test_every_way_a_key_can_be_wrong_is_just_a_401(ipp):
    make_user(ipp.sm, "ann", password=GOOD)
    make_user(ipp.sm, "bob", password=GOOD)
    make_user(ipp.sm, "off", password=GOOD)
    kid, ann_key = new_key(ipp.sm, "ann")
    _, off_key = new_key(ipp.sm, "off")
    _, expired = new_key(ipp.sm, "bob", ttl=1, now=NOW - timedelta(days=5))
    with ipp.sm() as s:
        s.query(User).filter_by(username="off").update({"enabled": False}); s.commit()
    cases = [("bob", ann_key), ("ghost", ann_key), ("ann", "cpk-wrong"), ("ann", ""), ("bob", expired), ("off", off_key)]
    for user, secret in cases:
        assert (await send(ipp, get_jobs(), user, secret)).status_code == 401, (user, secret)
    with ipp.sm() as s:
        assert s.scalars(select(User).where(User.username == "ghost")).first() is None   # keys mode never auto-creates
        s.query(PrintKey).filter_by(id=kid).update({"revoked_at": NOW}); s.commit()
    assert (await send(ipp, get_jobs(), "ann", ann_key)).status_code == 401


async def test_guessing_keys_is_throttled(ipp):
    make_user(ipp.sm, "ann", password=GOOD)
    for i in range(5):
        assert (await send(ipp, get_jobs(), "ann", f"cpk-guess-{i}")).status_code == 401
    assert (await send(ipp, get_jobs(), "ann", "cpk-guess-again")).status_code == 429
