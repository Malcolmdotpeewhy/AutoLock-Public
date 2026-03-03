import sys
import unittest
import time
from unittest.mock import MagicMock, patch

# Mock dependencies before import






from services.automation import AutomationEngine

class TestPanicLock(unittest.TestCase):
    def setUp(self):
        self.mock_lcu = MagicMock()
        self.mock_assets = MagicMock()
        self.mock_config = MagicMock()
        self.mock_log = MagicMock()

        # Config setup needs to happen BEFORE init
        def config_get(key, default=None):
            if key == "experimental_profile": return {}
            if key == "lock_in_delay": return 5
            return default

        self.mock_config.get.side_effect = config_get

        self.auto = AutomationEngine(
            self.mock_lcu,
            self.mock_assets,
            self.mock_config,
            log_func=self.mock_log
        )

        # Patch time.sleep
        self.patcher = patch('time.sleep', return_value=None)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_panic_lock_trigger_when_auto_lock_off(self):
        """
        Verify that when auto_lock_in is False, the code SHOULD NOT return early
        if timer is < 5s, allowing the emergency panic lock logic to trigger.
        """
        # Specific config for this test
        def config_side_effect(key, default=None):
            if key == "experimental_profile": return {}
            if key == "auto_lock_in": return False
            if key == "lock_in_delay": return 5
            if key == "pick_MID_1": return "Yasuo"
            return default

        self.mock_config.get.side_effect = config_side_effect
        self.auto.pick_delay = 5

        self.mock_assets.get_champ_id.return_value = 100

        # Action Object (Picking)
        action = {
            "id": 10,
            "actorCellId": 1,
            "championId": 100, # Hovering Yasuo
            "type": "pick",
            "completed": False,
            "isInProgress": True
        }

        # Session State - PANIC MODE (<5s)
        session = {
            "localPlayerCellId": 1,
            "timer": {"adjustedTimeLeftInPhase": 4000},
            "myTeam": [{"cellId": 1, "championId": 100}],
            "bans": {"myTeamBans": [], "theirTeamBans": []},
            "actions": [[action]]
        }

        picks = ["Yasuo"]

        self.auto.pick_hover_cid = 100
        self.auto.pick_hover_time = time.time() - 10

        # Execute
        with patch.object(self.auto, '_is_available', return_value=True):
             self.auto._perform_pick_action(action, picks, session)

        # Assert: Lock (complete=True) SHOULD be called
        calls = self.mock_lcu.action_champ_select.call_args_list
        lock_calls = [c for c in calls if c[1].get('complete') is True]

        # This will fail before the fix
        self.assertTrue(len(lock_calls) > 0, "Panic lock should have triggered!")

if __name__ == '__main__':
    unittest.main()
