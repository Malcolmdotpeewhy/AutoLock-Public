import sys
import unittest
import time
from unittest.mock import MagicMock, patch

# Mock dependencies






from services.automation import AutomationEngine

class TestPanicSwitch(unittest.TestCase):
    def setUp(self):
        self.mock_lcu = MagicMock()
        self.mock_assets = MagicMock()
        self.mock_config = MagicMock()
        self.mock_log = MagicMock()

        self.auto = AutomationEngine(
            self.mock_lcu,
            self.mock_assets,
            self.mock_config,
            log_func=self.mock_log
        )
        self.auto.pick_delay = 5

    def test_panic_stays_on_fail(self):
        """
        Verify that if lock fails in panic mode, it STAYS on current pick.
        """
        # Config
        def config_get(key, default=None):
            if key == "auto_lock_in": return True
            if key == "lock_in_delay": return 5
            return default
        self.mock_config.get.side_effect = config_get

        # Assets
        self.mock_assets.get_champ_id.side_effect = lambda name: 100 if name == "Yasuo" else 200

        # Action (Picking)
        action = {
            "id": 1,
            "actorCellId": 1,
            "championId": 100, # Currently hovering Yasuo
            "type": "pick",
            "completed": False,
            "isInProgress": True
        }

        # Session (Panic Mode < 5s)
        session = {
            "localPlayerCellId": 1,
            "timer": {"adjustedTimeLeftInPhase": 4000}, # 4s left
            "myTeam": [{"cellId": 1}],
            "bans": {},
            "actions": [[action]]
        }

        picks = ["Yasuo", "Yone"]

        # State
        self.auto.pick_hover_cid = 100 # We are hovering Yasuo
        self.auto.pick_hover_time = time.time() - 10 # Long enough

        # Mock LCU responses
        # Yasuo (100) lock attempt FAILS
        # Yone (200) hover attempt SUCCEEDS
        def lcu_side_effect(action_id, champ_id, complete=False):
            if champ_id == 100 and complete:
                # Fail the lock
                m = MagicMock()
                m.status_code = 500
                return m
            # Any other call succeeds
            m = MagicMock()
            m.status_code = 200
            return m

        self.mock_lcu.action_champ_select.side_effect = lcu_side_effect

        # Execute
        with patch.object(self.auto, '_is_available', return_value=True):
             self.auto._perform_pick_action(action, picks, session)

        # Verification
        # 1. Did we try to lock Yasuo?
        self.mock_lcu.action_champ_select.assert_any_call(1, 100, complete=True)

        # 2. Did we try to hover Yone? (We expect NOT to switch)
        # We expect NO call with champ_id=200
        calls = self.mock_lcu.action_champ_select.call_args_list
        yone_hover = [c for c in calls if c[0][1] == 200]

        if len(yone_hover) > 0:
            print("FAILED: Switched to Yone!")
        else:
            print("SUCCESS: Did not switch to Yone.")

        self.assertEqual(len(yone_hover), 0, "Should NOT have switched to Yone on panic failure")

if __name__ == '__main__':
    unittest.main()
