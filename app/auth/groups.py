"""The two groups every installation has: "default" (where everybody starts) and "administrator"."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Group, User

ADMIN_GROUP = "administrator"


def system_group_names() -> set[str]:
    return {settings.default_group, ADMIN_GROUP}


def _get_or_create(db: Session, name: str) -> Group:
    g = db.scalars(select(Group).where(Group.name == name)).first()
    if g is None:
        g = Group(name=name)
        db.add(g)
        db.flush()
    return g


def set_admin(db: Session, user: User, flag: bool) -> None:
    """Promote/demote and move the account: administrators live in "administrator", demoted ones go back to "default"."""
    user.is_admin = bool(flag)
    if flag:
        user.group_id = _get_or_create(db, ADMIN_GROUP).id
    else:
        admin_group = db.scalars(select(Group).where(Group.name == ADMIN_GROUP)).first()
        if admin_group is not None and user.group_id == admin_group.id:
            user.group_id = _get_or_create(db, settings.default_group).id


def ensure_system_groups(sm) -> None:
    """At start: both groups exist; every administrator is in "administrator", nobody else is."""
    with sm() as db:
        default, admins = _get_or_create(db, settings.default_group), _get_or_create(db, ADMIN_GROUP)
        for u in db.scalars(select(User)):
            if u.is_admin and u.group_id != admins.id:
                u.group_id = admins.id
            elif not u.is_admin and u.group_id == admins.id:
                u.group_id = default.id
        db.commit()
