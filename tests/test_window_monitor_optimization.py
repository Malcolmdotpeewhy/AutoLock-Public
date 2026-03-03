
import time
import unittest
from unittest.mock import MagicMock, patch
import sys

# Define a dummy class to replace ctk.CTk
class MockCTk:
    def __init__(self, *args, **kwargs):
        pass
    def after(self, ms, func=None):
        pass
    def geometry(self, *args):
        pass
    def title(self, *args):
        pass
    def configure(self, *args, **kwargs):
        pass
    def iconphoto(self, *args, **kwargs):
        pass
    def attributes(self, *args, **kwargs):
        pass
    def state(self):
        return "normal"
    def grid_columnconfigure(self, *args, **kwargs):
        pass
    def grid_rowconfigure(self, *args, **kwargs):
        pass
    def tkraise(self, *args):
        pass
    def mainloop(self, *args):
        pass
    def winfo_exists(self):
        return True

# Mock internal modules locally or rely on imports working now
# We avoid global sys.modules modification to prevent test pollution

from core.main import LeagueAgentApp

class TestWindowMonitorPerformance(unittest.TestCase):

    def setUp(self):
        # Patch psutil in core.main
        self.psutil_patch = patch('core.main.psutil')
        self.mock_psutil = self.psutil_patch.start()

        self.mock_proc = MagicMock()
        self.mock_proc.info = {'name': 'League of Legends.exe'}

        # Default: No game found (empty list)
        self.mock_psutil.process_iter.return_value = []

    def tearDown(self):
        self.psutil_patch.stop()

    def test_is_game_running_optimization(self):
        """
        Verify the actual implementation of _is_game_running optimization.
        """
        # Create a generic mock to act as 'self'
        app_mock = MagicMock()

        # 1. Test Baseline (Disconnected) - Should call psutil
        app_mock.lcu.is_connected = False
        app_mock.current_phase = None
        app_mock._last_full_scan = 0

        # Call the unbound method from the class
        result = LeagueAgentApp._is_game_running(app_mock)

        self.assertFalse(result)
        # Verify psutil called
        self.assertEqual(self.mock_psutil.process_iter.call_count, 1)

        # 2. Test Optimized (Connected, Lobby) - Should NOT call psutil
        self.mock_psutil.process_iter.reset_mock()
        app_mock.lcu.is_connected = True
        app_mock.current_phase = "Lobby"

        result = LeagueAgentApp._is_game_running(app_mock)

        self.assertFalse(result)
        self.assertEqual(self.mock_psutil.process_iter.call_count, 0)

        # 3. Test Optimized (Connected, InProgress) - Should call psutil
        self.mock_psutil.process_iter.reset_mock()
        app_mock.lcu.is_connected = True
        app_mock.current_phase = "InProgress"
        app_mock._last_full_scan = 0
        # Mock finding the game
        self.mock_psutil.process_iter.return_value = [self.mock_proc]

        result = LeagueAgentApp._is_game_running(app_mock)

        self.assertTrue(result)
        self.assertEqual(self.mock_psutil.process_iter.call_count, 1)

if __name__ == '__main__':
    unittest.main()
