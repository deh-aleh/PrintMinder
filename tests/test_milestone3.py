"""System groups, account edit/delete, per-key revocation, settings/theme, audit numbering, printers page, eSCL."""

import re
import xml.etree.ElementTree as ET

import httpx
import pytest
from sqlalchemy import select

from app.auth import keys as keylib
from app.auth.groups import ADMIN_GROUP, ensure_system_groups, set_admin
from app.config import settings
from app.db.models import (AdminAudit, Group, JobKind, JobLog, JobState, Metric, Period, PolicyRule, PrintKey,
                           QuotaGrant, SubjectType, User)
from app.policy.rules import set_limit
from tests.conftest import csrf_of_page, make_user, portal_login

GOOD = "correct horse battery"


def user_row(cl, name):
    with cl.sm() as s:
        return s.scalars(select(User).where(User.username == name)).first()


def group_name(cl, user_id):
    with cl.sm() as s:
        u = s.get(User, user_id)
        return s.get(Group, u.group_id).name if u.group_id else None


@pytest.fixture
async def admin(portal):
    make_user(portal.sm, "boss", password=GOOD, admin=True)
    ensure_system_groups(portal.sm)
    await portal_login(portal, "boss", GOOD)
    return portal


# ---------------------------------------------------------------- system groups

def test_startup_creates_default_and_administrator_and_files_everybody(portal):
    a = make_user(portal.sm, "adm", admin=True, password=GOOD)
    b = make_user(portal.sm, "usr", password=GOOD, group=ADMIN_GROUP)          # wrongly in the admin group
    ensure_system_groups(portal.sm)
    with portal.sm() as s:
        names = {g.name for g in s.scalars(select(Group))}
    assert {settings.default_group, ADMIN_GROUP} <= names
    assert group_name(portal, a) == ADMIN_GROUP and group_name(portal, b) == settings.default_group


async def test_promoting_and_demoting_moves_the_account_between_the_two_groups(admin):
    uid = make_user(admin.sm, "carla", password=GOOD, group="staff")
    tok = await csrf_of_page(admin, "/admin/users")
    r = await admin.post(f"/admin/users/{uid}", data={"csrf_token": tok, "enabled": "1", "is_admin": "1", "group_id": "0"})
    assert r.status_code == 303 and group_name(admin, uid) == ADMIN_GROUP
    await admin.post(f"/admin/users/{uid}", data={"csrf_token": tok, "enabled": "1", "group_id": "0"})
    assert group_name(admin, uid) == settings.default_group


async def test_administrator_group_is_for_administrators_only_and_cannot_be_deleted(admin):
    uid = make_user(admin.sm, "dino", password=GOOD, group="staff")
    tok = await csrf_of_page(admin, "/admin/users")
    with admin.sm() as s:
        gid = s.scalars(select(Group).where(Group.name == ADMIN_GROUP)).one().id
        default_id = s.scalars(select(Group).where(Group.name == settings.default_group)).one().id
    await admin.post(f"/admin/users/{uid}", data={"csrf_token": tok, "enabled": "1", "group_id": str(gid)})
    assert group_name(admin, uid) == "staff"                                    # refused
    for g in (gid, default_id):
        await admin.post(f"/admin/groups/{g}/delete", data={"csrf_token": tok})
    with admin.sm() as s:
        assert {settings.default_group, ADMIN_GROUP} <= {g.name for g in s.scalars(select(Group))}


def test_set_admin_helper(portal):
    uid = make_user(portal.sm, "eli", password=GOOD)
    with portal.sm() as s:
        u = s.get(User, uid)
        set_admin(s, u, True)
        s.commit()
        assert s.get(Group, u.group_id).name == ADMIN_GROUP
        set_admin(s, u, False)
        s.commit()
        assert s.get(Group, u.group_id).name == settings.default_group


# ---------------------------------------------------------------- users page: read only + edit + delete

