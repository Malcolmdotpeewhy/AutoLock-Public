import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock external dependencies






from services.automation import AutomationEngine

class TestPollingOptimization(unittest.TestCase):
    def setUp(self):
        self.mock_lcu = MagicMock()
        self.mock_assets = MagicMock()
        self.mock_config = MagicMock()
        self.mock_config.get.side_effect = lambda k, d=None: d  # Return default

        self.mock_lcu.is_connected = True

        self.auto = AutomationEngine(
            self.mock_lcu,
            self.mock_assets,
            self.mock_config,
            log_func=MagicMock()
        )

    @patch('time.sleep')
    def test_polling_rates(self, mock_sleep):
        # Define test cases: Phase -> Expected Sleep
        test_cases = [
            ("None", 3.0), # Improved responsiveness
            ("Lobby", 2.0),
            ("Matchmaking", 2.0),
            ("ReadyCheck", 1.0),
            ("ChampSelect", 0.5),
            ("InProgress", 30.0),
            ("UnknownPhase", 3.0) # Improved responsiveness
        ]

        for phase, expected_sleep in test_cases:
            # Setup phase
            def mock_request(method, endpoint, *args, **kwargs):
                if endpoint == "/lol-gameflow/v1/gameflow-phase":
                    m = MagicMock()
                    m.status_code = 200
                    m.json.return_value = phase
                    return m
                return MagicMock(status_code=200, json=lambda: {})

            self.mock_lcu.request.side_effect = mock_request

            # Reset mock
            mock_sleep.reset_mock()

            # Run tick
            self.auto._tick()

            # Verify sleep called with expected value
            # Note: _tick might call sleep multiple times? No, usually once at the end.
            # But wait, logic might have short-circuits.
            # In _tick: time.sleep(sleep_time) is at the very end.

            mock_sleep.assert_called_with(expected_sleep)

if __name__ == '__main__':
    unittest.main()
