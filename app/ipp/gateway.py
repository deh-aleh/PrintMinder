"""IPP reverse proxy: client -> gateway (auth, identity, op filter) -> CUPS."""

import base64
import binascii
import logging
from collections.abc import AsyncIterator
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from app.auth import keys, service
from app.auth.throttle import IP_FAILS, USER_FAILS, register_failure
from app.config import settings
from app.cups_client import UNKNOWN_CAPS, queue_caps
from app.ipp import codec
from app.ipp.rewrite import advertise_auth, rewrite_uris
from app.policy import audit, control, permissions
from app.db.models import Metric, PrintKey, Resource
from app.policy import pages as pages_mod
from app.policy.engine import Decision, check_job, effective_rules

log = logging.getLogger(__name__)
router = APIRouter()

MAX_HEAD = 1 << 20  # attributes section limit (documents stream after it)
IPP_CT = "application/ipp"
REALM = 'Basic realm="Print gateway", charset="UTF-8"'

# Operations any authenticated user may run. Everything else (printer admin, device/PPD
# listing, Print-URI/Send-URI = server-side fetch, hold/release) needs is_admin.
# Server-side fetch of a URL (SSRF): not even gateway admins may use these.
NEVER_OPS = {0x0003, 0x0007}  # Print-URI, Send-URI
# Answered without credentials (see ipp_proxy): read-only, no document, nothing is audited.
# Validate-Job is a "would this job be accepted?" question that carries no document: Windows asks it while adding a
# printer, before it has any password, and its "Add device" window can not ask for one. The quota is not consulted for
# an anonymous caller; the real job (Print-Job, Create-Job) still needs a login and is counted as always.
ANON_OPS = {codec.GET_PRINTER_ATTRIBUTES, codec.VALIDATE_JOB}
ANON_MAX_BODY = 64 << 10  # a capability query is a few hundred bytes
STATUS_OPS = {codec.GET_PRINTER_ATTRIBUTES, codec.GET_JOBS, 0x0008, 0x0009}  # a single-use key that has printed may still do these
SUBMIT_OPS = {codec.PRINT_JOB, codec.CREATE_JOB}  # each counts as one job against the quota
PERMISSION_OPS = {codec.PRINT_JOB, codec.CREATE_JOB, codec.VALIDATE_JOB}  # the ones the user's permissions are applied to
LISTING_OPS = {0x4002, 0x4005}  # CUPS-Get-Printers, CUPS-Get-Classes: a person limited to some printers only sees those
PERM_ATTRS = ("print-color-mode", "sides", "ColorModel", "ColorMode", "Duplex")  # what the permissions look at in a job
USER_OPS = {
    codec.PRINT_JOB, codec.VALIDATE_JOB, codec.CREATE_JOB, codec.SEND_DOCUMENT,
    0x0008,  # Cancel-Job
    0x0009,  # Get-Job-Attributes
    codec.GET_JOBS, codec.GET_PRINTER_ATTRIBUTES,
    0x0039,  # Cancel-My-Jobs
    0x003B,  # Close-Job
    0x003C,  # Identify-Printer
    0x4001,  # CUPS-Get-Default
    0x4002,  # CUPS-Get-Printers
    0x4005,  # CUPS-Get-Classes
}


async def read_head(request: Request) -> tuple[codec.IppMessage, bytes, AsyncIterator[bytes]]:
    """Buffer just enough of the body to parse the IPP header.

    Returns (message, bytes_after_header_already_read, iterator_for_the_rest).
    """
    it = request.stream().__aiter__()
    buf = b""
    async for chunk in it:
        buf += chunk
        try:
            msg, off = codec.decode_head(buf)
            return msg, buf[off:], it
        except codec.IppError:
            if len(buf) > MAX_HEAD:
                raise HTTPException(413, "IPP attributes too large")
    raise HTTPException(400, "malformed IPP request")


