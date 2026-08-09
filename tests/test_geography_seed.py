import unittest

from app import app, db
from models import Barangay, Municipality, Province
from seed.demo_data import seed_geography_data


class GeographySeedTestCase(unittest.TestCase):
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

    def test_seed_geography_data_creates_records(self):
        seed_geography_data()
        self.assertGreaterEqual(Province.query.count(), 1)
        self.assertGreaterEqual(Municipality.query.count(), 1)
        self.assertGreaterEqual(Barangay.query.count(), 1)


if __name__ == '__main__':
    unittest.main()
