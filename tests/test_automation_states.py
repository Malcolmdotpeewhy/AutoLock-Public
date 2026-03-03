import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock external dependencies



# Mock external dependencies to prevent import errors and side effects






from services.automation import AutomationEngine
from services.api_handler import LCUClient
from services.asset_manager import AssetManager, ConfigManager

class TestAutoPollerStates(unittest.TestCase):
    def setUp(self):
        self.mock_lcu = MagicMock()
        self.mock_assets = MagicMock()
        self.mock_config = MagicMock()

        def config_get(key, default=None):
            if key == "experimental_profile": return {}
            return default

        self.mock_config.get.side_effect = config_get
        self.mock_lcu.is_connected = True

        self.auto = AutomationEngine(
            self.mock_lcu,
            self.mock_assets,
            self.mock_config,
            log_func=MagicMock()
        )

        # Prevent sleep delays
        self.patcher = patch('time.sleep', return_value=None)
        self.patcher.start()

        # State control for mock request
        self.current_phase = "None"
        self.mock_lcu.request.side_effect = self._mock_request

    def tearDown(self):
        self.patcher.stop()

    def _mock_request(self, method, endpoint, data=None, silent=False):
        if endpoint == "/lol-gameflow/v1/gameflow-phase":
            m = MagicMock()
            m.status_code = 200
            m.json.return_value = self.current_phase
            return m

        if endpoint == "/lol-lobby/v2/lobby":
            m = MagicMock()
            m.status_code = 200
            m.json.return_value = {"gameConfig": {"queueId": 420}}
            return m

        if endpoint == "/lol-champ-select/v1/session":
             m = MagicMock()
             m.status_code = 200
             m.json.return_value = {
                "myTeam": [],
                "actions": [],
                "timer": {"adjustedTimeLeftInPhase": 30000},
                "localPlayerCellId": 0,
                "benchChampions": []
             }
             return m

        # Default response
        return MagicMock(status_code=200, json=lambda: {})

    def test_state_transitions(self):
        """Test transitions: Idle -> Lobby -> ChampSelect"""

        # 1. Idle
        self.auto.running = True

    @patch('services.automation.time.sleep')
    def test_transitions_idle_lobby_cs(self, mock_sleep):
        """
        Test state transitions: Idle -> Lobby -> ChampSelect.
        Verifies that last_phase is updated and phase-specific handlers are invoked.
        """
        self.current_phase = "None"

        # We need to simulate the LCU responses
        def lcu_request_side_effect(method, endpoint, *args, **kwargs):
            if endpoint == "/lol-gameflow/v1/gameflow-phase":
                return MagicMock(status_code=200, json=lambda: self.current_phase)

            # Default response for other calls
            return MagicMock(status_code=200, json=lambda: {})

        self.mock_lcu.request.side_effect = lcu_request_side_effect

        # --- Step 1: Idle (None) ---
        self.current_phase = "None"
        self.auto._tick()
        self.assertEqual(self.auto.last_phase, "None")

        # 2. Lobby
        self.current_phase = "Lobby"
        self.auto._tick()
        self.assertEqual(self.auto.last_phase, "Lobby")

        # 3. ChampSelect
        self.current_phase = "ChampSelect"

        # Reset mocks to track fresh calls
        self.mock_lcu.request.reset_mock()
        self.mock_lcu.request.side_effect = self._mock_request

        self.auto._tick()

        self.assertEqual(self.auto.last_phase, "ChampSelect")

        # Verify calls
        # Verify _handle_champ_select was triggered
        calls = self.mock_lcu.request.call_args_list
        endpoints = [call[0][1] for call in calls]

        self.assertIn("/lol-gameflow/v1/gameflow-phase", endpoints)
        self.assertIn("/lol-champ-select/v1/session", endpoints)

if __name__ == '__main__':
    unittest.main()