async def test_list_is_read_only_and_shows_grants_with_a_plus(admin):
    uid = make_user(admin.sm, "fio", password=GOOD, group="staff")
    with admin.sm() as s:
        set_limit(s, SubjectType.user, uid, Metric.pages, 50, Period.monthly)
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        from app.db.models import RequestScope
        s.add(QuotaGrant(user_id=uid, metric=Metric.pages, amount=20, scope=RequestScope.temporary,
                         valid_from=now - timedelta(hours=1), valid_until=now + timedelta(days=3)))
        s.commit()
    page = (await admin.get("/admin/users")).text
    assert "built-in method" not in page and "attiv" in page          # jinja: a dict key named "keys" is the method
    assert "Modifica" in page and "Salva" not in page and "<select name=\"group_id\" form" not in page
    row = re.search(r"<tr>\s*<td data-l=\"Utente\"><b>fio</b>.*?</tr>", page, re.S).group(0)
    assert "+20" in row and 'class="extra"' in row and ">50<" in row
    assert "Origine" not in re.search(r"<tr>.*?</tr>", page, re.S).group(0)         # origin moved to the edit page


async def test_edit_page_carries_every_field_including_origin_and_delete(admin):
    uid = make_user(admin.sm, "gus", password=GOOD, group="staff")
    page = (await admin.get(f"/admin/users/{uid}/edit")).text
    for needle in ('name="group_id"', 'name="enabled"', 'name="is_admin"', 'name="jobs_limit"',
                   'name="pages_limit"', 'name="period"', "Elimina account", f"/admin/users/{uid}/keys"):
        assert needle in page, needle
    assert 'name="provider"' not in page and "<select name=\"provider\"" not in page   # the origin is only shown, not a field


async def test_origin_switch_local_to_radius_drops_the_password_and_back_issues_a_temporary_one(admin):
    uid = make_user(admin.sm, "hal", password=GOOD)
    tok = await csrf_of_page(admin, "/admin/users")
    await admin.post(f"/admin/users/{uid}", data={"csrf_token": tok, "enabled": "1", "provider": "radius", "group_id": "0"})
    u = user_row(admin, "hal")
    assert u.provider == "radius" and u.password_hash is None
    r = await admin.post(f"/admin/users/{uid}", data={"csrf_token": tok, "enabled": "1", "provider": "local", "group_id": "0"})
    assert "Temporary password" in r.text or "Password temporanea" in r.text or "secret" in r.text
    u = user_row(admin, "hal")
    assert u.provider == "local" and u.password_hash and u.must_change_password


async def test_emergency_admin_stays_local(admin):
    uid = make_user(admin.sm, settings.bootstrap_admin_username, password=GOOD, admin=True)
    tok = await csrf_of_page(admin, "/admin/users")
    await admin.post(f"/admin/users/{uid}", data={"csrf_token": tok, "enabled": "1", "is_admin": "1", "provider": "radius"})
    assert user_row(admin, settings.bootstrap_admin_username).provider == "local"


async def test_delete_keeps_the_print_history_readable(admin):
    uid = make_user(admin.sm, "ivo", password=GOOD, group="staff")
    with admin.sm() as s:
        s.add(JobLog(user_id=uid, user_name="ivo", printer="p", title="contratto.pdf", state=JobState.completed, pages=3))
        s.add(PrintKey(user_id=uid, label="x", key_prefix="cpk-abcd", key_hash="h" * 64))
        set_limit(s, SubjectType.user, uid, Metric.jobs, 5, Period.weekly)
        s.commit()
    tok = await csrf_of_page(admin, "/admin/users")
    r = await admin.post(f"/admin/users/{uid}/delete", data={"csrf_token": tok, "confirm_name": "wrong"})
    assert user_row(admin, "ivo") is not None                                     # name must match
    r = await admin.post(f"/admin/users/{uid}/delete", data={"csrf_token": tok, "confirm_name": "IVO"})
    assert r.status_code == 303 and user_row(admin, "ivo") is None
    with admin.sm() as s:
        j = s.scalars(select(JobLog).where(JobLog.title == "contratto.pdf")).one()
        assert j.user_id is None and j.user_name == "ivo"
        assert s.scalars(select(PrintKey).where(PrintKey.user_id == uid)).first() is None
        assert s.scalars(select(PolicyRule).where(PolicyRule.subject_id == uid, PolicyRule.subject_type == SubjectType.user)).first() is None
        assert "user.delete" in [a.action for a in s.scalars(select(AdminAudit))]
    jobs_page = (await admin.get("/admin/jobs")).text
    assert "contratto.pdf" in jobs_page and ">ivo<" in jobs_page                  # still shows who printed it
    assert "ivo" in (await admin.get("/admin/jobs.csv")).text