async def _no_more() -> AsyncIterator[bytes]:
    return
    yield  # makes this an (empty) async generator


class TooLarge(Exception):
    pass


async def _body(head: bytes, rest: AsyncIterator[bytes], limit: int) -> AsyncIterator[bytes]:
    total = len(head)
    yield head
    async for chunk in rest:
        total += len(chunk)
        if total > limit:
            raise TooLarge
        yield chunk


def _scheme(request: Request) -> str:
    return settings.public_scheme or ("ipps" if request.url.scheme == "https" else "ipp")


def _public_bases(request: Request) -> tuple[str, str]:
    host = request.headers.get("host", "localhost")
    ipp = _scheme(request)
    return f"{ipp}://{host}", f"{'https' if ipp == 'ipps' else 'http'}://{host}"


def _unauthorized(detail: str = "authentication required") -> Response:
    return Response(detail, status_code=401, headers={"WWW-Authenticate": REALM}, media_type="text/plain")


def _parse_basic(header: str | None) -> tuple[str, str] | None:
    if not header or not header.lower().startswith("basic "):
        return None
    try:
        raw = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    user, sep, password = raw.partition(":")
    if not sep or not user or len(user) > 128 or any(ord(ch) < 32 for ch in user):
        return None
    return user, password


def _ipp_error(msg: codec.IppMessage, status: int, text: str) -> Response:
    resp = codec.make_error_response(status, msg.request_id, text)
    resp.version = msg.version
    return Response(codec.encode(resp), media_type=IPP_CT)


@router.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def not_found(path: str) -> Response:
    """IPP is POST-only. Without this, any unknown GET got a misleading 405 instead of a 404."""
    return Response("not found", status_code=404, media_type="text/plain")


