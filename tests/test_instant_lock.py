import unittest
from unittest.mock import MagicMock, patch
import sys
import time

# Mock dependencies






from services.automation import AutomationEngine

class TestInstantLock(unittest.TestCase):
    def setUp(self):
        self.mock_lcu = MagicMock()
        self.mock_assets = MagicMock()
        self.mock_config = MagicMock()

        # Configure Config to return delay=0
        self.config_data = {
            "lock_in_delay": 0.0,
            "auto_lock_in": True,
            "experimental_profile": {}
        }

        def config_get(key, default=None):
            return self.config_data.get(key, default)

        self.mock_config.get.side_effect = config_get

        self.auto = AutomationEngine(
            self.mock_lcu,
            self.mock_assets,
            self.mock_config,
            log_func=MagicMock()
        )
        # Ensure pick_delay is synced (it is set in __init__)
        self.auto.pick_delay = 0.0

    def test_instant_lock_first_tick(self):
        """
        Verify that if lock_in_delay is 0, the automation locks in immediately
        on the first tick, without a hover-only step.
        """
        # Setup Action (Picking)
        action_id = 123
        champ_id = 99
        champ_name = "Lux"

        action = {
            "id": action_id,
            "actorCellId": 1,
            "championId": 0, # Not hovering anything yet
            "type": "pick",
            "completed": False,
            "isInProgress": True # It is our turn
        }

        picks = [champ_name]

        # Mock Asset lookup
        self.mock_assets.get_champ_id.return_value = champ_id

        # Mock LCU Response for Instant Lock
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        self.mock_lcu.action_champ_select.return_value = mock_resp

        # Session (needed for _is_available)
        session = {
            "localPlayerCellId": 1,
            "myTeam": [{"cellId": 1, "championId": 0}],
            "bans": {},
            "timer": {"adjustedTimeLeftInPhase": 30000} # Plenty of time
        }

        # Execute
        self.auto._perform_pick_action(action, picks, session)

        # Assert
        # We expect action_champ_select to be called with complete=True
        # Current behavior: It calls complete=False (hover) and returns.

        calls = self.mock_lcu.action_champ_select.call_args_list
        self.assertTrue(len(calls) > 0, "No action taken!")

        # Check first call arguments
        # args: (action_id, champion_id)
        # kwargs: complete=...

        first_call = calls[0]
        args, kwargs = first_call

        self.assertEqual(args[0], action_id)
        self.assertEqual(args[1], champ_id)

        # EXPECTED (Desired): complete=True
        # ACTUAL (Current): complete=False
        is_complete = kwargs.get("complete", False)

        if is_complete:
            print("SUCCESS: Instant lock occurred on first tick.")
        else:
            print("FAILURE: First tick was a Hover (complete=False).")

        self.assertTrue(is_complete, "Should have locked instantly on first tick")

if __name__ == "__main__":
    unittest.main()
