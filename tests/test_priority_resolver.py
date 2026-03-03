import unittest
from unittest.mock import MagicMock
from services.automation import AutomationEngine

class TestPriorityResolver(unittest.TestCase):
    def setUp(self):
        self.mock_lcu = MagicMock()
        self.mock_assets = MagicMock()
        self.mock_config = MagicMock()
        
        # Mock asset manager champ name/id mapping
        champ_map = {
            1: "Karthus",
            2: "Ziggs",
            3: "Lux",
            4: "AurelionSol",
            5: "Garen"
        }
        self.mock_assets.get_champ_name.side_effect = lambda cid: champ_map.get(cid, "Unknown")
        self.mock_assets.get_champ_id.side_effect = lambda name: {v:k for k,v in champ_map.items()}.get(name, 0)
        
        self.engine = AutomationEngine(self.mock_lcu, self.mock_assets, self.mock_config)
        self.engine._log = MagicMock()
        self.engine._last_priority_swap = 0 # reset cooldown
        
    def test_priority_resolver_picks_highest(self):
        priority_list = ["AurelionSol", "Karthus", "Ziggs", "Lux"]
        
        session = {
            "benchChampions": [
                {"championId": 2}, # Ziggs
                {"championId": 3}  # Lux
            ],
            "localPlayerCellId": 1,
            "myTeam": [
                {"cellId": 1, "championId": 5} # Holding Garen (Not in list)
            ]
        }
        
        self.engine._perform_priority_sniper(session, priority_list)
        
        # Should pick Ziggs (ID 2) because Ziggs is higher priority than Lux
        self.mock_lcu.request.assert_called_with("POST", "/lol-champ-select/v1/session/bench/swap/2")

    def test_priority_resolver_stays_if_holding_higher(self):
        priority_list = ["AurelionSol", "Karthus", "Ziggs", "Lux"]
        
        session = {
            "benchChampions": [
                {"championId": 3}  # Lux
            ],
            "localPlayerCellId": 1,
            "myTeam": [
                {"cellId": 1, "championId": 2} # Holding Ziggs
            ]
        }
        
        self.engine._perform_priority_sniper(session, priority_list)
        
        # Should NOT swap, since Ziggs > Lux
        self.mock_lcu.request.assert_not_called()
        
    def test_priority_resolver_swaps_if_holding_lower(self):
        priority_list = ["AurelionSol", "Karthus", "Ziggs", "Lux"]
        
        session = {
            "benchChampions": [
                {"championId": 1}  # Karthus
            ],
            "localPlayerCellId": 1,
            "myTeam": [
                {"cellId": 1, "championId": 2} # Holding Ziggs
            ]
        }
        
        # reset internal cooldown state just in case
        self.engine._last_priority_swap = 0 
        self.engine._perform_priority_sniper(session, priority_list)
        
        # Should swap to Karthus (ID 1), since Karthus > Ziggs
        self.mock_lcu.request.assert_called_with("POST", "/lol-champ-select/v1/session/bench/swap/1")

if __name__ == '__main__':
    unittest.main()