@router.post("/{path:path}")
async def ipp_proxy(path: str, request: Request) -> Response:
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != IPP_CT:
        raise HTTPException(415, "application/ipp required")

    if request.url.scheme != "https" and not settings.allow_insecure_auth:
        return Response("TLS required (use ipps://)", status_code=403, media_type="text/plain")

    creds = _parse_basic(request.headers.get("authorization"))
    anonymous = creds is None
    user = None
    key = None
    if anonymous:
        # Capability queries are answered without credentials: IPP Everywhere clients (CUPS, KDE, Windows,
        # macOS) ask what the printer can do before they ever send a password. Only small, fully declared
        # bodies are read: anything that could carry a document is challenged at once, unread.
        # (libcups sends "Expect: 100-continue" even for plain attribute queries, so that header alone proves nothing.)
        declared = request.headers.get("content-length", "")
        if not settings.anonymous_discovery or not declared.isdigit() or int(declared) > ANON_MAX_BODY:
            log.info("unauthenticated request challenged (content-length=%r)", declared)
            return _unauthorized()
        msg, head_rest, rest = await read_head(request)
        if msg.code not in ANON_OPS:
            log.info("unauthenticated op=0x%04x path=/%s challenged", msg.code, path)
            return _unauthorized()
        identity = "anonymous"
    else:
        username, password = creds
        throttle = request.app.state.throttle
        ip = request.client.host if request.client else "?"
        ukey, ikey = f"u:{username.strip().lower()}|{ip}", f"ip:{ip}"
        if throttle.blocked(ukey, USER_FAILS) or throttle.blocked(ikey, IP_FAILS):
            return Response("too many failed attempts", status_code=429, headers={"Retry-After": "60"})
        user, key = await service.print_login_with_key(request.app, username, password, ip)
        if user is None:
            register_failure(throttle, ukey, ikey, password)
            log.warning("auth failed user=%r ip=%s", username, ip)
            return _unauthorized("invalid credentials")
        throttle.clear(ukey)
        identity = user.username
        msg, head_rest, rest = await read_head(request)
        if key is not None and key.used_at is not None and msg.code not in STATUS_OPS:
            log.info("single-use key %s of %s already used: op=0x%04x refused", key.key_prefix, identity, msg.code)
            return _unauthorized("this single-use key has already been used")
        if msg.code in NEVER_OPS or (msg.code not in USER_OPS and not user.is_admin):
            log.warning("op 0x%04x denied for user=%s", msg.code, identity)
            return _ipp_error(msg, codec.STATUS_FORBIDDEN, "operation not permitted")

    # Identity comes from authentication, never from the client.
    og = msg.group(codec.TAG_OPERATION)
    if og is None:
        og = codec.Group(codec.TAG_OPERATION)
        msg.groups.insert(0, og)
    og.set("requesting-user-name", codec.TAG_NAME, settings.cups_user_prefix + identity)
    log.debug("ipp op=0x%04x path=/%s user=%s", msg.code, path, identity)

    tz = ZoneInfo(settings.timezone)
    sm = request.app.state.sessionmaker
    printer, mismatch = _printer_name(path, og)
    if mismatch:  # CUPS obeys printer-uri, the audit/quota would follow the HTTP path: refuse the ambiguity
        return _ipp_error(msg, codec.STATUS_BAD_REQUEST, "printer-uri does not match the request path")
    log_id: int | None = None
    pages: int | None = None
    if user is not None and msg.code in (codec.PRINT_JOB, codec.SEND_DOCUMENT) and await run_in_threadpool(_has_pages_rule, sm, user):
        # A pages limit exists: read the document (bounded) to count its pages before deciding.
        head_rest, rest, whole = await _buffer(head_rest, rest, pages_mod.MAX_COUNT_BYTES)
        if whole:
            fmt = og.get("document-format")
            n = await run_in_threadpool(pages_mod.count_pages, head_rest, fmt.first if fmt else None)
            if n:
                copies = msg.get(codec.TAG_JOB, "copies")
                pages = n * (copies if isinstance(copies, int) and copies > 0 else 1)
    # What the person's permissions say about this job (colour, one-sided, printer, hours); None = nothing limits them.
    perm = await _permissions(request, sm, user, printer, msg, tz) if user is not None and msg.code in PERMISSION_OPS else None
    listing = None  # the printers a limited person may see in a printer list
    if user is not None and msg.code in LISTING_OPS:
        listing = await run_in_threadpool(permissions.load, sm, user)
        if listing.printers is not None:
            _ask_for_names(og)
        else:
            listing = None
    if msg.code in SUBMIT_OPS:
        title, options = _job_info(og, msg)
        if pages:
            options["pages_counted"] = pages
        if perm is not None and perm.changed:
            options["adjusted"] = list(perm.changed)  # the audit shows what was asked (color, sides) and what was corrected
        decision, log_id = await run_in_threadpool(_reserve, sm, user, printer, title, options, tz, pages, perm)
        if not decision.allowed:
            log.info("job denied user=%s printer=%s reason=%s", identity, printer, decision.reason)
            refused = _refused_by(perm, decision)
            if refused:
                await run_in_threadpool(permissions.notify_refused, sm, user.id, printer, perm)
            return _ipp_error(msg, codec.STATUS_NOT_POSSIBLE, _with_portal_hint(request, decision.reason, permission=refused))
        if perm is not None:
            _apply_permission(msg, perm)
            if perm.changed:
                await run_in_threadpool(permissions.notify_adjusted, sm, user.id, printer, perm)
    elif msg.code == codec.VALIDATE_JOB and user is not None:
        decision = await run_in_threadpool(_peek, sm, user, tz, printer, perm)
        if not decision.allowed:
            return _ipp_error(msg, codec.STATUS_NOT_POSSIBLE, _with_portal_hint(request, decision.reason, permission=_refused_by(perm, decision)))
        if perm is not None:
            _apply_permission(msg, perm)
    elif msg.code == codec.SEND_DOCUMENT and user is not None:
        why = await run_in_threadpool(_blocked, sm, user, printer)
        if why:
            return _ipp_error(msg, codec.STATUS_NOT_POSSIBLE, why)

    if key is not None and key.single_use and msg.code in (codec.PRINT_JOB, codec.SEND_DOCUMENT):
        # the print was accepted: the key is spent. Two requests racing with the same key: one passes, the other is refused.
        if not await run_in_threadpool(_consume_key, sm, key.id):
            if log_id is not None:
                await run_in_threadpool(_finalize, sm, log_id, False, None, "single-use key already used")
            return _unauthorized("this single-use key has already been used")
        log.info("single-use key %s of %s used", key.key_prefix, identity)

    upstream: httpx.AsyncClient = request.app.state.upstream
    try:
        resp = await upstream.post(
            "/" + path,
            content=_body(codec.encode(msg) + (b"" if anonymous else head_rest), _no_more() if anonymous else rest,
                          settings.max_request_mb << 20),
            headers={"Content-Type": IPP_CT, "Host": "localhost"},
        )
    except httpx.HTTPError as exc:
        log.error("upstream error: %s", exc)
        if log_id is not None:
            await run_in_threadpool(_finalize, sm, log_id, False, None, "CUPS unreachable")
        raise HTTPException(502, "CUPS unreachable")
    except TooLarge:
        log.warning("request too large user=%s printer=%s", identity, printer)
        if log_id is not None:
            _finalize(sm, log_id, False, None, f"request larger than {settings.max_request_mb} MB")
        return _ipp_error(msg, codec.STATUS_TOO_LARGE, f"request larger than {settings.max_request_mb} MB")
    except BaseException:
        # client dropped the upload, task cancelled, bug...: the quota slot must not stay burned.
        # Synchronous on purpose: this also runs while the task is being cancelled.
        if log_id is not None:
            _finalize(sm, log_id, False, None, "aborted before reaching CUPS")
        raise

    body = resp.content
    out = None
    is_ipp = resp.headers.get("content-type", "").startswith(IPP_CT)
    if resp.status_code == 200 and is_ipp:
        try:
            out = codec.decode(body)
        except codec.IppError:
            log.warning("undecodable IPP response, passed through unchanged")
    elif not is_ipp:
        # CUPS answers policy refusals with HTML (401/403/426 = "authenticate/upgrade"). Never leak that
        # to an IPP client, where 426 would read as "switch to TLS": turn it into a plain IPP error.
        refused = resp.status_code in (401, 403, 426)
        log.warning("CUPS refused op=0x%04x user=%s: HTTP %s", msg.code, identity, resp.status_code)
        out = codec.make_error_response(
            codec.STATUS_FORBIDDEN if refused else 0x0500, msg.request_id,
            "not permitted by print server" if refused else "print server error",
        )
        out.version = msg.version
        resp = httpx.Response(200, headers={"content-type": IPP_CT}, content=codec.encode(out))

    ipp_ok = out is not None and out.code < 0x0100  # successful-ok*
    if log_id is not None:
        job_id = out.get(codec.TAG_JOB, "job-id") if out else None
        reason = None if ipp_ok else f"CUPS status {'0x%04x' % out.code if out else resp.status_code}"
        await run_in_threadpool(_finalize, sm, log_id, ipp_ok, job_id, reason)
    elif msg.code == codec.SEND_DOCUMENT and ipp_ok:
        jid = _job_id_from_request(og)
        if jid is not None:
            await run_in_threadpool(
                _attach, sm, user.id, jid, og.get("document-name") and og.get("document-name").first,
                og.get("document-format") and og.get("document-format").first, pages,
            )

    if out is not None and listing is not None and out.code < 0x0100:
        out.groups = [g for g in out.groups if g.tag != codec.TAG_PRINTER or _may_see(listing, g)]
    if out is not None:
        internal = {"localhost", "127.0.0.1", "::1", urlsplit(settings.cups_url).hostname or ""}
        rewrite_uris(out, internal, *_public_bases(request))
        advertise_auth(out)
        _hide_internal(out)
        body = codec.encode(out)

    log.info("ipp op=0x%04x user=%s path=%s -> %s", msg.code, identity, "/" + path,
             "0x%04x" % out.code if out is not None else resp.status_code)
    return Response(body, status_code=resp.status_code, media_type=resp.headers.get("content-type", IPP_CT))


