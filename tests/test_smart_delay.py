import sys
import unittest
from unittest.mock import MagicMock, patch
import time
import random

# Mock external dependencies








from services.automation import AutomationEngine

class TestSmartDelay(unittest.TestCase):
    def setUp(self):
        # Create mocks for dependencies
        self.mock_customtkinter = MagicMock()
        self.mock_pil = MagicMock()
        self.mock_pil_image = MagicMock()
        self.mock_pil_imagetk = MagicMock()
        self.mock_psutil = MagicMock()
        self.mock_requests = MagicMock()
        self.mock_urllib3 = MagicMock()

        # Prepare sys.modules patch
        self.modules_patcher = patch.dict(sys.modules, {
            "customtkinter": self.mock_customtkinter,
            "PIL": self.mock_pil,
            "PIL.Image": self.mock_pil_image,
            "PIL.ImageTk": self.mock_pil_imagetk,
            "psutil": self.mock_psutil,
            "requests": self.mock_requests,
            "urllib3": self.mock_urllib3,
        })
        self.modules_patcher.start()
        self.addCleanup(self.modules_patcher.stop)

        # Force reload of AutomationEngine to pick up new mocks
        if "services.automation" in sys.modules:
            del sys.modules["services.automation"]

        import services.automation
        self.AutomationEngine = services.automation.AutomationEngine

        # Ensure services.automation is removed after test to prevent pollution
        def cleanup_module():
            if "services.automation" in sys.modules:
                del sys.modules["services.automation"]
        self.addCleanup(cleanup_module)

        self.mock_lcu = MagicMock()
        self.mock_assets = MagicMock()
        self.mock_config = MagicMock()
        self.mock_logger = MagicMock()

        self.automation = self.AutomationEngine(
            self.mock_lcu,
            self.mock_assets,
            self.mock_config,
            log_func=self.mock_logger
        )

    @patch("time.sleep")
    @patch("time.time")
    @patch("random.uniform", return_value=0.0) # Ensure deterministic delay
    def test_smart_delay_non_blocking(self, mock_random, mock_time, mock_sleep):
        """Verify that ReadyCheck handling does not block execution."""

        # Setup Config: Enabled, 5.0s delay
        def config_side_effect(key, default=None):
            if key == "auto_accept": return True
            if key == "accept_delay": return 5.0
            return default
        self.mock_config.get.side_effect = config_side_effect

        # Initial Time
        start_timestamp = 1000.0
        mock_time.return_value = start_timestamp

        # 1. First Tick: Enters ReadyCheck
        # Should initialize timer, but NOT accept yet
        self.automation._handle_ready_check("ReadyCheck")

        # Must NOT sleep (blocking)
        mock_sleep.assert_not_called()
        # Must NOT accept yet
        self.mock_lcu.request.assert_not_called()

        # 2. Second Tick: 2 seconds elapsed
        mock_time.return_value = start_timestamp + 2.0
        self.automation._handle_ready_check("ReadyCheck")

        mock_sleep.assert_not_called()
        self.mock_lcu.request.assert_not_called()

        # 3. Third Tick: 5.1 seconds elapsed (Threshold Met)
        mock_time.return_value = start_timestamp + 5.1
        self.automation._handle_ready_check("ReadyCheck")

        mock_sleep.assert_not_called()
        # Should accept exactly once
        self.mock_lcu.request.assert_called_once_with("POST", "/lol-matchmaking/v1/ready-check/accept")

        # 4. Fourth Tick: Still in ReadyCheck (e.g. waiting for others)
        # Should NOT accept again
        mock_time.return_value = start_timestamp + 6.0
        self.automation._handle_ready_check("ReadyCheck")

        self.mock_lcu.request.assert_called_once()

    def test_reset_on_phase_change(self):
        """Verify state resets when leaving ReadyCheck."""
        self.automation.ready_check_start = 12345
        self.automation.ready_check_accepted = True

        self.automation._handle_ready_check("Lobby")

        self.assertIsNone(self.automation.ready_check_start)
        self.assertFalse(self.automation.ready_check_accepted)

if __name__ == "__main__":
    unittest.main()
