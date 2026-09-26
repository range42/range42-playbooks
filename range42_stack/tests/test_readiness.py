import importlib
from pathlib import Path
import unittest
from unittest.mock import patch
from range42_stack.plan import build_plan
from test_plan import spec


class ReadinessTests(unittest.TestCase):
    def module(self):
        self.assertTrue((Path(__file__).parents[1] / 'readiness.py').is_file(), 'Readiness checks are missing')
        return importlib.import_module('range42_stack.readiness')

    def test_dns_must_point_every_enabled_service_at_the_gateway(self):
        module=self.module(); plan=build_plan(dict(spec(),profile='core'))
        with patch.object(module.socket, 'getaddrinfo', return_value=[(2,1,6,'',('10.81.0.10',443))]):
            module.validate_dns(plan, ['10.81.0.10'])
        with patch.object(module.socket, 'getaddrinfo', return_value=[(2,1,6,'',('10.82.0.10',443))]):
            with self.assertRaisesRegex(ValueError, 'DNS'): module.validate_dns(plan, ['10.81.0.10'])

    def test_http_readiness_is_authenticated_and_reports_each_failure(self):
        module=self.module(); plan=build_plan(dict(spec(),profile='core')); calls=[]
        def probe(url, token, ca):
            calls.append((url,token))
            if 'reporting.' in url: raise OSError('unreachable')
            return {'ready':True}
        result=module.check_endpoints(plan,'fixture-token',None,probe=probe)
        self.assertFalse(result['ready'])
        self.assertEqual(result['services']['reporting']['ready'],False)
        self.assertIn(('https://api.alpha.example.test/v1/health/ready','fixture-token'),calls)
        self.assertNotIn('fixture-token',str(result))

    def test_readiness_false_from_backend_is_not_a_success(self):
        module=self.module(); plan=build_plan(dict(spec(),profile='core'))
        result=module.check_endpoints(plan,'fixture-token',None,probe=lambda *a:{'ready':False})
        self.assertFalse(result['services']['backend']['ready'])