# ---- helpers (sync ones run in the threadpool)

def _with_portal_hint(request: Request, reason: str | None, permission: bool = False) -> str:
    """Where to go when a limit is reached: some clients show the status message to the user."""
    if reason in (control.BLOCKED_REASON, control.MAINTENANCE_REASON):
        return reason  # nothing to ask for: more quota would not help
    base = settings.portal_url.rstrip("/") or f"https://{request.headers.get('host', 'localhost')}"
    if permission:  # more quota would not help here either: the profile page says what the account may do
        return f"{reason}. To see what you may print: {base}/me"
    return f"{reason or 'not allowed'}. To ask for more quota: {base}/me"


def _refused_by(perm: permissions.PermDecision | None, decision: Decision) -> bool:
    """Was `decision` the refusal of the permissions (and not a blocked printer or the quota that came first or after)?"""
    return perm is not None and not perm.allowed and decision.reason == perm.reason


def _job_attrs(msg: codec.IppMessage) -> dict:
    """The values of the options the permissions care about. Job options belong in the job group, but some clients put them
    in the operation group: both are read (the job group wins)."""
    out: dict = {}
    for tag in (codec.TAG_OPERATION, codec.TAG_JOB):
        for g in msg.groups:
            if g.tag == tag:
                for a in g.attrs:
                    if a.name in PERM_ATTRS and isinstance(a.first, str):
                        out[a.name] = a.first
    return out


