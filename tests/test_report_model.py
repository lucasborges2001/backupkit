import json
import tempfile
import unittest
from pathlib import Path

from core.cli import write_report
from core.result import CheckResult, RunReport, ArtifactMetadata


class ReportModelTests(unittest.TestCase):
    def test_report_exposes_only_strict_pipeline_shape(self):
        report = RunReport(project='demo', resource='mysql-main', resource_type='mysql', command='precheck')
        report.add(CheckResult('core.config.required', 'OK', 'blocking', 'Required policy fields present'))
        report.add_notification('telegram', 'OK', 'telegram sent')
        payload = report.as_dict()

        self.assertEqual(
            set(payload),
            {
                'report_version',
                'metadata',
                'final_status',
                'phases',
                'artifacts',
                'validators',
                'notifications',
                'housekeeping',
                'final_summary',
            },
        )
        self.assertEqual(payload['report_version'], 2)
        self.assertEqual(payload['metadata']['project'], 'demo')
        self.assertEqual(payload['metadata']['resource'], 'mysql-main')
        self.assertEqual(payload['metadata']['resource_type'], 'mysql')
        self.assertEqual(payload['metadata']['command'], 'precheck')
        self.assertIn('started_at', payload['metadata'])
        self.assertIn('finished_at', payload['metadata'])
        self.assertIn('duration_ms', payload['metadata'])
        self.assertEqual(payload['final_status'], 'OK')

        self.assertEqual(len(payload['phases']), 1)
        phase = payload['phases'][0]
        self.assertEqual(phase['id'], 'precheck')
        self.assertEqual(phase['status'], 'OK')
        self.assertEqual(phase['summary']['counts']['total'], 1)
        self.assertEqual(
            set(phase['evidence']),
            {'checks', 'artifacts', 'restore_test', 'validators', 'notifications', 'housekeeping'},
        )
        self.assertEqual(phase['evidence']['checks'][0]['id'], 'core.config.required')
        self.assertEqual(phase['evidence']['artifacts'], [])
        self.assertEqual(phase['evidence']['restore_test'], {})
        self.assertEqual(phase['evidence']['validators'], [])
        self.assertEqual(phase['evidence']['notifications'][0]['channel'], 'telegram')
        self.assertEqual(phase['evidence']['housekeeping'], {})
        self.assertEqual(payload['notifications'][0]['channel'], 'telegram')
        self.assertEqual(payload['housekeeping'], {})
        self.assertIn('final_summary', payload)

        legacy_fields = {
            'project',
            'resource',
            'resource_type',
            'command',
            'phase',
            'started_at',
            'finished_at',
            'duration_sec',
            'status',
            'summary',
            'checks',
            'artifact',
            'restore_test',
        }
        self.assertTrue(legacy_fields.isdisjoint(payload))

    def test_report_surfaces_artifacts_and_validators_in_pipeline_arrays(self):
        report = RunReport(project='demo', resource='mysql-main', resource_type='mysql', command='restore-test')
        report.add(CheckResult('adapter.mysql.restore.import', 'OK', 'blocking', 'restore ok'))
        report.set_artifact(ArtifactMetadata.from_values(
            path='/tmp/demo.sql.gz',
            size_bytes=123,
            sha256='abc',
            timestamp='2026-03-31T00:00:00+00:00',
            engine='mysql',
            resource='mysql-main',
            project='demo',
            duration_sec=1.2,
            status='OK',
            metadata_path='/tmp/demo.sql.gz.meta.json',
        ))
        report.set_restore_test({
            'database': 'bkrt_demo',
            'cleanup_attempted': True,
            'cleanup_succeeded': True,
            'validator_results': [
                {
                    'id': 'users_non_zero',
                    'status': 'OK',
                    'severity': 'error',
                    'message': 'ok',
                }
            ],
        })

        payload = report.as_dict()

        self.assertEqual(len(payload['artifacts']), 1)
        self.assertEqual(payload['artifacts'][0]['engine'], 'mysql')
        self.assertEqual(len(payload['validators']), 1)
        self.assertEqual(payload['validators'][0]['id'], 'users_non_zero')
        evidence = payload['phases'][0]['evidence']
        self.assertEqual(evidence['restore_test']['database'], 'bkrt_demo')
        self.assertEqual(evidence['validators'][0]['id'], 'users_non_zero')
        self.assertEqual(evidence['artifacts'][0]['engine'], 'mysql')

    def test_write_report_writes_strict_precheck_report_json(self):
        report = RunReport(project='demo', resource='mysql-main', resource_type='mysql', command='precheck')
        report.add(CheckResult('core.output_dir.writable', 'OK', 'blocking', 'Output dir writable'))

        with tempfile.TemporaryDirectory() as tmp:
            report_path = write_report(report, tmp)
            self.assertEqual(report_path.name, 'precheck-report.json')
            payload = json.loads(Path(report_path).read_text(encoding='utf-8'))
            self.assertEqual(payload['report_version'], 2)
            self.assertEqual(payload['final_status'], 'OK')
            self.assertEqual(payload['metadata']['command'], 'precheck')
            self.assertEqual(payload['phases'][0]['status'], 'OK')
            self.assertEqual(payload['phases'][0]['summary']['counts']['total'], 1)
            self.assertNotIn('status', payload)
            self.assertNotIn('checks', payload)


if __name__ == '__main__':
    unittest.main()
