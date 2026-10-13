"""Printing from the browser (the phone path) and the set-up helpers shown on the profile page."""

import re

import httpx
import pytest
from sqlalchemy import select

from app.admin.printing import clean_filename, detect_type
from app.config import settings
from app.db.models import AdminAudit, JobLog, JobState, Metric, Period, SubjectType, User
from app.policy.rules import set_limit
from tests.conftest import CUPS_TEST_URL, csrf_of_page, make_user, portal_login, requires_cups

GOOD = "correct horse battery"
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
       b"trailer<</Root 1 0 R/Size 4>>\n%%EOF\n")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 40


# ---------------------------------------------------------------- what the file really is

def test_file_type_comes_from_the_content_not_from_the_name_or_the_browser():
    assert detect_type(PDF) == "application/pdf" and detect_type(PNG) == "image/png" and detect_type(JPG) == "image/jpeg"
    assert detect_type(b"GIF89a....") == "image/gif" and detect_type("ciao è un testo\n\tcon tab\r\n".encode()) == "text/plain"
    for bad in (b"MZ\x90\x00\x03", b"PK\x03\x04zip", b"\x7fELF\x02", b"#!/bin/sh\x00\x00", b"\x00\x01\x02", b"\xff\xfe\xfd\xfc", b"", b"<svg/>\x00"):
        assert detect_type(bad) is None, bad


def test_file_names_are_cleaned():
    assert clean_filename("../../etc/passwd") == "passwd"
    assert clean_filename("C:\\Users\\x\\relazione finale.pdf") == "relazione finale.pdf"
    assert clean_filename("a\x00b\x07c\n.pdf") == "abc.pdf"
    assert clean_filename("") == "document" and clean_filename(None) == "document" and clean_filename("...") == "document"
    assert len(clean_filename("x" * 999)) == 200


# ---------------------------------------------------------------- through the app

@pytest.fixture
async def web(portal):
    portal.app.state.upstream = httpx.AsyncClient(base_url=CUPS_TEST_URL, timeout=10)
    make_user(portal.sm, "ann", password=GOOD, group="staff")
    with portal.sm() as s:
        gid = s.scalars(select(User).where(User.username == "ann")).one().group_id
        set_limit(s, SubjectType.group, gid, Metric.jobs, 2, Period.weekly)
        s.commit()
    await portal_login(portal, "ann", GOOD)
    portal.token = await csrf_of_page(portal)
    yield portal
    await portal.app.state.upstream.aclose()


async def send(cl, data=PDF, name="relazione.pdf", queue="virtual", copies="1", token=None, content_type="application/pdf"):
    return await cl.post("/me/print", data={"queue": queue, "copies": copies, "csrf_token": token or cl.token},
                         files={"file": (name, data, content_type)} if data is not None else None)


def rows(cl):
    with cl.sm() as s:
        return [(j.title, j.state.value, j.printer, j.cups_job_id, j.options_json) for j in s.scalars(select(JobLog).order_by(JobLog.id))]


async def last_message(cl):
    html = (await cl.get("/me/print")).text
    m = re.findall(r'class="flash (?:ok|err)">([^<]*)<', html)
    return m[-1] if m else ""


@requires_cups
@pytest.mark.usefixtures("english")
async def test_a_phone_user_prints_a_pdf_and_it_is_audited_like_any_other_job(web):
    html = (await web.get("/me/print")).text
    assert 'enctype="multipart/form-data"' in html and 'name="file"' in html and "virtual" in html
    assert 'viewport' in (await web.get("/me")).text                                # usable at phone width
    r = await send(web, name="../../relazione.pdf", copies="2")
    assert r.status_code == 303 and r.headers["location"] == "/me/print"
    assert "Sent to virtual: relazione.pdf" in await last_message(web)
    [(title, state, printer, job_id, opts)] = rows(web)
    assert (title, state, printer) == ("relazione.pdf", "accepted", "virtual") and job_id
    assert opts == {"via": "web", "document_format": "application/pdf", "copies": 2}