async def _permissions(request: Request, sm, user, printer, msg, tz) -> permissions.PermDecision | None:
    perms = await run_in_threadpool(permissions.load, sm, user)
    if not perms.restricted:
        return None
    # the printer is asked what it can do only when colour or sides matter (and it is not refused for another reason anyway)
    need_caps = printer and permissions.printer_allowed(perms, printer) and not (perms.color and perms.one_sided)
    caps = await queue_caps(request.app, printer) if need_caps else dict(UNKNOWN_CAPS)
    return permissions.decide(perms, printer, caps, _job_attrs(msg), settings.permission_mode, audit.now_utc(), ZoneInfo(settings.timezone))


def _apply_permission(msg: codec.IppMessage, d: permissions.PermDecision) -> None:
    """Write the corrections into the request before it goes to CUPS: the attributes are taken out of the operation and job
    groups and the new values put in the job group (made if the client sent none)."""
    names = set(d.set_attrs) | d.drop_attrs
    if not names:
        return
    for g in msg.groups:
        if g.tag in (codec.TAG_OPERATION, codec.TAG_JOB):
            g.attrs = [a for a in g.attrs if a.name not in names]
    job = msg.group(codec.TAG_JOB)
    if job is None:
        job = codec.Group(codec.TAG_JOB, [])
        msg.groups.append(job)
    for name, value in d.set_attrs.items():
        job.attrs.append(codec.Attr(name, [codec.Val(codec.TAG_KEYWORD, value)]))


def _ask_for_names(og: codec.Group) -> None:
    """A printer list is filtered by name: make sure CUPS says the names, whatever attributes the client asked for."""
    a = og.get("requested-attributes")
    if a is not None and not any(v.value in ("all", "printer-name") for v in a.values):
        a.values.append(codec.Val(codec.TAG_KEYWORD, "printer-name"))


def _may_see(perms: permissions.Perms, group: codec.Group) -> bool:
    name = group.get("printer-name")
    return name is not None and isinstance(name.first, str) and permissions.printer_allowed(perms, name.first)