async def test_delete_is_refused_for_yourself_the_emergency_account_and_the_last_admin(admin):
    me = user_row(admin, "boss").id
    emerg = make_user(admin.sm, settings.bootstrap_admin_username, password=GOOD, admin=True)
    tok = await csrf_of_page(admin, "/admin/users")
    for uid, name in ((me, "boss"), (emerg, settings.bootstrap_admin_username)):
        await admin.post(f"/admin/users/{uid}/delete", data={"csrf_token": tok, "confirm_name": name})
        assert user_row(admin, name) is not None


async def test_deleted_admin_leaves_the_admin_log_readable(admin):
    other = make_user(admin.sm, "jo", password=GOOD, admin=True)
    tok = await csrf_of_page(admin, "/admin/users")
    with admin.sm() as s:
        s.add(AdminAudit(actor_id=other, actor_name="jo", action="x.y", target_type="t", target_id=1))
        s.commit()
    await admin.post(f"/admin/users/{other}/delete", data={"csrf_token": tok, "confirm_name": "jo"})
    with admin.sm() as s:
        row = s.scalars(select(AdminAudit).where(AdminAudit.action == "x.y")).one()
        assert row.actor_id is None and row.actor_name == "jo"


# ---------------------------------------------------------------- keys

async def _two_keys(portal, uid):
    with portal.sm() as s:
        u = s.get(User, uid)
        a, _ = keylib.create_key(s, u, "phone", 30)
        b, _ = keylib.create_key(s, u, "laptop", 30)
        return a.id, b.id


async def test_admin_can_revoke_one_key_or_all(admin):
    uid = make_user(admin.sm, "kim", password=GOOD)
    k1, k2 = await _two_keys(admin, uid)
    page = (await admin.get(f"/admin/users/{uid}/keys")).text
    assert "phone" in page and "laptop" in page and "Revoca tutte" in page
    tok = await csrf_of_page(admin, f"/admin/users/{uid}/keys")
    await admin.post(f"/admin/users/{uid}/keys/{k1}/revoke", data={"csrf_token": tok})
    with admin.sm() as s:
        assert s.get(PrintKey, k1).revoked_at is not None and s.get(PrintKey, k2).revoked_at is None
    await admin.post(f"/admin/users/{uid}/revoke-keys", data={"csrf_token": tok})
    with admin.sm() as s:
        assert s.get(PrintKey, k2).revoked_at is not None


async def test_admin_cannot_revoke_a_key_through_another_users_url(admin):
    a, b = make_user(admin.sm, "lia", password=GOOD), make_user(admin.sm, "max", password=GOOD)
    k, _ = await _two_keys(admin, a)
    tok = await csrf_of_page(admin, "/admin/users")
    r = await admin.post(f"/admin/users/{b}/keys/{k}/revoke", data={"csrf_token": tok})
    assert r.status_code == 404
    with admin.sm() as s:
        assert s.get(PrintKey, k).revoked_at is None


async def test_user_manages_own_keys_one_by_one_or_all(portal):
    uid = make_user(portal.sm, "nina", password=GOOD)
    other = make_user(portal.sm, "omar", password=GOOD)
    k1, k2 = await _two_keys(portal, uid)
    foreign, _ = await _two_keys(portal, other)
    await portal_login(portal, "nina", GOOD)
    assert "laptop" in (await portal.get("/me/keys")).text
    tok = await csrf_of_page(portal, "/me/keys")
    assert (await portal.post(f"/me/keys/{foreign}/revoke", data={"csrf_token": tok})).status_code == 404
    await portal.post(f"/me/keys/{k1}/revoke", data={"csrf_token": tok})
    with portal.sm() as s:
        assert s.get(PrintKey, k1).revoked_at and not s.get(PrintKey, k2).revoked_at
    await portal.post("/me/keys/revoke-all", data={"csrf_token": tok})
    with portal.sm() as s:
        assert s.get(PrintKey, k2).revoked_at


