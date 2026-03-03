import unittest
from unittest.mock import MagicMock, patch
import sys
import importlib

class TestAutoLockSpam(unittest.TestCase):
    def setUp(self):
        # Patch modules safely using patch.dict
        self.modules_patcher = patch.dict(sys.modules, {
            "customtkinter": MagicMock(),
            "requests": MagicMock(),
            "urllib3": MagicMock(),
            "PIL": MagicMock(),
            "psutil": MagicMock()
        })
        self.modules_patcher.start()

        # Re-import services.automation to ensure it uses patched modules
        # We need to invalidate cache for 'services' and 'services.automation'
        if 'services.automation' in sys.modules:
            del sys.modules['services.automation']
        if 'services' in sys.modules:
             # We can't easily delete a package if other modules use it,
             # but we can reload the specific module.
             pass

        # Import inside setup to use patched modules
        import services.automation
        importlib.reload(services.automation)
        self.AutomationEngine = services.automation.AutomationEngine

        self.lcu = MagicMock()
        self.assets = MagicMock()
        self.config = MagicMock()
        self.log_mock = MagicMock()

        # Configure config BEFORE init
        def config_init(key, default=None):
            if key == "lock_in_delay": return 5
            if key == "experimental_profile": return {}
            if key == "auto_lock_in": return False
            return default
        self.config.get.side_effect = config_init

        self.engine = self.AutomationEngine(
            self.lcu, self.assets, self.config, log_func=self.log_mock
        )

        self.assets.get_champ_id.return_value = 101
        self.engine._is_available = MagicMock(return_value=True)

    def tearDown(self):
        self.modules_patcher.stop()

    def test_auto_lock_off_spam(self):
        """Verify that disabling auto-lock prevents 'Failed to Lock' spam."""
        # Setup: Action (Picking phase, our turn)
        action = {
            "id": 1, "actorCellId": 0, "championId": 0,
            "completed": False, "type": "pick", "isInProgress": True
        }
        session = {"localPlayerCellId": 0, "timer": {"adjustedTimeLeftInPhase": 20000}}
        picks = ["TestChamp"]

        # Assume hovering already started
        self.engine.pick_hover_cid = 101
        import time
        self.engine.pick_hover_time = time.time() - 6

        # Run
        self.engine._perform_pick_action(action, picks, session)

        # Assert
        found_failure = False
        for call in self.log_mock.call_args_list:
            if "Failed to Lock" in call[0][0]:
                found_failure = True

        self.assertFalse(found_failure, "Should NOT log 'Failed to Lock' when auto-lock is disabled")

    def test_auto_lock_off_hover_msg(self):
        """Verify that we log 'Auto-Lock Disabled' when first hovering."""
        # Setup: New hover
        self.engine.pick_hover_cid = None
        action = {
            "id": 1, "actorCellId": 0, "championId": 0,
            "completed": False, "type": "pick", "isInProgress": True
        }
        session = {"localPlayerCellId": 0, "timer": {"adjustedTimeLeftInPhase": 20000}}
        picks = ["TestChamp"]

        # Run
        self.engine._perform_pick_action(action, picks, session)

        # Assert
        found_msg = False
        for call in self.log_mock.call_args_list:
            if "Hovering TestChamp (Auto-Lock Disabled)" in call[0][0]:
                found_msg = True

        self.assertTrue(found_msg, "Should log 'Hovering ... (Auto-Lock Disabled)'")

if __name__ == "__main__":
    unittest.main()