def _queue_of(path: str) -> str | None:
    parts = [unquote(p) for p in path.split("/") if p]
    return parts[1] if len(parts) >= 2 and parts[0] in ("printers", "classes") else None


def _printer_name(path: str, og: codec.Group) -> tuple[str | None, bool]:
    """(queue name, mismatch). CUPS prints on printer-uri, so that is what we must account for;
    when the HTTP path names another queue the request is ambiguous and gets refused."""
    a = og.get("printer-uri")
    from_uri = _queue_of(urlsplit(a.first).path) if a and isinstance(a.first, str) else None
    from_path = _queue_of(path)
    if from_uri and from_path and from_uri.lower() != from_path.lower():  # CUPS queue names ignore case
        return from_path, True
    return from_uri or from_path, False


def _job_info(og: codec.Group, msg: codec.IppMessage | None = None) -> tuple[str, dict]:
    """Title (file name as the client reports it) plus the details worth auditing."""
    def val(name):
        a = og.get(name)
        return a.first if a else None

    doc_name, job_name = val("document-name"), val("job-name")
    options = {}
    if doc_name:
        options["document_name"] = doc_name
    if val("document-format"):
        options["document_format"] = val("document-format")
    if msg is not None:  # what the client asked for; absent = the printer's own default
        for ipp_name, key in (("print-color-mode", "color"), ("sides", "sides")):
            v = msg.get(codec.TAG_JOB, ipp_name)
            if isinstance(v, str):
                options[key] = v
    return (job_name or doc_name or "untitled")[:512], options


def _job_id_from_request(og: codec.Group) -> int | None:
    a = og.get("job-id")
    if a and isinstance(a.first, int):
        return a.first
    a = og.get("job-uri")
    if a and isinstance(a.first, str):
        tail = urlsplit(a.first).path.rstrip("/").rsplit("/", 1)[-1]
        return int(tail) if tail.isdigit() else None
    return None


def _reserve(sm, user, printer, title, options, tz, pages=None, deny=None):
    with sm() as session:
        return audit.reserve(session, user, printer, title, options, tz, pages, deny=deny)


def _has_pages_rule(sm, user) -> bool:
    with sm() as session:
        return any(r.metric is Metric.pages for r in effective_rules(session, user, Resource.print))


async def _buffer(head: bytes, rest: AsyncIterator[bytes], cap: int) -> tuple[bytes, AsyncIterator[bytes], bool]:
    """Collect the document if it fits in `cap`; otherwise hand back what was read plus the unread remainder."""
    buf = bytearray(head)
    async for chunk in rest:
        buf += chunk
        if len(buf) > cap:
            return bytes(buf), rest, False
    return bytes(buf), _no_more(), True


def _peek(sm, user, tz, printer=None, perm=None):
    """Would a job be accepted? Same order as `audit.reserve`: blocked printer, permissions, quota."""
    with sm() as session:
        why = control.block_reason(session, user, printer)
        if why:
            return Decision(False, why)
        if perm is not None and not perm.allowed:
            return Decision(False, perm.reason, perm.localized)
        return check_job(session, user, Resource.print, audit.now_utc(), tz)


def _consume_key(sm, key_id):
    with sm() as session:
        row = session.get(PrintKey, key_id)
        return row is not None and keys.consume(session, row)


def _blocked(sm, user, printer):
    with sm() as session:
        return control.block_reason(session, user, printer)


def _finalize(sm, log_id, ok, job_id, reason):
    with sm() as session:
        audit.finalize(session, log_id, ok, job_id, reason)


def _attach(sm, user_id, job_id, name, fmt, pages=None):
    with sm() as session:
        audit.attach_document(session, user_id, job_id, name, fmt, pages)


def _hide_internal(msg: codec.IppMessage) -> None:
    """Drop CUPS-internal attributes clients have no business seeing."""
    for g in msg.groups:
        g.attrs = [a for a in g.attrs if a.name != "device-uri"]