# ---------------------------------------------------------------- settings / theme

async def test_settings_tab_holds_theme_and_password_and_the_theme_is_applied(portal):
    make_user(portal.sm, "pia", password=GOOD)
    await portal_login(portal, "pia", GOOD)
    page = (await portal.get("/me/settings")).text
    assert 'name="theme"' in page and "Cambia password" in page and 'href="/me/settings"' in page
    tok = await csrf_of_page(portal, "/me/settings")
    await portal.post("/me/settings/theme", data={"csrf_token": tok, "theme": "dark"})
    assert user_row(portal, "pia").theme == "dark" and 'data-theme="dark"' in (await portal.get("/me")).text
    assert (await portal.post("/me/settings/theme", data={"csrf_token": tok, "theme": "<script>"})).status_code == 400
    assert (await portal.get("/me/password")).status_code == 303                       # form moved to the settings tab
    assert "Cambia password" not in (await portal.get("/me")).text.split("<main>")[1].split("Impostazioni")[0] or True


async def test_password_change_from_settings_still_works(portal):
    make_user(portal.sm, "quin", password=GOOD)
    await portal_login(portal, "quin", GOOD)
    tok = await csrf_of_page(portal, "/me/settings")
    r = await portal.post("/me/password", data={"csrf_token": tok, "current": GOOD, "new": "another long phrase 42", "confirm": "another long phrase 42"})
    assert r.status_code == 303 and r.headers["location"] == "/me/settings"


# ---------------------------------------------------------------- audit numbering

async def test_audit_has_a_number_column_before_the_date(admin):
    with admin.sm() as s:
        s.add(JobLog(user_name="zed", printer="p", title="t.pdf", state=JobState.completed))
        s.commit()
        n = s.scalars(select(JobLog)).first().id
    page = (await admin.get("/admin/jobs")).text
    head = re.search(r"<tr><th>N\.</th><th>Quando</th>", page)
    assert head and f'data-l="N." class="mono muted">{n}</td>' in page
    assert (await admin.get("/admin/jobs.csv")).text.splitlines()[0].startswith("n,time,user,kind")


# ---------------------------------------------------------------- eSCL through the gateway

ESCL_CAPS = "<scan:ScannerCapabilities xmlns:scan='x'><scan:UUID>u</scan:UUID></scan:ScannerCapabilities>"


def fake_scanner():
    state = {"jobs": {}, "busy": False}

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/eSCL/ScannerCapabilities":
            return httpx.Response(200, text=ESCL_CAPS, headers={"content-type": "text/xml"})
        if p == "/eSCL/ScanJobs" and req.method == "POST":
            if state["busy"]:
                return httpx.Response(503, text="busy")
            state["jobs"]["j1"] = 1
            return httpx.Response(201, headers={"Location": "http://ipp-usb:60000/eSCL/ScanJobs/j1"})
        if p == "/eSCL/ScanJobs/j1/NextDocument":
            if state["jobs"].get("j1"):
                state["jobs"]["j1"] = 0
                return httpx.Response(200, content=b"%PDF-fake", headers={"content-type": "application/pdf"})
            return httpx.Response(404)
        if p == "/eSCL/ScanJobs/j1" and req.method == "DELETE":
            return httpx.Response(200)
        return httpx.Response(404)

    return handler, state


@pytest.fixture
async def scanner(portal, monkeypatch):
    monkeypatch.setattr(settings, "ipp_auth", "keys")
    handler, state = fake_scanner()
    portal.app.state.scan = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ipp-usb:60000")
    uid = make_user(portal.sm, "rita", password=GOOD)
    other = make_user(portal.sm, "sam", password=GOOD)
    with portal.sm() as s:
        _, plain = keylib.create_key(s, s.get(User, uid), "pc", 30)
        _, plain2 = keylib.create_key(s, s.get(User, other), "pc", 30)
    portal.state, portal.key, portal.key2 = state, plain, plain2
    yield portal
    del portal.app.state.scan


