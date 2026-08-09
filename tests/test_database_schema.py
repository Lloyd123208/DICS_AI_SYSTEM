import unittest

from app import app, db
from models import (
    Agency,
    Alert,
    AIRecommendation,
    AuditEvent,
    Barangay,
    EvacuationCenter,
    Facility,
    Incident,
    IncidentReport,
    Message,
    Municipality,
    Province,
    Report,
    Resource,
    ResourceRequest,
    Task,
    User,
)


class DatabaseSchemaTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_core_and_expanded_models_are_registered(self):
        self.assertTrue(User.__tablename__)
        self.assertTrue(Agency.__tablename__)
        self.assertTrue(Incident.__tablename__)
        self.assertTrue(Task.__tablename__)
        self.assertTrue(Resource.__tablename__)
        self.assertTrue(Alert.__tablename__)
        self.assertTrue(Report.__tablename__)
        self.assertTrue(Message.__tablename__)
        self.assertTrue(Province.__tablename__)
        self.assertTrue(Municipality.__tablename__)
        self.assertTrue(Barangay.__tablename__)
        self.assertTrue(Facility.__tablename__)
        self.assertTrue(EvacuationCenter.__tablename__)
        self.assertTrue(IncidentReport.__tablename__)
        self.assertTrue(ResourceRequest.__tablename__)
        self.assertTrue(AIRecommendation.__tablename__)
        self.assertTrue(AuditEvent.__tablename__)


if __name__ == '__main__':
    unittest.main()
