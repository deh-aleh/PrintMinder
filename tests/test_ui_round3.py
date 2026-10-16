"""Audit readability (stripes, state help, guest scan info), user creation with groups (local and RADIUS), the
actions page size, hover rules, forms that keep what was typed, the MFP badge."""

import re
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.admin.accounts import ACTIONS_PAGE
from app.db.models import AdminAudit, Group, JobKind, JobLog, JobState, User
from tests.conftest import csrf_of_page, make_user, portal_login

GOOD = "correct horse battery"


async def _admin(portal, name="boss"):
    make_user(portal.sm, name, password=GOOD, admin=True)
    await portal_login(portal, name, GOOD)


def _job(sm, user_id, **kw):
    with sm() as s:
        j = JobLog(user_id=user_id, kind=kw.pop("kind", JobKind.print), printer=kw.pop("printer", "p1"), title="a.pdf",
                   state=kw.pop("state", JobState.completed), ts=datetime.now(timezone.utc), **kw)
        s.add(j)
        s.commit()


@pytest.mark.usefixtures("english")
async def test_local_and_radius_users_can_be_created_in_a_chosen_group(portal, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "radius_host", "radius.test")      # the form is offered only when RADIUS is configured
    monkeypatch.setattr(settings, "radius_secret", "x")
    await _admin(portal)
    with portal.sm() as s:
        s.add(Group(name="studenti"))
        s.add(Group(name="docenti"))
        s.commit()
    csrf = await csrf_of_page(portal, "/admin/users")
    page = (await portal.get("/admin/users")).text
    forms = re.findall(r'<select name="group_id">(.*?)</select>', page, re.S)
    assert len(forms) == 2                                           # local form and RADIUS form
    for f in forms:
        assert "studenti" in f and "docenti" in f and "administrator" not in f
    with portal.sm() as s:
        gid = {g.name: g.id for g in s.scalars(select(Group))}

    r = await portal.post("/admin/users/local", data=dict(csrf_token=csrf, username="loc1", group_id=gid["studenti"]))
    assert r.status_code == 200 and "Temporary password" in r.text
    r = await portal.post("/admin/users", data=dict(csrf_token=csrf, username="Rad1", group_id=gid["docenti"]))
    assert r.status_code == 303
    with portal.sm() as s:
        u = {x.username: x for x in s.scalars(select(User))}
        assert u["loc1"].provider == "local" and u["loc1"].group_id == gid["studenti"]
        assert u["rad1"].provider == "radius" and u["rad1"].group_id == gid["docenti"]
        assert not u["rad1"].is_admin

    # the pre-registered person logs in through RADIUS later and keeps the group chosen for them
    # (the stub RADIUS knows "rad"/"radpw": pre-register that name, then let them in)
    await portal.post("/admin/users", data=dict(csrf_token=csrf, username="rad", group_id=gid["docenti"]))
    await portal.post("/logout", data=dict(csrf_token=csrf))
    login = await portal_login(portal, "rad", "radpw")
    assert login.status_code in (200, 303)
    with portal.sm() as s:
        rad = s.scalars(select(User).where(User.username == "rad")).one()
        assert rad.group_id == gid["docenti"] and rad.provider == "radius"

    # the administrator group is not offered and not accepted
    await portal_login(portal, "boss", GOOD)
    csrf = await csrf_of_page(portal, "/admin/users")
    with portal.sm() as s:
        admin_group = Group(name="administrator")          # exists in a real installation (made at start)
        s.add(admin_group)
        s.commit()
        admin_gid = admin_group.id
    page = (await portal.get("/admin/users")).text
    assert "administrator" not in " ".join(re.findall(r'<select name="group_id">(.*?)</select>', page, re.S))
    await portal.post("/admin/users/local", data=dict(csrf_token=csrf, username="sneaky", group_id=admin_gid))
    await portal.post("/admin/users", data=dict(csrf_token=csrf, username="sneaky2", group_id=admin_gid))
    with portal.sm() as s:
        assert not s.scalars(select(User).where(User.username.in_(["sneaky", "sneaky2"]))).all()


