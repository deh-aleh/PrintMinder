"""Count the pages of a document before it is printed, so the pages limit can be enforced for real.

Only formats whose page count can be read cheaply and reliably are counted; for anything else the answer is None
and the (soft) behaviour applies: the real page count is recorded after CUPS has printed the job.
"""

import io
import math
import re
import struct
from app.i18n import _, ngettext

MAX_COUNT_BYTES = 64 << 20  # larger documents are streamed, not buffered, and counted afterwards


def sniff(data: bytes, declared: str | None = None) -> str | None:
    """What the bytes really are (a client may say octet-stream or lie)."""
    head = data[:16]
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"UNIRAST\x00"):
        return "image/urf"
    if head.startswith(b"%!PS"):
        return "application/postscript"
    if declared in ("text/plain", None, "application/octet-stream") and b"\x00" not in data[:2048]:
        return "text/plain" if declared == "text/plain" else None
    return None


def count_pages(data: bytes, declared: str | None = None) -> int | None:
    kind = sniff(data, declared)
    try:
        if kind == "application/pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                return None
            return max(1, len(reader.pages))
        if kind in ("image/jpeg", "image/png", "image/gif"):
            return 1
        if kind == "image/urf":
            return max(1, struct.unpack(">I", data[8:12])[0])
        if kind == "application/postscript":
            m = re.search(rb"%%Pages:\s*(\d+)", data[:65536]) or re.search(rb"%%Pages:\s*(\d+)", data[-65536:])
            return max(1, int(m.group(1))) if m else None
        if kind == "text/plain":
            lines = data.count(b"\n") + 1
            return max(1, math.ceil(lines / 60))  # CUPS text filter: about 60 lines per page
    except Exception:  # damaged file: let CUPS decide, the real count is recorded afterwards
        return None
    return None


def parse_ranges(text: str) -> list[tuple[int, int]]:
    """"1,5" / "2-4, 7" / "3-" -> [(lo, hi)], hi = 0 meaning "to the end". Raises ValueError with a readable message."""
    out: list[tuple[int, int]] = []
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d{1,5})(?:(-)(\d{0,5}))?", part)
        if not m:
            raise ValueError(_("Invalid pages: “%(part)s”. Example: 1,5 or 2-4", part=part))
        lo = int(m.group(1))
        hi = int(m.group(3)) if m.group(3) else (0 if m.group(2) else lo)
        if lo < 1 or (hi and hi < lo):
            raise ValueError(_("Invalid range: “%(part)s”", part=part))
        out.append((lo, hi))
    if len(out) > 32:
        raise ValueError(_("Too many page ranges"))
    return out


def pages_in_ranges(ranges: list[tuple[int, int]], total: int | None) -> int | None:
    """How many distinct pages the ranges select. Needs `total` when a range is open-ended. Raises ValueError if the
    ranges select nothing from a document of known length."""
    if not ranges:
        return total
    if total is None:
        return None if any(hi == 0 for _, hi in ranges) else len({p for lo, hi in ranges for p in range(lo, hi + 1)})
    chosen = {p for lo, hi in ranges for p in range(lo, (hi or total) + 1) if p <= total}
    if not chosen:
        raise ValueError(ngettext("The document has only %(n)s page", "The document has only %(n)s pages", total))
    return len(chosen)
