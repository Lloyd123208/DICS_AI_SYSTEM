from __future__ import annotations

from typing import Iterable

from flask import session


ROLE_ALIASES = {
    'citizen': 'CITIZEN',
    'user': 'CITIZEN',
    'field_responder': 'RESPONDER',
    'responder': 'RESPONDER',
    'agency_coordinator': 'COORDINATOR',
    'coordinator': 'COORDINATOR',
    'incident_commander': 'COMMANDER',
    'commander': 'COMMANDER',
    'eoc_staff': 'EOC',
    'eoc': 'EOC',
    'admin': 'ADMIN',
}


def normalize_role(role: str | None) -> str | None:
    if not role:
        return None
    return ROLE_ALIASES.get(str(role).strip().lower(), str(role).strip().upper())


def current_role() -> str | None:
    try:
        return normalize_role(session.get('role'))
    except RuntimeError:
        return None


def is_authenticated() -> bool:
    return bool(session.get('username'))


def has_any_role(*roles: str) -> bool:
    role = current_role()
    if not role:
        return False
    return role in {normalize_role(r) for r in roles}


def user_has_any_role(user, *roles: str) -> bool:
    role = normalize_role(getattr(user, 'role', None))
    if not role:
        return False
    return role in {normalize_role(r) for r in roles}


def is_citizen() -> bool:
    return has_any_role('CITIZEN')


def is_responder() -> bool:
    return has_any_role('RESPONDER')


def is_coordinator() -> bool:
    return has_any_role('COORDINATOR')


def is_commander() -> bool:
    return has_any_role('COMMANDER')


def is_eoc() -> bool:
    return has_any_role('EOC')


def is_admin() -> bool:
    return has_any_role('ADMIN')


def can_view_incident(user, incident) -> bool:
    if not user or not incident:
        return False
    if is_admin():
        return True
    if is_citizen():
        return getattr(incident, 'user_id', None) == user.id
    if is_responder():
        return True
    if is_coordinator() or is_commander() or is_eoc():
        return True
    return False


def can_edit_incident(user, incident) -> bool:
    if not user or not incident:
        return False
    if is_admin():
        return True
    if is_citizen():
        return getattr(incident, 'user_id', None) == user.id
    if is_coordinator() or is_commander() or is_eoc():
        return True
    return False


def can_assign_task(user, incident) -> bool:
    if not user or not incident:
        return False
    return is_admin() or is_coordinator() or is_commander() or is_eoc()


def can_allocate_resource(user, resource) -> bool:
    if not user or not resource:
        return False
    return is_admin() or is_coordinator() or is_commander() or is_eoc()


def can_verify_incident(user) -> bool:
    return is_admin() or is_eoc()


def can_issue_alert(user) -> bool:
    return is_admin() or is_commander() or is_eoc()


def can_manage_users(user) -> bool:
    return is_admin()


def can_view_analytics(user) -> bool:
    return is_admin() or is_coordinator() or is_commander() or is_eoc()