@requires_cups
async def test_images_and_text_are_accepted_too(web):
    for data, name, ctype in ((JPG, "foto.jpg", "image/jpeg"), ("nota di prova\n".encode(), "nota.txt", "text/plain")):
        await send(web, data, name, content_type=ctype)
    assert [r[1] for r in rows(web)] == ["accepted", "accepted"]


@requires_cups
@pytest.mark.usefixtures("english")
async def test_the_quota_applies_and_the_refusal_points_to_the_request_form(web):
    await send(web)
    await send(web, name="due.pdf")
    r = await send(web, name="tre.pdf")
    assert r.status_code == 303 and r.headers["location"] == "/me"                   # sent where the request form is
    assert "weekly job limit reached (2/2)" in (await web.get("/me")).text
    assert [(r[0], r[1]) for r in rows(web)] == [("relazione.pdf", "accepted"), ("due.pdf", "accepted"), ("tre.pdf", "denied")]


@pytest.mark.usefixtures("english")
async def test_bad_uploads_are_refused_with_a_message_and_leave_no_trace(web, monkeypatch):
    cases = [
        (dict(data=b"MZ\x90\x00 an executable", name="innocent.pdf"), "Unsupported file"),     # lying name and content-type
        (dict(data=b"PK\x03\x04 a zip", name="doc.pdf"), "Unsupported file"),
        (dict(data=b"", name="empty.pdf"), "empty"),
        (dict(data=PDF, queue="nonexistent"), "Choose a printer"),
        (dict(data=PDF, queue="../../admin"), "Choose a printer"),
        (dict(data=PDF, copies="0"), "Copies"), (dict(data=PDF, copies="999"), "Copies"),
        (dict(data=PDF, copies="2.5"), "Copies"), (dict(data=PDF, copies="\u00b2"), "Copies"),
        (dict(data=None), "Choose a file"),
    ]
    web.app.state.queues_cache = (__import__("time").monotonic(), [{"name": "virtual", "info": "", "model": ""}])
    for kwargs, expected in cases:
        r = await send(web, **kwargs)
        assert r.status_code == 303, kwargs
        assert expected in await last_message(web), (kwargs, await last_message(web))
    assert rows(web) == []


@pytest.mark.usefixtures("english")
async def test_oversized_uploads_are_stopped_before_they_are_read(web, monkeypatch):
    monkeypatch.setattr(settings, "web_upload_mb", 1)
    web.app.state.queues_cache = (__import__("time").monotonic(), [{"name": "virtual", "info": "", "model": ""}])
    r = await send(web, PDF + b"x" * (2 << 20))
    assert r.status_code == 303 and "larger than 1 MB" in await last_message(web)
    assert rows(web) == []


async def test_csrf_login_and_content_length_are_required(web):
    assert (await send(web, token="wrong")).status_code == 403
    web.app.state.queues_cache = (__import__("time").monotonic(), [{"name": "virtual", "info": "", "model": ""}])

    async def chunks():
        yield b"--b\r\n"
    r = await web.post("/me/print", content=chunks(), headers={"Content-Type": "multipart/form-data; boundary=b"})
    assert r.status_code == 411                                                      # no declared size: refused unread
    anon = httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app, client=("10.0.0.50", 1)), base_url="https://gw.test")
    async with anon:
        r = await anon.post("/me/print", data={"queue": "virtual", "csrf_token": "x"}, files={"file": ("a.pdf", PDF)})
        assert r.status_code == 303 and r.headers["location"] == "/admin/login"
        assert (await anon.get("/me/print")).headers["location"] == "/admin/login"
    assert rows(web) == []


async def test_a_disabled_user_can_not_print_from_an_old_session(web):
    with web.sm() as s:
        s.query(User).filter_by(username="ann").update({"enabled": False}); s.commit()
    web.app.state.queues_cache = (__import__("time").monotonic(), [{"name": "virtual", "info": "", "model": ""}])
    r = await send(web)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login" and rows(web) == []


