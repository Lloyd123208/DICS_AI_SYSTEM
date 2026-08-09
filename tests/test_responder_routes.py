import importlib
import os
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image

os.environ.setdefault('SECRET_KEY', os.environ.get('SECRET_KEY') or 'development-secret')
# CRITICAL: this must be set before `app` is imported. Flask-SQLAlchemy binds
# and caches its engine the first time it's used; overriding
# SQLALCHEMY_DATABASE_URI on the config *after* import is not reliable and
# has previously caused the test suite to create/drop tables against the
# real instance/database.db file instead of an isolated database. Use a
# file-backed test DB so the schema is stable and reproducible before import.
TEST_DB_PATH = os.path.abspath(os.path.join('instance', 'test_responder_routes.db'))
os.environ.setdefault('DATABASE_URL', f'sqlite:///{TEST_DB_PATH}')

from flask import render_template_string

import app as app_module
from app import app, db
from models import User, CitizenReport, Incident, IncidentResponse, PostIncidentReport, Task, Resource, IncidentMessage
import scheduler


@app.route('/force-500')
def force_500():
    raise RuntimeError('intentional test failure')


class ResponderRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.drop_all()
            db.create_all()
            user = User(
                username='responder1',
                email='responder@example.com',
                password='secret',
                role='field_responder',
                agency='BFP',
                email_verified=True,
            )
            db.session.add(user)
            db.session.commit()

    def test_predict_hazard_fallback_contract_uses_insufficient_data(self):
        from ai import decision_support

        with patch('ai.decision_support.AI_PROVIDER', 'anthropic'), \
             patch.dict(os.environ, {'ANTHROPIC_API_KEY': ''}, clear=False):
            prediction = decision_support.predict_hazard(
                'flood',
                rainfall_mm=0,
                river_level_m=None,
                humidity_pct=0,
                population_density=0,
            )

        self.assertEqual(prediction.get('level'), 'INSUFFICIENT_DATA')
        self.assertTrue(prediction.get('degraded'))
        self.assertFalse(prediction.get('alert'))
        self.assertEqual(prediction.get('score'), 0.0)

    def test_field_responder_dashboard_requires_login(self):
        response = self.client.get('/responder-dashboard')
        self.assertEqual(response.status_code, 302)

    def test_coordinator_update_task_rejects_unowned_task(self):
        with self.app.app_context():
            coordinator = User(
                username='coordinator1',
                email='coord@example.com',
                password='secret',
                role='agency_coordinator',
                agency='BFP',
                email_verified=True,
            )
            db.session.add(coordinator)
            db.session.commit()

            incident = Incident(user_id=coordinator.id, hazard_type='earthquake', location='Test', message='Test', level='high', alert=True, status='ACTIVE')
            db.session.add(incident)
            db.session.commit()

            response = IncidentResponse(incident_id=incident.id, commander_id=coordinator.id, status='ACTIVE')
            db.session.add(response)
            db.session.commit()

            task = Task(
                incident_response_id=response.id,
                assigned_to_agency='DOH',
                assigned_by_id=coordinator.id,
                title='Unknown agency task',
                description='Should not be mutable by BFP coordinator',
                status='PENDING',
            )
            db.session.add(task)
            db.session.commit()
            task_id = task.id

        with self.client.session_transaction() as session:
            session['username'] = 'coordinator1'
            session['role'] = 'agency_coordinator'
            session['agency'] = 'BFP'

        response = self.client.post(f'/coordinator/tasks/{task_id}/update', data={'status': 'IN_PROGRESS'}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            refreshed = Task.query.get(task_id)
            self.assertEqual(refreshed.status, 'PENDING')

    def test_coordinator_allocate_resource_uses_coordinator_agency(self):
        with self.app.app_context():
            coordinator = User(
                username='coordinator2',
                email='coord2@example.com',
                password='secret',
                role='agency_coordinator',
                agency='BFP',
                email_verified=True,
            )
            db.session.add(coordinator)
            db.session.commit()

            incident = Incident(user_id=coordinator.id, hazard_type='earthquake', location='Test', message='Test', level='high', alert=True, status='ACTIVE')
            db.session.add(incident)
            db.session.commit()

            response = IncidentResponse(incident_id=incident.id, commander_id=coordinator.id, status='ACTIVE')
            db.session.add(response)
            db.session.commit()
            response_id = response.id

        with self.client.session_transaction() as session:
            session['username'] = 'coordinator2'
            session['role'] = 'agency_coordinator'
            session['agency'] = 'BFP'

        response = self.client.post('/coordinator/resources/allocate', data={
            'response_id': response_id,
            'agency': 'DOH',
            'resource_type': 'Vehicles',
            'quantity': 2,
            'status': 'AVAILABLE',
            'location': 'Base',
            'notes': 'Test',
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            resource = Resource.query.filter_by(incident_response_id=response_id).first()
            self.assertIsNotNone(resource)
            self.assertEqual(resource.agency, 'BFP')

    def test_coordinator_submit_report_requires_agency_owned_response_assets(self):
        with self.app.app_context():
            coordinator = User(
                username='coordinator3',
                email='coord3@example.com',
                password='secret',
                role='agency_coordinator',
                agency='BFP',
                email_verified=True,
            )
            db.session.add(coordinator)
            db.session.commit()

            incident = Incident(user_id=coordinator.id, hazard_type='earthquake', location='Test', message='Test', level='high', alert=True, status='ACTIVE')
            db.session.add(incident)
            db.session.commit()

            response = IncidentResponse(incident_id=incident.id, commander_id=coordinator.id, status='ACTIVE')
            db.session.add(response)
            db.session.commit()
            response_id = response.id

        with self.client.session_transaction() as session:
            session['username'] = 'coordinator3'
            session['role'] = 'agency_coordinator'
            session['agency'] = 'BFP'

        response = self.client.post('/coordinator/reports/submit', data={
            'response_id': response_id,
            'title': 'Test report',
            'content': 'This should be blocked',
            'report_type': 'UPDATE',
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            self.assertEqual(IncidentMessage.query.count(), 0)

    def test_create_default_admin_requires_password_env(self):
        with self.app.app_context():
            os.environ.pop('ADMIN_PASSWORD', None)
            with self.assertRaises(RuntimeError):
                app_module.create_default_admin()

    def test_create_default_admin_uses_default_credentials(self):
        with self.app.app_context():
            existing = User(username='admin', email='admin@dics-ai.local', password='legacy', role='user')
            db.session.add(existing)
            db.session.commit()

            os.environ['ADMIN_PASSWORD'] = 'test-admin-password'
            app_module.create_default_admin()
            admin = User.query.filter_by(username='admin').first()
            self.assertEqual(admin.role, 'admin')
            self.assertTrue(app_module.check_password_hash(admin.password, 'test-admin-password'))

    def test_register_requires_minimum_password_length(self):
        response = self.client.post('/register', data={
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'short',
            'full_name': 'New User',
            'contact_number': '09170000000',
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Password must be at least 8 characters.', response.data)

    def test_public_registration_assigns_citizen_role(self):
        response = self.client.post('/register', data={
            'username': 'citizenuser',
            'email': 'citizen@example.com',
            'password': 'strongpass123',
            'full_name': 'Citizen User',
            'contact_number': '09170000000',
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            user = User.query.filter_by(username='citizenuser').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.role, 'citizen')

    def test_field_responder_dashboard_renders_for_role(self):
        with self.client.session_transaction() as session:
            session['username'] = 'responder1'
            session['role'] = 'field_responder'
            session['agency'] = 'BFP'

        response = self.client.get('/responder-dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Field Responder', response.data)

    def test_secret_key_uses_environment_and_initializes_db_on_request(self):
        original_secret = os.environ.get('SECRET_KEY')
        os.environ['SECRET_KEY'] = 'env-secret-test'

        try:
            import app as app_module
            app_module = importlib.reload(app_module)
            client = app_module.app.test_client()

            response = client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(app_module.app.config['SECRET_KEY'], 'env-secret-test')
            self.assertTrue(app_module._init_attempted)
        finally:
            if original_secret is None:
                os.environ.pop('SECRET_KEY', None)
            else:
                os.environ['SECRET_KEY'] = original_secret

    def test_secret_key_generates_random_value_when_unset(self):
        # SECRET_KEY must never fall back to a fixed, known string checked into
        # source control (session forgery risk). When unset, the app should
        # generate a random per-process key instead.
        original_secret = os.environ.get('SECRET_KEY')
        os.environ.pop('SECRET_KEY', None)

        try:
            import app as app_module
            with self.assertWarns(RuntimeWarning):
                app_module = importlib.reload(app_module)
            secret_key = app_module.app.config['SECRET_KEY']
            self.assertTrue(secret_key)
            self.assertNotEqual(secret_key, 'dev-secret-key-change-me')
            self.assertGreaterEqual(len(secret_key), 32)
        finally:
            if original_secret is None:
                os.environ.pop('SECRET_KEY', None)
            else:
                os.environ['SECRET_KEY'] = original_secret
            importlib.reload(app_module)

    def test_citizen_report_creates_record_with_photo_and_anonymous_flag(self):
        with self.client.session_transaction() as session:
            session['username'] = 'responder1'
            session['role'] = 'user'

        image_stream = BytesIO()
        Image.new('RGB', (1, 1), color='white').save(image_stream, format='JPEG')
        image_stream.seek(0)

        response = self.client.post('/citizen-report', data={
            'hazard_type': 'flood',
            'severity': 'high',
            'location': 'Barangay Test',
            'description': 'Water rising',
            'affected_people': '5',
            'injuries': '0',
            'contact': '09171234567',
            'gps_lat': '14.1234',
            'gps_lng': '121.5678',
            'anonymous': 'on',
            'photo': (image_stream, 'photo.jpg'),
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            report = CitizenReport.query.filter_by(location='Barangay Test').first()
            self.assertIsNotNone(report)
            self.assertTrue(report.anonymous)
            self.assertEqual(report.gps_latitude, 14.1234)
            self.assertEqual(report.gps_longitude, 121.5678)
            self.assertIsNotNone(report.photo_filename)
            upload_response = self.client.get(f'/uploads/{report.photo_filename}')
            self.assertEqual(upload_response.status_code, 200)
            self.assertGreater(len(upload_response.data), 0)
            self.assertTrue(upload_response.data.startswith(b'\xff\xd8'))

    def test_citizen_report_rejects_invalid_photo_upload(self):
        with self.client.session_transaction() as session:
            session['username'] = 'responder1'
            session['role'] = 'user'

        response = self.client.post('/citizen-report', data={
            'hazard_type': 'flood',
            'severity': 'high',
            'location': 'Barangay Test',
            'description': 'Water rising',
            'affected_people': '5',
            'injuries': '0',
            'contact': '09171234567',
            'gps_lat': '14.1234',
            'gps_lng': '121.5678',
            'photo': (BytesIO(b'not-an-image'), 'evil.exe'),
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Photo upload was invalid.', response.data)
        with self.app.app_context():
            self.assertEqual(CitizenReport.query.count(), 0)
            self.assertEqual(Incident.query.count(), 0)

    def test_citizen_report_rejects_oversized_photo_upload(self):
        with self.client.session_transaction() as session:
            session['username'] = 'responder1'
            session['role'] = 'user'

        self.app.config['MAX_UPLOAD_SIZE_BYTES'] = 64

        image_stream = BytesIO()
        Image.new('RGB', (4, 4), color='white').save(image_stream, format='JPEG')
        image_stream.seek(0)

        response = self.client.post('/citizen-report', data={
            'hazard_type': 'flood',
            'severity': 'high',
            'location': 'Barangay Test',
            'description': 'Water rising',
            'affected_people': '5',
            'injuries': '0',
            'contact': '09171234567',
            'gps_lat': '14.1234',
            'gps_lng': '121.5678',
            'photo': (image_stream, 'photo.jpg', 'image/jpeg'),
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Photo upload was invalid.', response.data)
        with self.app.app_context():
            self.assertEqual(CitizenReport.query.count(), 0)
            self.assertEqual(Incident.query.count(), 0)

    def test_citizen_report_rejects_photo_with_unsupported_mimetype(self):
        with self.client.session_transaction() as session:
            session['username'] = 'responder1'
            session['role'] = 'user'

        image_stream = BytesIO()
        Image.new('RGB', (1, 1), color='white').save(image_stream, format='JPEG')
        image_stream.seek(0)

        response = self.client.post('/citizen-report', data={
            'hazard_type': 'flood',
            'severity': 'high',
            'location': 'Barangay Test',
            'description': 'Water rising',
            'affected_people': '5',
            'injuries': '0',
            'contact': '09171234567',
            'gps_lat': '14.1234',
            'gps_lng': '121.5678',
            'photo': (image_stream, 'photo.jpg', 'application/octet-stream'),
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Photo upload was invalid.', response.data)
        with self.app.app_context():
            self.assertEqual(CitizenReport.query.count(), 0)
            self.assertEqual(Incident.query.count(), 0)

    def test_map_pins_endpoint_returns_active_incidents_with_coordinates(self):
        with self.app.app_context():
            citizen_report = CitizenReport(
                user_id=1,
                hazard_type='flood',
                severity='high',
                location='Barangay Test',
                description='Water rising',
                gps_latitude=14.1234,
                gps_longitude=121.5678,
                anonymous=False,
            )
            db.session.add(citizen_report)
            db.session.flush()

            incident = Incident(
                user_id=1,
                hazard_type='flood',
                location='Barangay Test',
                message='Water rising',
                level='high',
                alert=True,
                status='ACTIVE',
                reported_by='citizen',
                citizen_report_id=citizen_report.id,
            )
            db.session.add(incident)
            db.session.commit()

        with self.client.session_transaction() as session:
            session['username'] = 'responder1'
            session['role'] = 'citizen'

        response = self.client.get('/api/map-pins')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(isinstance(data, list))
        self.assertGreaterEqual(len(data), 1)
        self.assertEqual(data[0]['hazard_type'], 'flood')
        self.assertEqual(data[0]['lat'], 14.1234)
        self.assertEqual(data[0]['lng'], 121.5678)

    def test_custom_error_handlers_render_friendly_pages(self):
        response = self.client.get('/does-not-exist')
        self.assertEqual(response.status_code, 404)
        self.assertIn(b'Page Not Found', response.data)
        self.assertIn(b'The page you requested could not be found.', response.data)

        response = self.client.get('/force-500')
        self.assertEqual(response.status_code, 500)
        self.assertIn(b'Something went wrong on our side.', response.data)

    def test_template_rendering_without_request_context_is_safe(self):
        with self.app.app_context():
            rendered = render_template_string('Status: {{ alert_count }}', alert_count=0)

        self.assertEqual(rendered, 'Status: 0')

    def test_monitor_hazards_creates_incident_for_high_risk_prediction(self):
        weather_data = {
            'city': 'Lipa',
            'temperature': 31,
            'humidity': 85,
            'pressure': 1008,
            'wind_speed': 8,
            'rainfall': 20,
            'weather': 'heavy rain',
            'fetched_at': 'now',
        }
        prediction = {
            'type': 'flood',
            'score': 80.0,
            'level': 'Severe',
            'message': 'Severe hazard risk.',
            'alert': True,
        }

        with patch.object(scheduler, 'get_all_weather_data', return_value={'Lipa': weather_data}), \
             patch.object(scheduler, 'predict_hazard', return_value=prediction):
            with self.app.app_context():
                scheduler.monitor_hazards()

        with self.app.app_context():
            incident = Incident.query.filter_by(hazard_type='flood').order_by(Incident.created_at.desc()).first()
            self.assertIsNotNone(incident)
            self.assertTrue(incident.alert)
            self.assertEqual(incident.score, 80.0)
            self.assertEqual(incident.location, 'Lipa')

    def test_monitor_hazards_creates_incidents_for_multiple_hazard_types(self):
        weather_data = {
            'city': 'Lipa',
            'temperature': 31,
            'humidity': 85,
            'pressure': 1008,
            'wind_speed': 8,
            'rainfall': 20,
            'weather': 'heavy rain',
            'fetched_at': 'now',
        }

        def fake_predict_hazard(hazard_type, **kwargs):
            return {
                'type': hazard_type,
                'score': 80.0,
                'level': 'Severe',
                'message': f'Severe {hazard_type} risk.',
                'alert': True,
            }

        with patch.object(scheduler, 'get_all_weather_data', return_value={'Lipa': weather_data}), \
             patch.object(scheduler, 'predict_hazard', side_effect=fake_predict_hazard):
            with self.app.app_context():
                scheduler.monitor_hazards()

        with self.app.app_context():
            incidents = Incident.query.filter(Incident.hazard_type.in_(['flood', 'landslide'])).all()
            self.assertEqual(len(incidents), 2)
            self.assertEqual({incident.hazard_type for incident in incidents}, {'flood', 'landslide'})

    def test_api_realtime_data_returns_all_calabarzon_cities(self):
        weather_data = {
            'city': 'Cavite',
            'temperature': 30,
            'humidity': 70,
            'pressure': 1009,
            'wind_speed': 5,
            'rainfall': 2,
            'weather': 'sunny',
            'fetched_at': 'now',
        }

        with patch.object(app_module, 'get_all_weather_data', return_value={'Cavite': weather_data}), \
             patch.object(app_module, 'get_earthquake_data', return_value=[]):
            with self.client.session_transaction() as session:
                session['username'] = 'responder1'
                session['role'] = 'field_responder'

            response = self.client.get('/api/realtime-data')
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn('weather', data)
            self.assertIn('earthquakes', data)
            self.assertEqual(data['weather']['Cavite']['city'], 'Cavite')

    def test_post_incident_evaluation_saves_report_for_closed_response(self):
        with self.app.app_context():
            commander = User(
                username='commander1',
                email='commander@example.com',
                password='secret',
                role='incident_commander',
                agency='BFP',
                email_verified=True,
            )
            db.session.add(commander)
            db.session.commit()

            incident = Incident(
                user_id=commander.id,
                hazard_type='flood',
                location='Lipa',
                message='Flooding reported',
                level='HIGH',
                alert=True,
                status='CLOSED',
                reported_by='system',
            )
            db.session.add(incident)
            db.session.commit()

            response = IncidentResponse(
                incident_id=incident.id,
                commander_id=commander.id,
                status='CLOSED',
                situation_summary='Resolved',
            )
            db.session.add(response)
            db.session.commit()
            db.session.refresh(response)

        with self.client.session_transaction() as session:
            session['username'] = 'commander1'
            session['role'] = 'incident_commander'
            session['agency'] = 'BFP'

        response_result = self.client.post(f'/incident-response/{response.id}/post-incident-evaluation', data={
            'lessons_learned': 'Improved shelter coordination',
            'response_rating': '5',
            'recommendations': 'Add more evacuation buses',
        }, follow_redirects=True)

        self.assertEqual(response_result.status_code, 200)
        with self.app.app_context():
            report = PostIncidentReport.query.filter_by(incident_response_id=response.id).first()
            self.assertIsNotNone(report)
            self.assertEqual(report.lessons_learned, 'Improved shelter coordination')
            self.assertEqual(report.response_rating, 5)
            self.assertEqual(report.recommendations, 'Add more evacuation buses')

    def test_coordinator_comms_page_renders_for_agency_coordinator(self):
        with self.client.session_transaction() as session:
            session['username'] = 'coordinator1'
            session['role'] = 'agency_coordinator'
            session['agency'] = 'DILG'

        with self.app.app_context():
            coordinator = User(
                username='coordinator1',
                email='coordinator@example.com',
                password='secret',
                role='agency_coordinator',
                agency='DILG',
                email_verified=True,
            )
            db.session.add(coordinator)
            db.session.commit()

            incident = Incident(
                user_id=coordinator.id,
                hazard_type='storm',
                location='Region Test',
                message='Storm forming',
                level='moderate',
                alert=False,
                status='ACTIVE',
                reported_by='system',
            )
            db.session.add(incident)
            db.session.commit()

            from models import IncidentResponse
            response = IncidentResponse(
                incident_id=incident.id,
                commander_id=coordinator.id,
                status='ACTIVE',
                situation_summary='Summary',
            )
            db.session.add(response)
            db.session.commit()

        response = self.client.get('/coordinator/comms')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Communication Center', response.data)

    def test_coordinator_submit_report_creates_message(self):
        with self.client.session_transaction() as session:
            session['username'] = 'coordinator1'
            session['role'] = 'agency_coordinator'
            session['agency'] = 'DILG'

        with self.app.app_context():
            coordinator = User(
                username='coordinator1',
                email='coordinator@example.com',
                password='secret',
                role='agency_coordinator',
                agency='DILG',
                email_verified=True,
            )
            db.session.add(coordinator)
            db.session.commit()
            coordinator_id = coordinator.id

            incident = Incident(
                user_id=coordinator_id,
                hazard_type='storm',
                location='Region Test',
                message='Storm forming',
                level='moderate',
                alert=False,
                status='ACTIVE',
                reported_by='system',
            )
            db.session.add(incident)
            db.session.commit()

            from models import IncidentResponse
            incident_response = IncidentResponse(
                incident_id=incident.id,
                commander_id=coordinator_id,
                status='ACTIVE',
                situation_summary='Summary',
            )
            db.session.add(incident_response)
            db.session.commit()
            incident_response_id = incident_response.id

            task = Task(
                incident_response_id=incident_response_id,
                assigned_to_agency='DILG',
                assigned_by_id=coordinator_id,
                title='Agency-owned task',
                description='Supports coordinator report submission',
                status='PENDING',
                priority='MEDIUM',
            )
            db.session.add(task)
            db.session.commit()

        response = self.client.post('/coordinator/reports/submit', data={
            'response_id': incident_response_id,
            'title': 'Test Broadcast',
            'content': 'This is a test broadcast message.',
            'report_type': 'UPDATE',
            'affected_areas': 'Region Test',
            'evacuated': '0',
            'casualties': '0',
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            from models import IncidentMessage
            message = IncidentMessage.query.filter_by(title='Test Broadcast').first()
            self.assertIsNotNone(message)
            self.assertEqual(message.content, 'This is a test broadcast message.')
            self.assertEqual(message.reporter_id, coordinator_id)
            self.assertEqual(message.incident_response_id, incident_response_id)
            self.assertEqual(message.source, 'coordinator')


if __name__ == '__main__':
    unittest.main()
