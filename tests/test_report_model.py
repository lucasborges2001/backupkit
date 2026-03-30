import json
import tempfile
import unittest
from pathlib import Path

from core.cli import write_report
from core.result import CheckResult, RunReport


class ReportModelTests(unittest.TestCase):
    def test_report_keeps_precheck_fields_and_adds_growth_metadata(self):
        report = RunReport(project='demo', resource='mysql-main', resource_type='mysql', command='precheck')
        report.add(CheckResult('core.config.required', 'OK', 'blocking', 'Required policy fields present'))
        payload = report.as_dict()

        self.assertEqual(payload['project'], 'demo')
        self.assertEqual(payload['resource'], 'mysql-main')
        self.assertEqual(payload['resource_type'], 'mysql')
        self.assertEqual(payload['command'], 'precheck')
        self.assertEqual(payload['phase'], 'precheck')
        self.assertEqual(payload['status'], 'OK')
        self.assertEqual(payload['summary']['OK'], 1)
        self.assertEqual(payload['summary']['total'], 1)
        self.assertIn('started_at', payload)
        self.assertIn('finished_at', payload)
        self.assertEqual(payload['checks'][0]['id'], 'core.config.required')

    def test_write_report_still_writes_precheck_report_json(self):
        report = RunReport(project='demo', resource='mysql-main', resource_type='mysql', command='precheck')
        report.add(CheckResult('core.output_dir.writable', 'OK', 'blocking', 'Output dir writable'))

        with tempfile.TemporaryDirectory() as tmp:
            report_path = write_report(report, tmp)
            self.assertEqual(report_path.name, 'precheck-report.json')
            payload = json.loads(Path(report_path).read_text(encoding='utf-8'))
            self.assertEqual(payload['status'], 'OK')
            self.assertEqual(payload['summary']['total'], 1)


if __name__ == '__main__':
    unittest.main()