@pytest.mark.usefixtures("english")
async def test_cups_down_frees_the_quota_slot(web):
    web.app.state.queues_cache = (__import__("time").monotonic(), [{"name": "virtual", "info": "", "model": ""}])
    await web.app.state.upstream.aclose()
    web.app.state.upstream = httpx.AsyncClient(base_url="http://127.0.0.1:9", timeout=1)
    await send(web)
    assert "did not accept" in await last_message(web)
    assert [(r[1]) for r in rows(web)] == ["failed"]                                 # the slot is free again


@requires_cups
async def test_filenames_with_html_are_shown_escaped_in_the_audit(web):
    make_user(web.sm, "boss", password=GOOD, admin=True)
    await send(web, name="<img src=x onerror=alert(1)>.pdf")
    boss = httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app, client=("10.0.0.9", 1)), base_url="https://gw.test")
    async with boss:
        await portal_login(boss, "boss", GOOD)
        page = (await boss.get("/admin/jobs")).text
    assert "<img src=x" not in page and "&lt;img src=x" in page


# ---------------------------------------------------------------- the set-up help

async def test_the_key_page_gives_a_ready_command_per_printer_and_never_logs_the_key(web):
    web.app.state.queues_cache = (__import__("time").monotonic(), [{"name": "HP7305", "info": "", "model": ""}, {"name": "virtual", "info": "", "model": ""}])
    r = await web.post("/me/keys", data={"label": "pc", "csrf_token": web.token})
    key = re.search(r'class="secret">([^<]+)<', r.text).group(1)
    cmds = re.findall(r'class="secret" style="font-size:13px[^>]*>([^<]+)<', r.text)
    urls, cmds = cmds[:2], cmds[2:]                                                  # GUI address first, terminal command after
    assert all(u.startswith("ipps://ann:") for u in urls) and urls[0] == f"ipps://ann:{key}@gw.test/printers/HP7305"
    assert len(cmds) == 2 and all(c.startswith("lpadmin -p ") for c in cmds)
    assert f'ipps://ann:{key}@gw.test/printers/HP7305' in cmds[0] and "auth-info-required=none" in cmds[0]
    assert key not in (await web.get("/me")).text                                    # shown once, never again


async def test_the_profile_explains_how_to_connect_each_kind_of_device(web):
    web.app.state.queues_cache = (__import__("time").monotonic(), [{"name": "HP7305", "info": "", "model": ""}])
    page = (await web.get("/me")).text
    assert "Telefono o tablet" in page and "/me/print" in page and "Linux" in page and "Windows / macOS" in page
    assert "ipps://gw.test/printers/" in page and "HP7305" in page


def two_pages() -> bytes:
    import io
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(200, 200)
    w.add_blank_page(200, 200)
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


@requires_cups
@pytest.mark.usefixtures("english")
async def test_print_options_reach_cups_and_page_ranges_are_checked_first(web):
    async def go(**extra):
        return await web.post("/me/print", data={"queue": "virtual", "copies": "1", "csrf_token": web.token, **extra},
                              files={"file": ("relazione.pdf", two_pages(), "application/pdf")})
    for bad in ({"pages": "5"}, {"pages": "3-1"}, {"pages": "x"}, {"media": "iso_a99"}, {"comment": "x" * 51}):
        r = await go(**bad)
        assert r.status_code == 303 and rows(web) == [], bad                      # refused, nothing reserved
    assert (await go(orientation="sideways")).status_code == 400
    ok = await go(pages="1", orientation="landscape", color="monochrome", comment="Contratto firmato")
    assert ok.status_code == 303 and "Sent to virtual: relazione.pdf" in await last_message(web)
    [(title, state, _, job_id, opts)] = rows(web)
    assert state == "accepted" and job_id
    assert opts["comment"] == "Contratto firmato" and title == "relazione.pdf" and opts["page_ranges"] == "1" and opts["orientation"] == "landscape" and opts["color"] == "monochrome"
