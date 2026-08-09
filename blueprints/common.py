from flask import session

from models import User
import services.permissions as permission_service


def is_admin():
    """Backward-compatible helper delegating to the shared permission module."""
    return permission_service.is_admin()


def is_admin_or_coordinator():
    """Check if user is admin or coordinator (for viewing/managing agency operations)."""
    return is_admin() or permission_service.is_coordinator()


def is_incident_commander():
    return is_admin() or permission_service.is_commander()


def is_admin_coordinator_or_commander():
    return is_admin() or permission_service.is_coordinator() or permission_service.is_commander()


def is_field_responder():
    return permission_service.is_responder()


def is_eoc_staff():
    return permission_service.is_eoc()


def is_admin_or_eoc():
    """Check if user is admin or EOC staff (for dispatch-style operations:
    verifying incidents, assigning/transferring commanders, toggling alerts)."""
    return is_admin() or permission_service.is_eoc()


def is_coordinator():
    return permission_service.is_coordinator()


def get_coordinator_agency():
    user = User.query.filter_by(username=session.get('username')).first()
    return user.agency if user else None
