import json
import sys
from unittest.mock import MagicMock

# Mock GUI dependencies






from services.asset_manager import AssetManager
from services.automation import AutomationEngine


# Mock Config
class MockConfig:
    def __init__(self):
        self.data = {
            "arena_pick_1": "Shaco",
            "arena_pick_2": "Teemo",
            "arena_ban_1": "Zed",
            "enable_auto_pick": True,
            "enable_auto_ban": True,
        }

    def get(self, key, default=None):
        return self.data.get(key, default)


# Mock Objects
lcu = MagicMock()
assets = MagicMock()
config = MockConfig()
auto = AutomationEngine(lcu, assets, config, log_func=print)

# Simulate Arena Session (myTeam size 2)
arena_session = {
    "myTeam": [{"cellId": 0}, {"cellId": 1}],
    "actions": [[{"id": 1, "type": "pick", "actorCellId": 0, "completed": False}]],
}

print("--- Testing Arena Detection ---")
picks = auto._get_pick_preferences(role="", session=arena_session)
print(f"Arena Picks Returned: {picks}")

bans = auto._get_ban_preference(role="", session=arena_session)
print(f"Arena Ban Returned: {bans}")

if "Shaco" in picks and bans == "Zed":
    print("\n✅ SUCCESS: Arena Mode detected and picks/bans returned.")
else:
    print("\n❌ FAILURE: Arena Logic faulty.")