async def test_audit_has_stripes_state_help_and_guest_info(portal):
    await _admin(portal)
    with portal.sm() as s:
        boss = s.scalars(select(User).where(User.username == "boss")).one().id
        guest = User(username="ospite-scansione", provider="local", enabled=False)
        s.add(guest)
        s.commit()
        gid = guest.id
    _job(portal.sm, gid, kind=JobKind.scan, printer="scanner",
         options_json={"via": "escl", "guest_ip": "10.1.2.3", "guest_host": "pc-aula3.scuola.lan"})
    _job(portal.sm, boss)
    page = (await portal.get("/admin/jobs")).text
    assert 'class="stack-md zebra"' in page
    assert 'id="states-help"' in page and all(w in page for w in ("Accettato.", "Completato.", "Negato.", "Fallito.", "Annullato.", "In attesa."))
    assert re.search(r"<th>Stato <button[^>]*info-lg", page)
    assert "10.1.2.3" in page and "pc-aula3.scuola.lan" in page and "Scansione senza accesso" in page
    assert page.count("Scansione senza accesso") == 1                   # only the guest row has the button
    # no hostname known: say so instead of leaving a hole
    _job(portal.sm, gid, kind=JobKind.scan, printer="scanner", options_json={"via": "escl", "guest_ip": "10.9.9.9"})
    assert "non disponibile" in (await portal.get("/admin/jobs")).text


async def test_guest_scan_records_the_host_name(portal, monkeypatch):
    from app import escl

    monkeypatch.setattr(escl.socket, "gethostbyaddr", lambda ip: ("laptop.lan", [], [ip]))
    assert await escl._hostname("10.0.0.7") == "laptop.lan"
    monkeypatch.setattr(escl.socket, "gethostbyaddr", lambda ip: (_ for _ in ()).throw(OSError("no name")))
    assert await escl._hostname("10.0.0.7") == ""


async def test_actions_page_is_30_rows_and_roomy(portal):
    await _admin(portal)
    with portal.sm() as s:
        for i in range(ACTIONS_PAGE + 5):
            s.add(AdminAudit(actor_name="boss", action=f"test.{i}"))
        s.commit()
    page = (await portal.get("/admin/actions")).text
    assert ACTIONS_PAGE == 30
    assert page.count('<td class="mono">test.') == 30 and "Pagina 1 / 2" in page
    assert 'class="roomy stack"' in page


async def test_theme_rules_and_kept_forms(portal):
    await _admin(portal)
    page = (await portal.get("/admin/users")).text
    css = re.search(r"<style>(.*?)</style>", page, re.S).group(1)
    assert "nav a:hover" in css and "#ffa733" in css                    # orange top bar
    assert "button.maint:hover" not in css                              # the maintenance button is left out
    assert "button.danger:hover" in css                                 # Blocca uso / Elimina swap colours
    for url, marker in (("/admin/backups", "data-keep"), ("/me/print", 'data-keep'), ("/me/scan", 'data-keep="always"')):
        assert marker in (await portal.get(url)).text, url


def test_mfp_badge_follows_what_the_device_reports():
    """Only a device that also answers as an eSCL scanner is marked MFP; nothing depends on a model name."""
    from app.admin.common import templates

    def render(scanner):
        q = {"name": "q1", "state": "inattiva", "online": True, "accepting": True, "queued": 0, "reasons": [], "message": "",
             "device_uri": "ipp://x", "ink": [], "location": "", "color": False}
        dev = {"ipp": {}, "usage": [], "config": {}, "scanner": scanner}
        d = {"title": "Printer", "base": "http://x:631", "online": True, "virtual": False, "queues": [q], "device": dev, "stats": {}, "scan_stats": None}
        return templates.get_template("printers.html").render(
            request=type("R", (), {"url": type("U", (), {"path": "/admin/printers"})()})(), me=None, csrf="t", flashes=[],
            devices=[d], controls={}, key=str.lower, maintenance=False, keepalive={}, next_due=lambda r: None,
            describe=str, split=lambda h: (h, "hours"), presets=[], transport=lambda u: None, refresh_seconds=15)

    assert ">MFP<" in render({"state": "Idle"})
    assert ">MFP<" not in render(None)
