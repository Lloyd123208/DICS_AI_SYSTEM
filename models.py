from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from datetime import datetime

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """SQLite does not enforce foreign key constraints by default. Without
    this, deleting a row (including via raw SQL or a database tool) can
    silently leave dependent rows pointing at nothing -- e.g. an
    IncidentResponse whose incident_id no longer matches any Incident. That
    orphaned state is what caused 500s/404s when a commander opened an
    incident response tied to a missing incident. Turning this on makes the
    ondelete='CASCADE' rules below actually apply."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        # Non-SQLite engines (e.g. Postgres in production) don't need this
        # and don't support this pragma; ignore quietly.
        pass


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(150), nullable=True)
    contact_number = db.Column(db.String(20), nullable=True)
    agency = db.Column(db.String(150), nullable=True)
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(500), nullable=True)
    role = db.Column(db.String(20), default='user')
    is_disabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    incidents = db.relationship('Incident', foreign_keys='[Incident.user_id]', backref='user', lazy=True)
    citizen_reports = db.relationship('CitizenReport', backref='user', lazy=True)
    alerts = db.relationship('Alert', backref='user', lazy=True, cascade='all, delete-orphan')
    reports = db.relationship('Report', backref='user', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('Message', foreign_keys='[Message.sender_id]', backref='sender', lazy=True, cascade='all, delete-orphan')
    received_messages = db.relationship('Message', foreign_keys='[Message.recipient_id]', backref='recipient', lazy=True)
    audit_events = db.relationship('AuditEvent', backref='user', lazy=True, cascade='all, delete-orphan')
    ai_recommendations = db.relationship('AIRecommendation', backref='user', lazy=True, cascade='all, delete-orphan')

    @property
    def password_hash(self):
        return self.password


class Agency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Province(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=True)
    name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    municipalities = db.relationship('Municipality', backref='province', lazy=True, cascade='all, delete-orphan')


class Municipality(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    province_id = db.Column(db.Integer, db.ForeignKey('province.id'), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=True)
    name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    barangays = db.relationship('Barangay', backref='municipality', lazy=True, cascade='all, delete-orphan')


class Barangay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    municipality_id = db.Column(db.Integer, db.ForeignKey('municipality.id'), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=True)
    name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CitizenReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    hazard_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    affected_people = db.Column(db.Integer, nullable=True)
    injuries = db.Column(db.Integer, nullable=True)
    contact = db.Column(db.String(30), nullable=True)
    gps_latitude = db.Column(db.Float, nullable=True)
    gps_longitude = db.Column(db.Float, nullable=True)
    province_id = db.Column(db.Integer, db.ForeignKey('province.id'), nullable=True)
    municipality_id = db.Column(db.Integer, db.ForeignKey('municipality.id'), nullable=True)
    barangay_id = db.Column(db.Integer, db.ForeignKey('barangay.id'), nullable=True)
    anonymous = db.Column(db.Boolean, default=False)
    photo_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Incident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    hazard_type = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(255), nullable=True)
    rainfall_mm = db.Column(db.Float, nullable=True)
    river_level_m = db.Column(db.Float, nullable=True)
    humidity_pct = db.Column(db.Float, nullable=True)
    population_density = db.Column(db.Float, nullable=True)
    score = db.Column(db.Float, nullable=True)
    level = db.Column(db.String(20), nullable=True)
    message = db.Column(db.String(255), nullable=False)
    alert = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='NEW')
    verified_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    citizen_report_id = db.Column(db.Integer, db.ForeignKey('citizen_report.id'), nullable=True)
    reported_by = db.Column(db.String(50), nullable=True)
    province_id = db.Column(db.Integer, db.ForeignKey('province.id'), nullable=True)
    municipality_id = db.Column(db.Integer, db.ForeignKey('municipality.id'), nullable=True)
    barangay_id = db.Column(db.Integer, db.ForeignKey('barangay.id'), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    citizen_report = db.relationship('CitizenReport', backref=db.backref('incident', uselist=False), foreign_keys=[citizen_report_id])
    response = db.relationship('IncidentResponse', backref='incident', lazy=True, uselist=False, cascade='all, delete-orphan')
    verifier = db.relationship('User', foreign_keys=[verified_by_id], backref='verified_incidents')
    reports = db.relationship('Report', backref='incident', lazy=True, cascade='all, delete-orphan')
    alerts = db.relationship('Alert', backref='incident', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='incident', lazy=True, cascade='all, delete-orphan')
    ai_recommendations = db.relationship('AIRecommendation', backref='incident', lazy=True, cascade='all, delete-orphan')
    incident_reports = db.relationship('IncidentReport', backref='incident', lazy=True, cascade='all, delete-orphan')
    resource_requests = db.relationship('ResourceRequest', backref='incident', lazy=True, cascade='all, delete-orphan')


class IncidentResponse(db.Model):
    """Active incident response coordination"""
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incident.id', ondelete='CASCADE'), nullable=False)
    commander_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='ACTIVE')  # ACTIVE, MONITORING, RESOLVED, CLOSED
    situation_summary = db.Column(db.Text, nullable=True)
    priority_level = db.Column(db.String(20), default='MEDIUM')  # LOW, MEDIUM, HIGH, CRITICAL
    affected_population = db.Column(db.Integer, nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    commander = db.relationship('User', backref='incident_responses')
    tasks = db.relationship('Task', backref='incident_response', lazy=True, cascade='all, delete-orphan')
    resources = db.relationship('Resource', backref='incident_response', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('IncidentMessage', backref='incident_response', lazy=True, cascade='all, delete-orphan')


class Task(db.Model):
    """Incident response tasks assigned to agencies"""
    id = db.Column(db.Integer, primary_key=True)
    incident_response_id = db.Column(db.Integer, db.ForeignKey('incident_response.id', ondelete='CASCADE'), nullable=False)
    assigned_to_agency = db.Column(db.String(150), nullable=False)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='PENDING')  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    priority = db.Column(db.String(20), default='MEDIUM')  # LOW, MEDIUM, HIGH, CRITICAL
    estimated_completion = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assigned_by = db.relationship('User', backref='assigned_tasks', foreign_keys=[assigned_by_id])


class IncidentMessage(db.Model):
    """Unified inter-role incident communications log."""
    id = db.Column(db.Integer, primary_key=True)
    incident_response_id = db.Column(db.Integer, db.ForeignKey('incident_response.id', ondelete='CASCADE'), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    report_type = db.Column(db.String(50), default='UPDATE')
    source = db.Column(db.String(20), default='coordinator')
    affected_areas = db.Column(db.String(500), nullable=True)
    casualties = db.Column(db.Integer, nullable=True)
    evacuated = db.Column(db.Integer, nullable=True)
    gps_latitude = db.Column(db.Float, nullable=True)
    gps_longitude = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reporter = db.relationship('User', backref='incident_messages', foreign_keys=[reporter_id])


class PostIncidentReport(db.Model):
    """Structured lessons learned and feedback after an incident response closes."""
    id = db.Column(db.Integer, primary_key=True)
    incident_response_id = db.Column(db.Integer, db.ForeignKey('incident_response.id', ondelete='CASCADE'), nullable=False, unique=True)
    lessons_learned = db.Column(db.Text, nullable=True)
    response_rating = db.Column(db.Integer, nullable=True)
    recommendations = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    incident_response = db.relationship('IncidentResponse', backref=db.backref('post_incident_report', cascade='all, delete-orphan'), uselist=False)


class Resource(db.Model):
    """Resource allocation tracking"""
    id = db.Column(db.Integer, primary_key=True)
    incident_response_id = db.Column(db.Integer, db.ForeignKey('incident_response.id', ondelete='CASCADE'), nullable=False)
    resource_type = db.Column(db.String(100), nullable=False)  # Personnel, Equipment, Vehicles, Supplies, etc.
    agency = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='AVAILABLE')  # AVAILABLE, DEPLOYED, RETURNING, UNAVAILABLE
    location = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    allocated_at = db.Column(db.DateTime, default=datetime.utcnow)
    deployed_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Facility(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    facility_type = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    province_id = db.Column(db.Integer, db.ForeignKey('province.id'), nullable=True)
    municipality_id = db.Column(db.Integer, db.ForeignKey('municipality.id'), nullable=True)
    barangay_id = db.Column(db.Integer, db.ForeignKey('barangay.id'), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EvacuationCenter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, db.ForeignKey('facility.id'), nullable=False)
    capacity = db.Column(db.Integer, nullable=True)
    occupancy = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='OPEN')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IncidentReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incident.id', ondelete='CASCADE'), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    report_type = db.Column(db.String(50), nullable=False, default='SITUATIONAL')
    summary = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResourceRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incident.id', ondelete='CASCADE'), nullable=False)
    resource_type = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(20), default='OPEN')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AIRecommendation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incident.id', ondelete='CASCADE'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    recommendation_type = db.Column(db.String(100), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    confidence_score = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    entity_type = db.Column(db.String(100), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incident.id', ondelete='CASCADE'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default='MEDIUM')
    status = db.Column(db.String(20), default='ACTIVE')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incident.id', ondelete='CASCADE'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    report_type = db.Column(db.String(50), default='GENERAL')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incident.id', ondelete='CASCADE'), nullable=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


