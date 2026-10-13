"""Create .env and config/gateway.env, and add the options a new version brings to the ones that already exist.

    python -m app.envsync --init  --root DIR      make the files that are missing (a first install)
    python -m app.envsync         --root DIR      add the options that are missing, with their comments
    python -m app.envsync --check --root DIR      only say what would be added

The templates (docker/env.example and docker/gateway.env.example) hold every option with its explanation. A file that
exists is only ever ADDED to, at the end: no value is changed, nothing is reordered or removed. An option counts as
present when its line exists, also when it is commented out (#NAME=...). Options that only make sense at install time
(the version and the image registry) are never added to an existing file. Uses only the Python standard library, so it
runs on the host and inside the gateway image alike.
"""

import argparse
import os
import re
import secrets
import shutil
import sys
import tomllib
from datetime import datetime
from pathlib import Path

VAR = re.compile(r"^#?([A-Z][A-Z0-9_]*)=")   # "NAME=value" or "#NAME=value" (a commented example); "# NAME=..." is prose
INSTALL_ONLY = {"PRINTGW_REGISTRY", "PRINTGW_VERSION"}   # decided once by docker-init.sh, changed by update.sh only
TARGETS = (("docker/env.example", ".env"), ("docker/gateway.env.example", "config/gateway.env"))
SYSTEM_TEMPLATES = Path("/usr/share/printminder")        # where the gateway image keeps the templates


def parse(text: str) -> list[dict]:
    """The template as blocks: the comment lines before an option, and the option line itself."""
    blocks, pending = [], []
    for line in text.splitlines():
        m = VAR.match(line)
        if m:
            while pending and not pending[0].strip():
                pending.pop(0)
            blocks.append({"key": m.group(1), "lines": pending + [line], "active": not line.startswith("#")})
            pending = []
        else:
            pending.append(line)
    return blocks


def keys_in(text: str) -> set[str]:
    return {m.group(1) for m in (VAR.match(line) for line in text.splitlines()) if m}


def version_of(root: Path) -> str:
    try:
        return tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    except (OSError, KeyError, ValueError):
        from importlib import metadata
        try:
            return metadata.version("cups-policy-gateway")
        except metadata.PackageNotFoundError:
            return "0.0.0"


def fill(text: str, values: dict[str, str]) -> str | None:
    """Replace the __NAME__ markers; None when one is left over (a value this run does not know)."""
    for name, value in values.items():
        text = text.replace(f"__{name}__", value)
    return None if re.search(r"__[A-Z_]+__", text) else text


def render(template: str, values: dict[str, str]) -> str:
    """A whole template for a first install."""
    return fill(template, values) or template


def values_for(root: Path, project_dir: str, uid: int, gid: int) -> dict[str, str]:
    return {"PUID": str(uid), "PGID": str(gid), "PROJECT_DIR": project_dir, "VERSION": version_of(root)}


def find_template(rel: str, root: Path) -> Path:
    for base in (root, SYSTEM_TEMPLATES):
        p = base / rel if base == root else base / Path(rel).name
        if p.is_file():
            return p
    raise FileNotFoundError(f"template {rel} not found (looked in {root} and {SYSTEM_TEMPLATES})")


def missing_blocks(template: str, existing: str, values: dict[str, str]) -> list[dict]:
    have = keys_in(existing)
    out = []
    for b in parse(template):
        if b["key"] in have or b["key"] in INSTALL_ONLY or "__GENERATED__" in "\n".join(b["lines"]):
            continue
        text = fill("\n".join(b["lines"]), values)
        if text is not None:
            out.append({"key": b["key"], "text": text})
    return out


def sync_file(template: Path, target: Path, values: dict[str, str], check: bool, today: datetime | None = None) -> list[str]:
    """Add the missing options to `target`; returns their names. With `check` nothing is written."""
    existing = target.read_text()
    add = missing_blocks(template.read_text(), existing, values)
    if not add or check:
        return [b["key"] for b in add]
    stamp = (today or datetime.now()).strftime("%Y%m%d-%H%M%S")
    backup = target.with_name(f"{target.name}.bak-{stamp}")
    shutil.copy2(target, backup)                       # keeps the permissions: gateway.env holds secrets (mode 600)
    body = existing if existing.endswith("\n") else existing + "\n"
    body += f"\n# ===== added by scripts/env-sync.sh on {stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}: new options, with their default values =====\n"
    body += "\n\n".join(b["text"] for b in add) + "\n"
    tmp = target.with_name(f".{target.name}.tmp")
    shutil.copy2(target, tmp)
    tmp.write_text(body)
    tmp.replace(target)
    return [b["key"] for b in add]


def init_file(template: Path, target: Path, values: dict[str, str]) -> bool:
    if target.exists():
        return False
    values = {**values, "GENERATED": secrets.token_urlsafe(48)}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(template.read_text(), values))
    target.chmod(0o600)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=".", help="the project folder (where .env and config/ are)")
    ap.add_argument("--project-dir", default="", help="the same folder as the host sees it (when this runs in a container)")
    ap.add_argument("--init", action="store_true", help="create the files that are missing")
    ap.add_argument("--check", action="store_true", help="only list what would be added")
    ap.add_argument("--uid", type=int, default=None)
    ap.add_argument("--gid", type=int, default=None)
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    values = values_for(root, args.project_dir or str(root), os.getuid() if args.uid is None else args.uid,
                        os.getgid() if args.gid is None else args.gid)
    changed = 0
    for tmpl_rel, target_rel in TARGETS:
        template, target = find_template(tmpl_rel, root), root / target_rel
        if not target.exists():
            if args.init:
                init_file(template, target, values)
                print(f"created {target_rel}")
            continue
        added = sync_file(template, target, values, args.check)
        if added:
            changed += len(added)
            print(f"{target_rel}: {'would add' if args.check else 'added'} {len(added)} new option(s): {', '.join(added)}")
    if not changed and not args.init:
        print("nothing to add: every option of this version is already in your files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
