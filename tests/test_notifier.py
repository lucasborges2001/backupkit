import unittest
from unittest.mock import MagicMock, patch
from core.notifier import (
    NotificationService, 
    TelegramNotifier, 
    SummaryRenderer, 
    NotificationMessage,
    NotificationResult
)
from core.result import RunReport, CheckResult

class TestNotifier(unittest.TestCase):
    def setUp(self):
        self.config = {
            'env': {
                'TELEGRAM_BOT_TOKEN': 'test_token',
                'TELEGRAM_CHAT_ID': 'test_chat_id'
            },
            'policy': {
                'project': {'name': 'test-project'},
                'resource': {'name': 'test-resource'},
                'notifications': {
                    'telegram': {
                        'enabled': True
                    }
                }
            }
        }

    def test_summary_renderer_returns_message(self):
        report = RunReport('test-project', 'test-resource', 'backup')
        report.add(CheckResult('check.1', 'ERROR', 'blocking', 'failure message'))
        
        message = SummaryRenderer.render(report)
        self.assertIsInstance(message, NotificationMessage)
        self.assertEqual(message.title, '[backupkit] BACKUP ERROR')
        self.assertIn('Proyecto: test-project', message.body)
        self.assertIn('Checks:', message.body)
        self.assertIn('- check.1: failure message', message.body)

    @patch('urllib.request.urlopen')
    def test_telegram_notifier_consumes_message(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"ok": true}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        notifier = TelegramNotifier('token', 'chat_id')
        message = NotificationMessage(title='Title', body='Body', status='ERROR')
        
        result = notifier.notify(message)
        self.assertEqual(result, 'telegram sent')

    def test_notification_service_policy_ok_skips(self):
        service = NotificationService(self.config)
        report = RunReport('test-project', 'test-resource', 'backup')
        
        results = service.notify(report)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].channel, 'system')
        self.assertEqual(results[0].status, 'SKIP')

    @patch('core.notifier.TelegramNotifier.notify')
    def test_notification_service_error_notifies(self, mock_notify):
        mock_notify.return_value = 'telegram sent'
        
        service = NotificationService(self.config)
        report = RunReport('test-project', 'test-resource', 'backup')
        report.add(CheckResult('check.1', 'ERROR', 'blocking', 'failure'))
        
        results = service.notify(report)
        # Expected: 1 result for telegram
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].channel, 'telegram')
        self.assertEqual(results[0].status, 'OK')

    def test_notification_service_disabled_evidence(self):
        self.config['policy']['notifications']['telegram']['enabled'] = False
        service = NotificationService(self.config)
        report = RunReport('test-project', 'test-resource', 'backup')
        report.add(CheckResult('check.1', 'ERROR', 'blocking', 'failure'))
        
        results = service.notify(report)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].channel, 'telegram')
        self.assertEqual(results[0].status, 'DISABLED')

    def test_notification_service_missing_config_evidence(self):
        self.config['env'] = {} # Missing tokens
        service = NotificationService(self.config)
        report = RunReport('test-project', 'test-resource', 'backup')
        report.add(CheckResult('check.1', 'ERROR', 'blocking', 'failure'))
        
        results = service.notify(report)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].channel, 'telegram')
        self.assertEqual(results[0].status, 'SKIP')
        self.assertIn('Missing credentials', results[0].note)

if __name__ == '__main__':
    unittest.main()
