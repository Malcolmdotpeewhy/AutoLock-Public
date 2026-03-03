import unittest
from unittest.mock import MagicMock, patch
import sys
import math
import time

# Mock external dependencies






# Add root to sys.path
sys.path.append('.')

# Import after mocks
from services.automation import AutomationEngine

class TestAutoAcceptCountdown(unittest.TestCase):
    def setUp(self):
        self.mock_lcu = MagicMock()
        self.mock_assets = MagicMock()
        self.mock_config = MagicMock()

        # Configure config.get side effect
        def config_get(key, default=None):
            if key == "accept_delay": return 3.0
            if key == "auto_accept": return True
            if key == "experimental_profile": return {}
            return default

        self.mock_config.get.side_effect = config_get
        self.mock_lcu.is_connected = True

        self.mock_log = MagicMock()

        self.auto = AutomationEngine(
            self.mock_lcu,
            self.mock_assets,
            self.mock_config,
            log_func=self.mock_log
        )

        # Initialize internal state if not present (simulate __init__)
        if not hasattr(self.auto, '_last_countdown_log'):
             self.auto._last_countdown_log = None

    @patch("random.uniform", return_value=0.0)
    def test_countdown_logs_presence(self, mock_random):
        """Verify presence of logs (after fix)."""
        phase = "ReadyCheck"

        # T=0
        with patch('time.time', return_value=100.0):
            self.auto._handle_ready_check(phase) # Init timer

        # T=0.1 -> Remaining 2.9 -> Should Log "3s..."
        with patch('time.time', return_value=100.1):
            self.auto._handle_ready_check(phase)

        # T=1.1 -> Remaining 1.9 -> Should Log "2s..."
        with patch('time.time', return_value=101.1):
            self.auto._handle_ready_check(phase)

        # Verify calls
        logs = [str(call[0][0]) for call in self.mock_log.call_args_list]
        print(f"Presence Test Logs: {logs}")

        # We check if ANY log contains the string
        has_3 = any("Auto Accept: 3s..." in log for log in logs)
        has_2 = any("Auto Accept: 2s..." in log for log in logs)

        self.assertTrue(has_3, "Expected log 'Auto Accept: 3s...'")
        self.assertTrue(has_2, "Expected log 'Auto Accept: 2s...'")

    @patch("random.uniform")
    def test_delay_variance(self, mock_random):
        """Verify that delay includes random variance."""
        mock_random.return_value = 1.5
        phase = "ReadyCheck"

        # Reset state just in case
        self.auto.ready_check_start = None
        self.auto.ready_check_delay = None

        # Trigger initialization
        with patch('time.time', return_value=100.0):
            self.auto._handle_ready_check(phase)

        # Expected delay: 3.0 (config) + 1.5 (mock random) = 4.5
        # Note: Implementation logic: base_delay + variance
        mock_random.assert_called_with(0.0, 1.5)

        # Check internal state if possible, or verify behavior
        # Since ready_check_delay is stored on the instance now:
        self.assertEqual(self.auto.ready_check_delay, 4.5)

if __name__ == "__main__":
    unittest.main()
