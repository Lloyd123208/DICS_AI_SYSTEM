import os
import unittest

os.environ['SECRET_KEY'] = 'test-secret'

from tests.test_responder_routes import ResponderRoutesTestCase

suite = unittest.defaultTestLoader.loadTestsFromTestCase(ResponderRoutesTestCase)
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
