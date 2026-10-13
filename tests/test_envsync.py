import os
import stat
from datetime import datetime
from pathlib import Path

import pytest

from app import envsync
from app.config import Settings

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = (
    "# header of the file\n\n"
    "# --- Section one ---\n# what ONE does\nONE=1\n\n"
    "# what TWO does\n# second line\nTWO=2\n\n"
    "# an example, off by default\n#THREE=3\n\n"
    "# the session key\nSECRET=__GENERATED__\n\n"
    "# where it runs\nWHERE=__PROJECT_DIR__/data\n\n"
    "# decided at install\nPRINTGW_VERSION=__VERSION__\n\n"
    "# needs a value this run does not have\nLATER=__UNKNOWN__\n"
)
VALUES = {"PUID": "1000", "PGID": "1000", "PROJECT_DIR": "/srv/pm", "VERSION": "1.2.3"}


def test_blocks_keep_their_comments_and_commented_examples_count_as_options():
    blocks = {b["key"]: b for b in envsync.parse(TEMPLATE)}
    assert list(blocks) == ["ONE", "TWO", "THREE", "SECRET", "WHERE", "PRINTGW_VERSION", "LATER"]
    assert blocks["TWO"]["lines"] == ["# what TWO does", "# second line", "TWO=2"]
    assert blocks["THREE"]["active"] is False
    assert envsync.keys_in("A=1\n#B=2\n# C=3 is prose\n  D=4\n") == {"A", "B"}


def test_only_new_options_are_added_values_stay_and_a_backup_is_kept(tmp_path):
    tpl, target = tmp_path / "t", tmp_path / ".env"
    tpl.write_text(TEMPLATE)
    target.write_text("ONE=my-own-value\nEXTRA=mine\n#THREE=changed\n")
    target.chmod(0o600)
    added = envsync.sync_file(tpl, target, VALUES, check=False, today=datetime(2026, 10, 13, 12, 0, 0))
    assert added == ["TWO", "WHERE"]                      # THREE exists (commented), SECRET/VERSION/LATER are never added
    text = target.read_text()
    assert text.startswith("ONE=my-own-value\nEXTRA=mine\n#THREE=changed\n")     # what was there is untouched, in order
    assert "# what TWO does\n# second line\nTWO=2" in text and "WHERE=/srv/pm/data" in text
    assert "SECRET" not in text and "PRINTGW_VERSION" not in text and "LATER" not in text
    backup = tmp_path / ".env.bak-20261013-120000"
    assert backup.read_text() == "ONE=my-own-value\nEXTRA=mine\n#THREE=changed\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600 and stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert envsync.sync_file(tpl, target, VALUES, check=False) == []              # a second run changes nothing
    assert len(list(tmp_path.glob(".env.bak-*"))) == 1


def test_check_writes_nothing(tmp_path):
    tpl, target = tmp_path / "t", tmp_path / ".env"
    tpl.write_text(TEMPLATE)
    target.write_text("ONE=1\n")
    assert envsync.sync_file(tpl, target, VALUES, check=True) == ["TWO", "THREE", "WHERE"]
    assert target.read_text() == "ONE=1\n" and not list(tmp_path.glob("*.bak-*"))


def test_init_makes_missing_files_with_a_secret_and_never_overwrites(tmp_path):
    (tmp_path / "docker").mkdir()
    for name in ("env.example", "gateway.env.example"):
        (tmp_path / "docker" / name).write_text((ROOT / "docker" / name).read_text())
    assert envsync.main(["--init", "--root", str(tmp_path), "--project-dir", "/srv/pm", "--uid", "1234", "--gid", "55"]) == 0
    env, gw = (tmp_path / ".env").read_text(), (tmp_path / "config/gateway.env").read_text()
    assert "PUID=1234" in env and "PGID=55" in env and "PROJECT_DIR=/srv/pm" in env and "__" not in env
    key = [l for l in gw.splitlines() if l.startswith("CUPSPL_SECRET_KEY=")][0].split("=", 1)[1]
    assert len(key) >= 40 and "__GENERATED__" not in gw
    assert stat.S_IMODE((tmp_path / "config/gateway.env").stat().st_mode) == 0o600
    (tmp_path / ".env").write_text("PUID=7\n")
    envsync.main(["--init", "--root", str(tmp_path)])
    assert (tmp_path / ".env").read_text().startswith("PUID=7\n")                # an existing file is never rewritten: at most added to


def test_every_option_of_the_real_templates_can_be_added_without_changing_behaviour():
    """An option added to an old install carries its template value: it must be the same as the program's own default,
    otherwise adding it would change how an installed gateway behaves."""
    defaults = Settings(_env_file=None)
    template = (ROOT / "docker" / "gateway.env.example").read_text()
    checked = 0
    for b in envsync.parse(template):
        if not b["active"] or not b["key"].startswith("CUPSPL_") or "__GENERATED__" in b["lines"][-1]:
            continue
        field, raw = b["key"][len("CUPSPL_"):].lower(), b["lines"][-1].split("=", 1)[1]
        if field == "timezone":
            continue                                                            # always present in installs: set by the user
        assert hasattr(defaults, field), f"{b['key']} is in the template but is not a setting"
        assert getattr(Settings(_env_file=None, **{field: raw}), field) == getattr(defaults, field), \
            f"{b['key']}={raw!r} in gateway.env.example differs from the default in app/config.py"
        checked += 1
    assert checked > 30
