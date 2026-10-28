"""Regression: auth URLs and clinical identifiers must not enter access logs."""
import importlib.util
from pathlib import Path
import unittest

from gunicorn.glogging import Logger


class AccessLogPrivacyTests(unittest.TestCase):
    def test_real_gunicorn_atoms_do_not_leak_request_values(self):
        spec = importlib.util.spec_from_file_location('web_config', 'gunicorn.conf.py')
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        atoms = Logger.atoms(object.__new__(Logger), type('Response', (), {'status': '200 OK', 'sent': 32, 'headers': []})(),
            [('Referer', 'patient-secret'), ('User-Agent', 'patient-secret')],
            {'REMOTE_ADDR': 'patient-secret', 'REQUEST_METHOD': 'GET',
             'RAW_URI': '/oauth?code=patient-secret', 'PATH_INFO': '/clients/patient-secret',
             'QUERY_STRING': 'token=patient-secret', 'SERVER_PROTOCOL': 'HTTP/1.1'},
            __import__('datetime').timedelta(milliseconds=20))
        rendered = config.access_log_format % atoms
        self.assertNotIn('patient-secret', rendered)
        self.assertIn('status=200', rendered)
        self.assertIn('method=GET', rendered)

    def test_nginx_format_uses_only_structural_variables(self):
        import re
        config = Path('ops/nginx/privacy-logging.conf').read_text()
        directives = '\n'.join(line for line in config.splitlines() if not line.startswith('#'))
        self.assertEqual(set(re.findall(r'\$\w+', directives)),
            {'$time_iso8601', '$request_method', '$status', '$body_bytes_sent', '$request_time'})


if __name__ == '__main__':
    unittest.main()