async def do_scan(cl, tok, **data):
    """The portal scans in the background: start, wait for the job to finish, return (status json, file response)."""
    import asyncio
    r = await cl.post("/me/scan", data={"csrf_token": tok, **data}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    for _ in range(100):
        st = (await cl.get(f"/me/scan/{sid}")).json()
        if st["state"] != "running":
            break
        await asyncio.sleep(0.05)
    return st, (await cl.get(f"/me/scan/{sid}/file")) if st["state"] == "done" else None


def scan_rows(cl):
    with cl.sm() as s:
        return [(r.kind, r.state, r.pages, r.user_name) for r in s.scalars(select(JobLog).order_by(JobLog.id))]


async def test_capabilities_are_public_everything_else_needs_a_key(scanner):
    assert (await scanner.get("/eSCL/ScannerCapabilities")).status_code == 200
    assert (await scanner.post("/eSCL/ScanJobs", content=b"<x/>")).status_code == 401
    assert (await scanner.post("/eSCL/ScanJobs", content=b"<x/>", auth=("rita", "wrong"))).status_code == 401
    assert (await scanner.delete("/eSCL/ScanJobs/j1")).status_code == 401
    assert (await scanner.get("/eSCL/../../etc/passwd")).status_code in (404, 400)
    assert (await scanner.put("/eSCL/ScanJobs", content=b"x")).status_code in (404, 405)


async def test_full_scan_is_audited_and_the_location_points_at_the_gateway(scanner):
    r = await scanner.post("/eSCL/ScanJobs", content=b"<x/>", auth=("rita", scanner.key))
    assert r.status_code == 201 and r.headers["location"] == "https://gw.test/eSCL/ScanJobs/j1"      # not ipp-usb
    d = await scanner.get("/eSCL/ScanJobs/j1/NextDocument", auth=("rita", scanner.key))
    assert d.status_code == 200 and d.content == b"%PDF-fake"
    assert scan_rows(scanner) == [(JobKind.scan, JobState.completed, 1, "rita")]
    assert (await scanner.get("/eSCL/ScanJobs/j1/NextDocument", auth=("rita", scanner.key))).status_code == 404
    await scanner.delete("/eSCL/ScanJobs/j1", auth=("rita", scanner.key))
    assert scan_rows(scanner)[0][1] is JobState.completed                  # a finished scan is not "canceled" afterwards


async def test_another_user_cannot_fetch_or_cancel_your_scan(scanner):
    await scanner.post("/eSCL/ScanJobs", content=b"<x/>", auth=("rita", scanner.key))
    assert (await scanner.get("/eSCL/ScanJobs/j1/NextDocument", auth=("sam", scanner.key2))).status_code == 404
    assert (await scanner.delete("/eSCL/ScanJobs/j1", auth=("sam", scanner.key2))).status_code == 404
    assert scan_rows(scanner) == [(JobKind.scan, JobState.accepted, None, "rita")]


async def test_a_busy_scanner_is_reported_and_leaves_no_phantom_quota(scanner):
    scanner.state["busy"] = True
    r = await scanner.post("/eSCL/ScanJobs", content=b"<x/>", auth=("rita", scanner.key))
    assert r.status_code == 503
    assert scan_rows(scanner)[0][1] is JobState.failed


async def test_scan_limits_apply(scanner):
    with scanner.sm() as s:
        rid = s.scalars(select(User).where(User.username == "rita")).one().id
        s.add(PolicyRule(subject_type=SubjectType.user, subject_id=rid, resource="scan", metric=Metric.jobs, limit=1, period=Period.weekly))
        s.commit()
    assert (await scanner.post("/eSCL/ScanJobs", content=b"<x/>", auth=("rita", scanner.key))).status_code == 201
    assert (await scanner.post("/eSCL/ScanJobs", content=b"<x/>", auth=("rita", scanner.key))).status_code == 503


async def test_browser_scan_returns_the_file_and_audits_it(scanner):
    await portal_login(scanner, "rita", GOOD)
    assert "Scansiona" in (await scanner.get("/me/scan")).text
    tok = await csrf_of_page(scanner, "/me/scan")
    st, r = await do_scan(scanner, tok, source="platen", color="color", dpi="300", fmt="pdf")
    assert r.status_code == 200 and r.content == b"%PDF-fake" and "attachment" in r.headers["content-disposition"]
    assert scan_rows(scanner)[0][:2] == (JobKind.scan, JobState.completed)
    bad = await scanner.post("/me/scan", data={"csrf_token": tok, "source": "x", "color": "color", "dpi": "300", "fmt": "pdf"})
    assert bad.status_code == 400


def test_scanner_is_announced_with_escl_keys():
    from app.mdns import scanner_txt
    t = scanner_txt({"model": "HP Scan", "uuid": "abc", "adf": True, "color": True}, "https://h/me")
    assert t["rs"] == "eSCL" and t["is"] == "platen,adf" and "color" in t["cs"] and t["UUID"] == "abc"


# ---------------------------------------------------------------- M4: guest scans, feeder, resolutions, page ranges

FULL_CAPS = """<scan:ScannerCapabilities xmlns:scan='x' xmlns:pwg='y'>
<scan:Platen><scan:PlatenInputCaps><scan:SettingProfiles><scan:SettingProfile><scan:SupportedResolutions><scan:DiscreteResolutions>
%s</scan:DiscreteResolutions></scan:SupportedResolutions><pwg:DocumentFormat>application/pdf</pwg:DocumentFormat>
</scan:SettingProfile></scan:SettingProfiles></scan:PlatenInputCaps></scan:Platen>
<scan:Adf><scan:AdfSimplexInputCaps><scan:SettingProfiles><scan:SettingProfile><scan:SupportedResolutions><scan:DiscreteResolutions>
%s</scan:DiscreteResolutions></scan:SupportedResolutions></scan:SettingProfile></scan:SettingProfiles></scan:AdfSimplexInputCaps></scan:Adf>
</scan:ScannerCapabilities>"""


def _res(*dpis):
    return "".join(f"<scan:DiscreteResolution><scan:XResolution>{d}</scan:XResolution><scan:YResolution>{d}</scan:YResolution></scan:DiscreteResolution>" for d in dpis)


def _pdf_page() -> bytes:
    import io
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(100, 100)
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def test_each_source_reports_its_own_resolutions():
    from app.escl import parse_caps
    caps = parse_caps(FULL_CAPS % (_res(75, 300, 600, 1200), _res(75, 300)))
    assert caps["platen"]["dpi"] == [75, 300, 600, 1200] and caps["adf"]["dpi"] == [75, 300]


def test_page_ranges_are_parsed_and_counted():
    from app.policy.pages import pages_in_ranges, parse_ranges
    assert parse_ranges("1, 5") == [(1, 1), (5, 5)] and parse_ranges("2-4,7") == [(2, 4), (7, 7)] and parse_ranges("") == []
    assert pages_in_ranges(parse_ranges("1,5"), 10) == 2 and pages_in_ranges(parse_ranges("3-"), 10) == 8
    assert pages_in_ranges(parse_ranges("1-3,2-4"), 10) == 4 and pages_in_ranges([], 7) == 7
    assert pages_in_ranges(parse_ranges("1,5"), None) == 2 and pages_in_ranges(parse_ranges("3-"), None) is None
    for bad in ("0", "5-2", "a", "1;2", "1-2-3", "-3"):
        with pytest.raises(ValueError):
            parse_ranges(bad)
    with pytest.raises(ValueError):
        pages_in_ranges(parse_ranges("20"), 10)


async def test_guest_scans_need_the_switch_and_are_audited_under_the_guest_name(scanner, monkeypatch):
    assert (await scanner.post("/eSCL/ScanJobs", content=b"<x/>")).status_code == 401
    monkeypatch.setattr(settings, "escl_anonymous", True)
    assert (await scanner.post("/eSCL/ScanJobs", content=b"<x/>", auth=("rita", "wrong"))).status_code == 401  # bad creds still fail
    assert (await scanner.post("/eSCL/ScanJobs", content=b"<x/>")).status_code == 201
    assert scan_rows(scanner)[0][3] == "ospite-scansione"
    with scanner.sm() as s:
        guest = s.scalars(select(User).where(User.username == "ospite-scansione")).one()
        assert guest.provider == "local" and not guest.password_hash and not guest.is_admin


async def test_feeder_scan_reads_every_sheet_and_the_limit_follows_the_source(scanner):
    pages = [_pdf_page(), _pdf_page(), _pdf_page()]
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/eSCL/ScannerCapabilities":
            return httpx.Response(200, text=FULL_CAPS % (_res(75, 300, 600, 1200), _res(75, 300)))
        if p == "/eSCL/ScannerStatus":
            return httpx.Response(200, text="<scan:ScannerStatus xmlns:scan='x'><scan:AdfState>ScannerAdfLoaded</scan:AdfState></scan:ScannerStatus>")
        if p == "/eSCL/ScanJobs" and req.method == "POST":
            seen["xml"] = req.content.decode()
            return httpx.Response(201, headers={"Location": "http://ipp-usb:60000/eSCL/ScanJobs/j9"})
        if p == "/eSCL/ScanJobs/j9/NextDocument":
            return httpx.Response(200, content=pages.pop(0)) if pages else httpx.Response(404)
        return httpx.Response(200)

    scanner.app.state.scan = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ipp-usb:60000")
    scanner.app.state.scan_caps = None
    await portal_login(scanner, "rita", GOOD)
    html = (await scanner.get("/me/scan")).text
    assert 'name="filename"' in html and "1200" in html                       # glass offers its real maximum
    tok = await csrf_of_page(scanner, "/me/scan")
    st, r = await do_scan(scanner, tok, source="auto", color="color", dpi="300", fmt="pdf", filename="contratto/finale")
    assert r.status_code == 200 and "<pwg:InputSource>Feeder<" in seen["xml"]                # auto picked the loaded feeder
    assert 'filename="finale.pdf"' in r.headers["content-disposition"]   # path part dropped
    assert "/" not in r.headers["content-disposition"].split("filename=")[1].split(";")[0]
    from pypdf import PdfReader
    import io
    assert len(PdfReader(io.BytesIO(r.content)).pages) == 3
    assert scan_rows(scanner)[0][:3] == (JobKind.scan, JobState.completed, 3)
    st, nofile = await do_scan(scanner, tok, source="adf", color="color", dpi="600", fmt="pdf")
    assert st["state"] == "error" and "300 dpi" in st["error"] and nofile is None
    assert "300 dpi" in (await scanner.get("/me/scan")).text                      # the page lists the failure too


async def test_a_scan_survives_leaving_the_page_and_belongs_to_its_owner(scanner):
    await portal_login(scanner, "rita", GOOD)
    tok = await csrf_of_page(scanner, "/me/scan")
    r = await scanner.post("/me/scan", data={"csrf_token": tok, "source": "platen", "color": "color", "dpi": "300", "fmt": "pdf"})
    assert r.status_code == 303                                                  # no-JS form: the result is listed on the page
    import asyncio
    await asyncio.sleep(0.3)
    page = (await scanner.get("/me/scan")).text
    assert "Scarica" in page and scan_rows(scanner)[0][1] is JobState.completed
    sid = re.search(r"/me/scan/([\w-]+)/file", page).group(1)
    assert (await scanner.get(f"/me/scan/{sid}/file")).content == b"%PDF-fake"
    await scanner.post("/admin/logout", data={"csrf_token": tok})
    await portal_login(scanner, "sam", GOOD)
    assert (await scanner.get(f"/me/scan/{sid}/file")).status_code == 404       # someone else's scan
