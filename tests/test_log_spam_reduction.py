import unittest
import unittest.mock
from services.api_handler import LCUClient

class TestLogSpamReduction(unittest.TestCase):
    def setUp(self):
        # Patch Logger to track calls
        self.logger_patcher = unittest.mock.patch('services.api_handler.Logger')
        self.mock_logger = self.logger_patcher.start()

        # Patch requests.Session to prevent actual network calls
        self.session_patcher = unittest.mock.patch('requests.Session')
        self.mock_session_cls = self.session_patcher.start()
        self.mock_session = self.mock_session_cls.return_value

        # Setup mock response
        mock_response = unittest.mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        self.mock_session.request.return_value = mock_response

        self.lcu = LCUClient()
        # Force connected state
        self.lcu.is_connected = True
        self.lcu.base_url = "https://127.0.0.1:12345"

    def tearDown(self):
        self.logger_patcher.stop()
        self.session_patcher.stop()

    def test_request_logs_by_default(self):
        """Verify that request logs debug messages by default."""
        self.lcu.request("GET", "/test-endpoint")

        # Should log REQ and RES
        # We look for calls to Logger.debug
        debug_calls = self.mock_logger.debug.call_args_list

        # Filter for our specific logs
        req_logs = [call for call in debug_calls if "REQ ->" in str(call)]
        res_logs = [call for call in debug_calls if "RES <-" in str(call)]

        self.assertTrue(len(req_logs) > 0, "Should log request start")
        self.assertTrue(len(res_logs) > 0, "Should log response end")

    def test_request_silent_suppresses_logs(self):
        """Verify that silent=True suppresses debug logs."""
        # This test is expected to PASS now that we implemented the feature

        try:
            self.lcu.request("GET", "/test-endpoint", silent=True)
        except TypeError:
            self.fail("LCUClient.request() does not accept 'silent' argument yet!")

        debug_calls = self.mock_logger.debug.call_args_list
        req_logs = [call for call in debug_calls if "REQ ->" in str(call)]
        res_logs = [call for call in debug_calls if "RES <-" in str(call)]

        self.assertEqual(len(req_logs), 0, "Should NOT log request start when silent=True")
        self.assertEqual(len(res_logs), 0, "Should NOT log response end when silent=True")

if __name__ == '__main__':
    unittest.main()
